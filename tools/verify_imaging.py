#!/usr/bin/env python3
"""Validate SKAetch bilinear Fourier sampling, gridding, and dirty imaging."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from skaetch.geometry import STAGES, load_station_coordinates
from skaetch.imaging import (
    apply_imaging_weighting,
    bilinear_sample_fourier_grid,
    centered_fft2,
    centered_ifft2,
    cloud_in_cell_grid,
    dirty_image_and_psf,
    fourier_axes_lambda,
)
from skaetch.sampling import earth_rotation_uvw_lambda, station_baselines_enu_m

FREQUENCY_HZ = 150e6
DECLINATION_DEG = -26.7
REAL_STAGE_HOUR_ANGLES_H = np.array([-3.0, 0.0, 3.0])
VISUAL_HOUR_ANGLES_H = np.linspace(-3.0, 3.0, 37)
GRID_SHAPE = (257, 257)
FIELD_OF_VIEW_RAD = np.deg2rad(0.20)
ATOL = 5e-12


def _assert_close(name: str, actual, expected, tolerance: float = ATOL) -> float:
    error = float(np.max(np.abs(np.asarray(actual) - np.asarray(expected))))
    if error > tolerance:
        raise AssertionError(f"{name}: error {error:.3e} exceeds {tolerance:.3e}")
    return error


def validate_bilinear_hand_calculation() -> tuple[float, float]:
    """Compare production interpolation with a literal four-corner hand calculation."""
    u_axis = np.array([-1.0, 0.0, 1.0])
    v_axis = np.array([-2.0, 0.0, 2.0])
    grid = np.array(
        [
            [0 + 0j, 1 + 2j, 2 + 4j],
            [10 + 1j, 11 + 3j, 12 + 5j],
            [20 + 2j, 21 + 4j, 22 + 6j],
        ],
        dtype=complex,
    )
    u = -0.25
    v = 1.0
    sampled, valid = bilinear_sample_fourier_grid(grid, u, v, u_axis, v_axis)
    if not bool(valid):
        raise AssertionError("interior bilinear sample was unexpectedly rejected")

    fu = 0.75
    fv = 0.50
    expected = (
        (1.0 - fu) * (1.0 - fv) * grid[1, 0]
        + fu * (1.0 - fv) * grid[1, 1]
        + (1.0 - fu) * fv * grid[2, 0]
        + fu * fv * grid[2, 1]
    )
    interior_error = abs(complex(sampled) - expected)
    if interior_error > ATOL:
        raise AssertionError(f"bilinear hand calculation error {interior_error:.3e}")

    boundary_samples, boundary_valid = bilinear_sample_fourier_grid(
        grid,
        np.array([-1.0, 1.0, 1.01]),
        np.array([-2.0, 2.0, 0.0]),
        u_axis,
        v_axis,
    )
    if not np.array_equal(boundary_valid, np.array([True, True, False])):
        raise AssertionError("inclusive boundary/out-of-domain handling is incorrect")
    boundary_error = max(
        abs(boundary_samples[0] - grid[0, 0]),
        abs(boundary_samples[1] - grid[2, 2]),
        abs(boundary_samples[2]),
    )
    if boundary_error > ATOL:
        raise AssertionError(f"bilinear boundary error {boundary_error:.3e}")
    return float(interior_error), float(boundary_error)


def validate_cic_conservation() -> tuple[float, float, int]:
    """Check four-cell weights, edge cases, conservation, and Hermitian conjugates."""
    axis = np.arange(-2.0, 3.0)
    u = np.array([0.25, 0.0, 2.0, -2.0, 2.5])
    v = np.array([0.50, 1.0, 2.0, 0.0, 0.0])
    values = np.array([2 + 3j, 1 - 2j, 4 + 0j, 5 + 1j, 99 + 0j])
    accumulated, density, accepted = cloud_in_cell_grid(
        u, v, values, axis, axis, clear_fourier_origin=False
    )
    if accepted != 4:
        raise AssertionError(f"expected 4 accepted samples, got {accepted}")
    conservation_error = abs(float(density.sum()) - 4.0)
    if conservation_error > ATOL:
        raise AssertionError(f"cloud-in-cell density conservation error {conservation_error:.3e}")

    # Hand-check the four cloud-in-cell weights for the off-grid (0.25, 0.50) sample.
    hand_density = np.zeros_like(density)
    _, hand_density, hand_accepted = cloud_in_cell_grid(
        [0.25], [0.50], [1.0], axis, axis, clear_fourier_origin=False
    )
    expected_hand = np.zeros_like(hand_density)
    expected_hand[2, 2] = 0.375
    expected_hand[2, 3] = 0.125
    expected_hand[3, 2] = 0.375
    expected_hand[3, 3] = 0.125
    hand_error = _assert_close("four-cell CIC hand weights", hand_density, expected_hand)
    if hand_accepted != 1:
        raise AssertionError("off-grid hand-check sample was not accepted exactly once")

    # Exact cell-centre sample at (0, 1) must land wholly in that cell.
    _, centre_density, centre_accepted = cloud_in_cell_grid(
        [0.0], [1.0], [1.0], axis, axis, clear_fourier_origin=False
    )
    expected_centre = np.zeros_like(centre_density)
    expected_centre[3, 2] = 1.0
    centre_error = _assert_close("cell-centre CIC", centre_density, expected_centre)
    if centre_accepted != 1:
        raise AssertionError("cell-centre sample was not accepted exactly once")

    # On the internal u=0 cell edge, v=0.5 must split equally between two cells.
    _, edge_density, edge_accepted = cloud_in_cell_grid(
        [0.0], [0.5], [1.0], axis, axis, clear_fourier_origin=False
    )
    expected_edge = np.zeros_like(edge_density)
    expected_edge[2, 2] = 0.5
    expected_edge[3, 2] = 0.5
    edge_error = _assert_close("cell-edge CIC", edge_density, expected_edge)
    if edge_accepted != 1:
        raise AssertionError("cell-edge sample was not accepted exactly once")

    # A single sample plus its conjugate should form a Hermitian gridded pair.
    pair_grid, pair_density, pair_accepted = cloud_in_cell_grid(
        [0.25],
        [0.50],
        [2.0 + 3.0j],
        axis,
        axis,
        include_conjugates=True,
        clear_fourier_origin=False,
    )
    if pair_accepted != 2:
        raise AssertionError(f"expected physical+conjugate count 2, got {pair_accepted}")
    hermitian_error = _assert_close(
        "conjugate Hermitian grid",
        pair_grid,
        np.conjugate(pair_grid[::-1, ::-1]),
    )
    _assert_close("conjugate density symmetry", pair_density, pair_density[::-1, ::-1])
    if abs(pair_density.sum() - 2.0) > ATOL:
        raise AssertionError("physical+conjugate density was not conserved")

    # SKAetch's imaging convention clears the exact Fourier-origin cell after
    # gridding.  A sample that would otherwise populate that cell must therefore
    # leave both the complex and density grids at zero there.
    origin_grid, origin_density, origin_accepted = cloud_in_cell_grid(
        [0.0],
        [0.0],
        [7.0 + 2.0j],
        axis,
        axis,
    )
    origin = (2, 2)
    if origin_accepted != 1:
        raise AssertionError("origin diagnostic sample was not counted as accepted")
    if origin_grid[origin] != 0.0j or origin_density[origin] != 0.0:
        raise AssertionError("Fourier origin was not cleared after gridding")

    # Ensure complex accumulation itself has not been confused with density.
    if np.allclose(accumulated.real, density):
        raise AssertionError("complex values and sampling density are not being accumulated independently")
    return conservation_error, max(hand_error, centre_error, edge_error, hermitian_error), accepted


def validate_weighting_distinction() -> tuple[float, float, float]:
    """Use deliberately repeated samples to distinguish natural and equal-cell weighting."""
    axis = np.arange(-3.0, 4.0)
    u = np.array([1.0, 1.0, 1.0, 1.0, -1.0])
    v = np.array([0.0, 0.0, 0.0, 0.0, 1.0])
    vis = np.ones(len(u), dtype=complex)
    accumulated, density, accepted = cloud_in_cell_grid(u, v, vis, axis, axis)
    if accepted != 5:
        raise AssertionError("repeated-sample weighting test rejected an on-grid point")

    natural_values, natural_weights = apply_imaging_weighting(accumulated, density, "natural")
    equal_values, equal_weights = apply_imaging_weighting(accumulated, density, "equal-cell")
    repeated_cell = (3, 4)  # v=0, u=+1
    single_cell = (4, 2)    # v=+1, u=-1
    natural_ratio = float(natural_weights[repeated_cell] / natural_weights[single_cell])
    equal_ratio = float(equal_weights[repeated_cell] / equal_weights[single_cell])
    if abs(natural_ratio - 4.0) > ATOL:
        raise AssertionError(f"natural repeated-cell weight ratio {natural_ratio:.6f}, expected 4")
    if abs(equal_ratio - 1.0) > ATOL:
        raise AssertionError(f"equal-cell weight ratio {equal_ratio:.6f}, expected 1")
    _assert_close("equal-cell cell normalisation", equal_values[repeated_cell], 1.0 + 0.0j)
    _assert_close("natural accumulated visibility", natural_values[repeated_cell], 4.0 + 0.0j)

    natural_dirty, _ = dirty_image_and_psf(accumulated, density, "natural")
    equal_dirty, _ = dirty_image_and_psf(accumulated, density, "equal-cell")
    image_difference = float(np.max(np.abs(natural_dirty - equal_dirty)))
    if image_difference <= 1e-3:
        raise AssertionError("natural and equal-cell dirty images did not respond differently to repeated sampling")
    return natural_ratio, equal_ratio, image_difference


def validate_fourier_and_psf_identities() -> tuple[float, float, float]:
    shape = (17, 17)
    centre = (shape[0] // 2, shape[1] // 2)
    delta = np.zeros(shape)
    delta[centre] = 1.0
    transform = centered_fft2(delta)
    delta_error = _assert_close("centred delta FFT", transform, np.ones(shape, dtype=complex))

    rng = np.random.default_rng(20260828)
    image = rng.normal(size=shape)
    round_trip = centered_ifft2(centered_fft2(image))
    round_trip_error = _assert_close("FFT round trip", round_trip, image, tolerance=2e-12)

    axis = np.arange(-8.0, 9.0)
    u = np.array([0.2, 1.6, -2.2, 3.1])
    v = np.array([1.1, -0.5, 2.7, -3.4])
    flux = 2.75
    accumulated, density, _ = cloud_in_cell_grid(
        u,
        v,
        np.full(len(u), flux, dtype=complex),
        axis,
        axis,
        include_conjugates=True,
    )
    dirty, psf = dirty_image_and_psf(accumulated, density, "natural")
    point_source_error = _assert_close("point-source dirty image", dirty, flux * psf, tolerance=2e-12)
    psf_peak_error = abs(psf[centre] - 1.0)
    if psf_peak_error > ATOL:
        raise AssertionError(f"normalised PSF central value error {psf_peak_error:.3e}")
    return delta_error, round_trip_error, max(point_source_error, float(psf_peak_error))


def synthetic_source(shape: tuple[int, int]) -> np.ndarray:
    y, x = np.indices(shape, dtype=float)
    y -= shape[0] // 2
    x -= shape[1] // 2
    source = np.exp(-0.5 * ((x / 15.0) ** 2 + (y / 8.0) ** 2))
    source += 0.55 * np.exp(-0.5 * (((x - 22.0) / 6.0) ** 2 + ((y + 14.0) / 5.0) ** 2))
    source += 0.25 * np.exp(-0.5 * (((x + 28.0) / 3.5) ** 2 + ((y - 18.0) / 3.5) ** 2))
    source /= source.sum()
    return source


def sample_real_stage(stage: str, hour_angles_h: np.ndarray) -> dict[str, object]:
    coordinates = np.asarray(load_station_coordinates(stage), dtype=float)
    baselines = station_baselines_enu_m(coordinates)
    uvw = earth_rotation_uvw_lambda(
        baselines,
        hour_angles_h,
        DECLINATION_DEG,
        FREQUENCY_HZ,
    )
    u = uvw[..., 0].reshape(-1)
    v = uvw[..., 1].reshape(-1)

    source = synthetic_source(GRID_SHAPE)
    fourier = centered_fft2(source)
    u_axis, v_axis = fourier_axes_lambda(GRID_SHAPE, FIELD_OF_VIEW_RAD)
    vis, valid = bilinear_sample_fourier_grid(fourier, u, v, u_axis, v_axis)

    # Use only physical points whose conjugates are also representable on the
    # finite even/odd Fourier grid.  GRID_SHAPE is odd here, so this also makes
    # the Hermitian relationship transparent and exact to floating-point error.
    _, valid_conjugate = bilinear_sample_fourier_grid(fourier, -u, -v, u_axis, v_axis)
    valid_pair = valid & valid_conjugate
    raw_accumulated, raw_density, raw_accepted = cloud_in_cell_grid(
        u[valid_pair],
        v[valid_pair],
        vis[valid_pair],
        u_axis,
        v_axis,
        include_conjugates=True,
        clear_fourier_origin=False,
    )
    accumulated, density, accepted = cloud_in_cell_grid(
        u[valid_pair],
        v[valid_pair],
        vis[valid_pair],
        u_axis,
        v_axis,
        include_conjugates=True,
    )
    expected_accepted = 2 * int(np.count_nonzero(valid_pair))
    if raw_accepted != expected_accepted or accepted != expected_accepted:
        raise AssertionError(
            f"{stage}: accepted gridding count raw={raw_accepted}, cleared={accepted}, "
            f"expected={expected_accepted}"
        )
    raw_density_error = abs(float(raw_density.sum()) - expected_accepted)
    density_relative_error = raw_density_error / max(float(expected_accepted), 1.0)
    if density_relative_error > 5e-14:
        raise AssertionError(
            f"{stage}: pre-origin-clear density conservation relative error "
            f"{density_relative_error:.3e}"
        )

    origin = (len(v_axis) // 2, len(u_axis) // 2)
    removed_zero_spacing_weight = float(raw_density[origin])
    if accumulated[origin] != 0.0j or density[origin] != 0.0:
        raise AssertionError(f"{stage}: Fourier origin was not cleared")
    density_error = abs(
        float(density.sum()) - (expected_accepted - removed_zero_spacing_weight)
    )
    if density_error / max(float(expected_accepted), 1.0) > 5e-14:
        raise AssertionError(f"{stage}: post-origin-clear density accounting failed")

    hermitian_error = float(np.max(np.abs(accumulated - np.conjugate(accumulated[::-1, ::-1]))))
    density_symmetry_error = float(np.max(np.abs(density - density[::-1, ::-1])))
    visibility_scale = max(float(np.max(np.abs(accumulated))), 1.0)
    density_scale = max(float(np.max(density)), 1.0)
    hermitian_relative_error = hermitian_error / visibility_scale
    density_symmetry_relative_error = density_symmetry_error / density_scale
    if hermitian_relative_error > 5e-13 or density_symmetry_relative_error > 5e-13:
        raise AssertionError(
            f"{stage}: conjugate symmetry relative errors "
            f"visibility={hermitian_relative_error:.3e}, "
            f"density={density_symmetry_relative_error:.3e}"
        )

    natural_dirty, natural_psf = dirty_image_and_psf(accumulated, density, "natural")
    equal_dirty, equal_psf = dirty_image_and_psf(accumulated, density, "equal-cell")
    imag_error = max(
        float(np.max(np.abs(natural_dirty.imag))),
        float(np.max(np.abs(equal_dirty.imag))),
        float(np.max(np.abs(natural_psf.imag))),
        float(np.max(np.abs(equal_psf.imag))),
    )
    if imag_error > 2e-12:
        raise AssertionError(f"{stage}: Hermitian dirty-image imaginary residue {imag_error:.3e}")

    return {
        "stage": stage,
        "stations": len(coordinates),
        "baselines": len(baselines),
        "physical_samples": len(u),
        "accepted_physical": int(np.count_nonzero(valid_pair)),
        "acceptance_fraction": float(np.count_nonzero(valid_pair) / max(len(u), 1)),
        "density_error": density_error,
        "density_relative_error": density_relative_error,
        "removed_zero_spacing_weight": removed_zero_spacing_weight,
        "hermitian_error": hermitian_error,
        "hermitian_relative_error": hermitian_relative_error,
        "density_symmetry_relative_error": density_symmetry_relative_error,
        "imag_error": imag_error,
        "source": source,
        "fourier": fourier,
        "density": density,
        "natural_dirty": natural_dirty.real,
        "equal_dirty": equal_dirty.real,
        "natural_psf": natural_psf.real,
        "equal_psf": equal_psf.real,
    }


def write_weighting_plot(output_dir: Path) -> None:
    axis = np.arange(-3.0, 4.0)
    u = np.array([1.0, 1.0, 1.0, 1.0, -1.0])
    v = np.array([0.0, 0.0, 0.0, 0.0, 1.0])
    accumulated, density, _ = cloud_in_cell_grid(u, v, np.ones(len(u)), axis, axis)
    natural_dirty, natural_psf = dirty_image_and_psf(accumulated, density, "natural")
    equal_dirty, equal_psf = dirty_image_and_psf(accumulated, density, "equal-cell")

    fig, axes = plt.subplots(2, 2, figsize=(8.0, 7.0), constrained_layout=True)
    panels = [
        (natural_psf.real, "Natural PSF"),
        (equal_psf.real, "Equal-cell PSF"),
        (natural_dirty.real, "Natural dirty image"),
        (equal_dirty.real, "Equal-cell dirty image"),
    ]
    for ax, (data, title) in zip(axes.flat, panels, strict=True):
        image = ax.imshow(data, origin="lower", interpolation="nearest")
        ax.set_title(title)
        ax.set_xlabel("image x pixel")
        ax.set_ylabel("image y pixel")
        fig.colorbar(image, ax=ax, shrink=0.8)
    fig.suptitle("Repeated UV samples: natural versus equal-cell weighting")
    fig.savefig(output_dir / "weighting_comparison.png", dpi=220)
    plt.close(fig)


def write_real_stage_plot(result: dict[str, object], output_dir: Path) -> None:
    source = np.asarray(result["source"])
    fourier = np.asarray(result["fourier"])
    density = np.asarray(result["density"])
    natural = np.asarray(result["natural_dirty"])
    equal = np.asarray(result["equal_dirty"])
    u_axis, v_axis = fourier_axes_lambda(GRID_SHAPE, FIELD_OF_VIEW_RAD)
    half_fov_arcmin = 0.5 * np.rad2deg(FIELD_OF_VIEW_RAD) * 60.0
    angular_extent = (-half_fov_arcmin, half_fov_arcmin, -half_fov_arcmin, half_fov_arcmin)
    uv_extent = (u_axis[0] / 1e3, u_axis[-1] / 1e3, v_axis[0] / 1e3, v_axis[-1] / 1e3)

    fig, axes = plt.subplots(2, 3, figsize=(12.0, 7.5), constrained_layout=True)
    panels = [
        (source, "Artificial source", angular_extent, "x (arcmin)", "y (arcmin)"),
        (np.log10(1.0 + np.abs(fourier)), "log10(1 + |Fourier plane|)", uv_extent, "u (kλ)", "v (kλ)"),
        (np.log10(1.0 + density), "log10(1 + sampling density)", uv_extent, "u (kλ)", "v (kλ)"),
        (natural, "Natural dirty image", angular_extent, "x (arcmin)", "y (arcmin)"),
        (equal, "Equal-cell dirty image", angular_extent, "x (arcmin)", "y (arcmin)"),
        (natural - equal, "Natural − equal-cell", angular_extent, "x (arcmin)", "y (arcmin)"),
    ]
    for ax, (data, title, extent, x_label, y_label) in zip(axes.flat, panels, strict=True):
        image = ax.imshow(data, origin="lower", extent=extent, aspect="equal")
        ax.set_title(title)
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
        fig.colorbar(image, ax=ax, shrink=0.78)
    fig.suptitle(
        f"SKA-Low {result['stage']} imaging validation: "
        f"{result['accepted_physical']:,}/{result['physical_samples']:,} physical UV samples accepted"
    )
    fig.savefig(output_dir / "real_ska_imaging.png", dpi=220)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stages",
        nargs="+",
        choices=STAGES,
        default=list(STAGES),
        help="SKA-Low stages to exercise; default is all five",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("build/imaging-validation"),
        help="Directory for ignored visual validation products",
    )
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()

    interpolation_error, boundary_error = validate_bilinear_hand_calculation()
    conservation_error, symmetry_error, accepted = validate_cic_conservation()
    natural_ratio, equal_ratio, weighting_difference = validate_weighting_distinction()
    delta_error, round_trip_error, point_source_error = validate_fourier_and_psf_identities()

    rows = [sample_real_stage(stage, REAL_STAGE_HOUR_ANGLES_H) for stage in args.stages]

    if not args.no_plots:
        plot_dir = args.output / "plots"
        plot_dir.mkdir(parents=True, exist_ok=True)
        write_weighting_plot(plot_dir)
        visual_stage = "AA2" if "AA2" in args.stages else args.stages[-1]
        visual_result = sample_real_stage(visual_stage, VISUAL_HOUR_ANGLES_H)
        write_real_stage_plot(visual_result, plot_dir)
        print(f"Wrote visual validation plots to {plot_dir}")

    print(
        f"PASS bilinear interpolation: hand error {interpolation_error:.3e}, "
        f"boundary error {boundary_error:.3e}"
    )
    print(
        f"PASS cloud-in-cell: density error {conservation_error:.3e}, "
        f"symmetry/centre error {symmetry_error:.3e}, accepted synthetic samples {accepted}"
    )
    print(
        f"PASS weighting distinction: natural repeated/single ratio {natural_ratio:.1f}, "
        f"equal-cell ratio {equal_ratio:.1f}, max dirty-image difference {weighting_difference:.3e}"
    )
    print(
        f"PASS Fourier identities: delta {delta_error:.3e}, round trip {round_trip_error:.3e}, "
        f"point-source/PSF {point_source_error:.3e}"
    )
    for row in rows:
        print(
            f"PASS {row['stage']:5s}: {row['stations']:3d} stations, {row['baselines']:6d} baselines, "
            f"accepted {row['accepted_physical']:,}/{row['physical_samples']:,} physical samples "
            f"({100.0 * row['acceptance_fraction']:.2f}%), density rel. error "
            f"{row['density_relative_error']:.3e}, DC weight removed "
            f"{row['removed_zero_spacing_weight']:.3f}, Hermitian rel. error "
            f"{row['hermitian_relative_error']:.3e}, image Im residue {row['imag_error']:.3e}"
        )
    print("PASS SKAetch Fourier gridding and dirty imaging")


if __name__ == "__main__":
    main()
