#!/usr/bin/env python3
"""Validate SKAetch's ENU -> equatorial XYZ -> UVW coordinate transforms."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from skaetch.geometry import STAGES, load_station_coordinates
from skaetch.uvw import (
    C_M_S,
    SKA_LOW_LATITUDE_DEG,
    enu_baseline_to_uvw_lambda,
    enu_to_equatorial_xyz_m,
    equatorial_xyz_to_uvw_m,
    xyz_to_uvw_rotation,
)

FREQUENCY_HZ = 150e6
MATRIX_TOLERANCE_LAMBDA = 1e-9
NORM_TOLERANCE_RELATIVE = 1e-12
ZENITH_TOLERANCE_LAMBDA = 1e-9
ORIENTATION_TOLERANCE_M = 1e-12
STAGE_SLUGS = {
    "AA0.5": "AA0p5",
    "AA1": "AA1",
    "AA2": "AA2",
    "AA*": "AAstar",
    "AA4": "AA4",
}


def station_baselines(stage: str) -> tuple[np.ndarray, np.ndarray]:
    """Return all ``station_2 - station_1`` East/North baselines for a stage."""
    coordinates = np.asarray(load_station_coordinates(stage), dtype=float)
    first, second = np.triu_indices(len(coordinates), 1)
    delta = coordinates[second] - coordinates[first]
    return delta[:, 0], delta[:, 1]


def reference_matrix_uvw_lambda(
    east_m: np.ndarray,
    north_m: np.ndarray,
    hour_angle_h: float,
    declination_deg: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Independent literal matrix expression of the documented transform."""
    hour_angle_rad = math.radians(hour_angle_h * 15.0)
    declination_rad = math.radians(declination_deg)
    latitude_rad = math.radians(SKA_LOW_LATITUDE_DEG)

    x_m = -math.sin(latitude_rad) * north_m
    y_m = east_m
    z_m = math.cos(latitude_rad) * north_m
    matrix = np.array(
        [
            [math.sin(hour_angle_rad), math.cos(hour_angle_rad), 0.0],
            [
                -math.sin(declination_rad) * math.cos(hour_angle_rad),
                math.sin(declination_rad) * math.sin(hour_angle_rad),
                math.cos(declination_rad),
            ],
            [
                math.cos(declination_rad) * math.cos(hour_angle_rad),
                -math.cos(declination_rad) * math.sin(hour_angle_rad),
                math.sin(declination_rad),
            ],
        ],
        dtype=float,
    )
    xyz_m = np.vstack((x_m, y_m, z_m))
    uvw_m = matrix @ xyz_m
    wavelength_m = C_M_S / FREQUENCY_HZ
    return tuple(uvw_m[index] / wavelength_m for index in range(3))


def maximum_abs_difference(left, right) -> float:
    return float(np.max(np.abs(np.asarray(left) - np.asarray(right))))


def validate_reference_matrix() -> float:
    rng = np.random.default_rng(20260818)
    east_m = rng.normal(0.0, 20_000.0, 2048)
    north_m = rng.normal(0.0, 20_000.0, 2048)
    hour_angle_h = float(rng.uniform(-5.0, 5.0))
    declination_deg = float(rng.uniform(-70.0, 40.0))

    actual = enu_baseline_to_uvw_lambda(
        east_m,
        north_m,
        0.0,
        hour_angle_h,
        declination_deg,
        FREQUENCY_HZ,
    )
    reference = reference_matrix_uvw_lambda(
        east_m,
        north_m,
        hour_angle_h,
        declination_deg,
    )
    error = max(
        maximum_abs_difference(actual[index], reference[index])
        for index in range(3)
    )
    if error >= MATRIX_TOLERANCE_LAMBDA:
        raise AssertionError(
            f"independent matrix error {error:.3e} wavelengths exceeds "
            f"{MATRIX_TOLERANCE_LAMBDA:.1e}"
        )
    return error


def validate_rotation_matrix() -> tuple[float, float]:
    """Check that the explicit XYZ -> UVW matrix is a proper rotation."""
    hour_angle_rad = np.deg2rad(np.linspace(-90.0, 90.0, 19))
    declination_rad = np.deg2rad(np.linspace(-70.0, 40.0, 19))
    rotation = xyz_to_uvw_rotation(hour_angle_rad, declination_rad)
    identity = np.einsum("...ik,...jk->...ij", rotation, rotation)
    orthogonality_error = float(
        np.max(np.abs(identity - np.eye(3, dtype=float)))
    )
    determinant_error = float(np.max(np.abs(np.linalg.det(rotation) - 1.0)))
    if max(orthogonality_error, determinant_error) >= NORM_TOLERANCE_RELATIVE:
        raise AssertionError(
            "rotation-matrix error exceeds "
            f"{NORM_TOLERANCE_RELATIVE:.1e}: "
            f"orthogonality={orthogonality_error:.3e}, "
            f"determinant={determinant_error:.3e}"
        )
    return orthogonality_error, determinant_error


def validate_norm_invariance() -> tuple[float, float]:
    rng = np.random.default_rng(20260818)
    east_m = rng.normal(0.0, 20_000.0, 2048)
    north_m = rng.normal(0.0, 20_000.0, 2048)
    up_m = rng.normal(0.0, 100.0, 2048)
    latitude_rad = math.radians(SKA_LOW_LATITUDE_DEG)
    hour_angle_rad = math.radians(float(rng.uniform(-75.0, 75.0)))
    declination_rad = math.radians(float(rng.uniform(-70.0, 40.0)))

    b_x_m, b_y_m, b_z_m = enu_to_equatorial_xyz_m(
        east_m,
        north_m,
        up_m,
        latitude_rad=latitude_rad,
    )
    b_u_m, b_v_m, b_w_m = equatorial_xyz_to_uvw_m(
        b_x_m,
        b_y_m,
        b_z_m,
        hour_angle_rad,
        declination_rad,
    )

    norm_enu = np.sqrt(east_m**2 + north_m**2 + up_m**2)
    norm_xyz = np.sqrt(b_x_m**2 + b_y_m**2 + b_z_m**2)
    norm_uvw = np.sqrt(b_u_m**2 + b_v_m**2 + b_w_m**2)
    denominator = np.maximum(norm_enu, np.finfo(float).tiny)
    xyz_error = float(np.max(np.abs(norm_xyz - norm_enu) / denominator))
    uvw_error = float(np.max(np.abs(norm_uvw - norm_enu) / denominator))

    if max(xyz_error, uvw_error) >= NORM_TOLERANCE_RELATIVE:
        raise AssertionError(
            "rotation norm error exceeds "
            f"{NORM_TOLERANCE_RELATIVE:.1e}: XYZ={xyz_error:.3e}, "
            f"UVW={uvw_error:.3e}"
        )
    return xyz_error, uvw_error


def validate_orientation() -> dict[str, float]:
    """Lock down the adopted hour-angle direction with simple unit baselines."""
    east_m = 1.0
    north_m = 0.0
    up_m = 0.0

    transit = enu_baseline_to_uvw_lambda(
        east_m,
        north_m,
        up_m,
        0.0,
        SKA_LOW_LATITUDE_DEG,
        FREQUENCY_HZ,
    )
    wavelength_m = C_M_S / FREQUENCY_HZ
    transit_u_m = float(transit[0] * wavelength_m)
    transit_v_m = float(transit[1] * wavelength_m)
    transit_w_m = float(transit[2] * wavelength_m)

    before = enu_baseline_to_uvw_lambda(
        east_m,
        north_m,
        up_m,
        -6.0,
        0.0,
        FREQUENCY_HZ,
    )
    after = enu_baseline_to_uvw_lambda(
        east_m,
        north_m,
        up_m,
        6.0,
        0.0,
        FREQUENCY_HZ,
    )
    before_w_m = float(before[2] * wavelength_m)
    after_w_m = float(after[2] * wavelength_m)

    checks = {
        "transit_b_u_m": transit_u_m,
        "transit_b_v_m": transit_v_m,
        "transit_b_w_m": transit_w_m,
        "minus_6h_b_w_m": before_w_m,
        "plus_6h_b_w_m": after_w_m,
    }
    expected = {
        "transit_b_u_m": 1.0,
        "transit_b_v_m": 0.0,
        "transit_b_w_m": 0.0,
        "minus_6h_b_w_m": 1.0,
        "plus_6h_b_w_m": -1.0,
    }
    for name, value in checks.items():
        if abs(value - expected[name]) >= ORIENTATION_TOLERANCE_M:
            raise AssertionError(
                f"orientation check {name}={value:.16g}, expected {expected[name]:.16g}"
            )
    return checks


def stage_marker_size(baseline_count: int) -> float:
    if baseline_count <= 200:
        return 12.0
    if baseline_count <= 3_000:
        return 4.0
    if baseline_count <= 50_000:
        return 1.2
    return 0.35


def write_zenith_plot(
    stage: str,
    u_lambda: np.ndarray,
    v_lambda: np.ndarray,
    output_dir: Path,
) -> None:
    u_klambda = np.asarray(u_lambda) / 1000.0
    v_klambda = np.asarray(v_lambda) / 1000.0
    baseline_count = len(u_klambda)
    slug = STAGE_SLUGS[stage]

    with plt.rc_context(
        {
            "font.size": 11,
            "axes.titlesize": 12,
            "axes.labelsize": 11,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
        }
    ):
        figure, axes = plt.subplots(figsize=(6.4, 6.0), constrained_layout=True)
        rasterized = baseline_count > 20_000
        scatter_kwargs = {
            "s": stage_marker_size(baseline_count),
            "marker": "o",
            "linewidths": 0,
            "rasterized": rasterized,
        }
        axes.scatter(u_klambda, v_klambda, **scatter_kwargs)
        axes.scatter(-u_klambda, -v_klambda, **scatter_kwargs)
        axes.set_aspect("equal", adjustable="box")
        axes.margins(x=0.04, y=0.04)
        axes.set_xlabel("u (kλ)")
        axes.set_ylabel("v (kλ)")
        axes.set_title(
            f"SKA-Low {stage} zenith UV coverage at 150 MHz\n"
            f"{baseline_count:,} baselines + conjugates"
        )
        axes.grid(alpha=0.2, linewidth=0.5)
        figure.savefig(output_dir / f"{slug}_zenith_uv.png", dpi=300)
        figure.savefig(output_dir / f"{slug}_zenith_uv.pdf")
        plt.close(figure)


def validate_stages(plot_dir: Path | None) -> list[dict[str, float | int | str]]:
    rows: list[dict[str, float | int | str]] = []
    wavelength_m = C_M_S / FREQUENCY_HZ

    for stage in STAGES:
        east_m, north_m = station_baselines(stage)
        u_lambda, v_lambda, w_lambda = enu_baseline_to_uvw_lambda(
            east_m,
            north_m,
            0.0,
            0.0,
            SKA_LOW_LATITUDE_DEG,
            FREQUENCY_HZ,
        )
        expected_u = east_m / wavelength_m
        expected_v = north_m / wavelength_m
        zenith_error = max(
            maximum_abs_difference(u_lambda, expected_u),
            maximum_abs_difference(v_lambda, expected_v),
            float(np.max(np.abs(w_lambda))),
        )
        if zenith_error >= ZENITH_TOLERANCE_LAMBDA:
            raise AssertionError(
                f"{stage}: zenith identity error {zenith_error:.3e} wavelengths exceeds "
                f"{ZENITH_TOLERANCE_LAMBDA:.1e}"
            )

        rows.append(
            {
                "stage": stage,
                "baselines": len(east_m),
                "zenith_error_lambda": zenith_error,
                "max_abs_u_klambda": float(np.max(np.abs(u_lambda)) / 1000.0),
                "max_abs_v_klambda": float(np.max(np.abs(v_lambda)) / 1000.0),
            }
        )
        if plot_dir is not None:
            write_zenith_plot(stage, u_lambda, v_lambda, plot_dir)

    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("build/uvw-validation"),
        help="Directory for ignored visual validation products",
    )
    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="Run numerical checks without creating validation plots",
    )
    args = parser.parse_args()

    matrix_error = validate_reference_matrix()
    rotation_orthogonality_error, rotation_determinant_error = validate_rotation_matrix()
    xyz_norm_error, uvw_norm_error = validate_norm_invariance()
    orientation = validate_orientation()

    plot_dir = None
    if not args.no_plots:
        plot_dir = args.output / "plots"
        plot_dir.mkdir(parents=True, exist_ok=True)

    stage_rows = validate_stages(plot_dir)

    print(f"PASS independent matrix: {matrix_error:.3e} wavelengths")
    print(
        "PASS explicit rotation:   "
        f"orthogonality {rotation_orthogonality_error:.3e}, "
        f"|det(R)-1| {rotation_determinant_error:.3e}"
    )
    print(f"PASS ENU -> XYZ norm:    {xyz_norm_error:.3e} relative")
    print(f"PASS XYZ -> UVW norm:    {uvw_norm_error:.3e} relative")
    print(
        "PASS hour-angle orientation: "
        f"transit B_U={orientation['transit_b_u_m']:+.1f} m, "
        f"H=-6h B_W={orientation['minus_6h_b_w_m']:+.1f} m, "
        f"H=+6h B_W={orientation['plus_6h_b_w_m']:+.1f} m"
    )
    for row in stage_rows:
        print(
            f"PASS {row['stage']:5s}: {row['baselines']:6d} baselines, "
            f"zenith error {row['zenith_error_lambda']:.3e} λ, "
            f"|u|max {row['max_abs_u_klambda']:.3f} kλ, "
            f"|v|max {row['max_abs_v_klambda']:.3f} kλ"
        )
    if plot_dir is not None:
        print(f"Wrote visual validation plots to {plot_dir}")
    print("PASS SKAetch UVW geometry")


if __name__ == "__main__":
    main()
