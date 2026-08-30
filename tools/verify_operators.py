#!/usr/bin/env python3
"""Validate frozen SKAetch operators and idealised science reconstruction."""

from __future__ import annotations

import argparse
import hashlib
from importlib.resources import as_file, files
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from skimage import color, transform

from skaetch.geometry import STAGES, load_station_coordinates
from skaetch.imaging import centered_fft2, centered_ifft2
from skaetch.operators import (
    DECLINATION_DEG,
    DURATIONS,
    FREQUENCY_HZ,
    OUTREACH_SPEC,
    SOURCE_SIZE_DEG,
    SCIENCE_SPEC,
    build_sparse_operator_from_uv,
    duration_hour_angles_h,
    load_frozen_operator,
    load_operator_manifest,
    source_pixels_for_spec,
)
from skaetch.preprocessing import (
    centre_square_crop,
    embed_preprocessed_source,
    robust_preprocess,
    science_preprocess,
)
from skaetch.reconstruction import (
    SCIENCE_RECONSTRUCTION_ITERATIONS,
    central_support_mask,
    positive_support_reconstruction,
)
from skaetch.sampling import earth_rotation_uvw_lambda, station_baselines_enu_m

COEFF_REL_TOL = 2e-6
SCIENCE_WEIGHT_REL_TOL = 2e-12


def sha256_resource(resource) -> str:
    digest = hashlib.sha256()
    with resource.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def synthetic_rgb(height: int = 180, width: int = 250) -> np.ndarray:
    """Return a deterministic portrait-like test pattern without external assets."""
    y, x = np.indices((height, width), dtype=float)
    xn = (x - (width - 1) / 2) / (0.5 * width)
    yn = (y - (height - 1) / 2) / (0.5 * height)
    face = np.exp(-((xn / 0.55) ** 2 + (yn / 0.78) ** 2) * 2.0)
    eye1 = np.exp(-(((xn + 0.20) / 0.08) ** 2 + ((yn + 0.16) / 0.06) ** 2) * 2.0)
    eye2 = np.exp(-(((xn - 0.20) / 0.08) ** 2 + ((yn + 0.16) / 0.06) ** 2) * 2.0)
    mouth_curve = yn - (0.20 + 0.22 * xn**2)
    mouth = np.exp(-((mouth_curve / 0.035) ** 2 + (xn / 0.34) ** 8))
    base = np.clip(0.15 + 0.70 * face - 0.38 * eye1 - 0.38 * eye2 - 0.34 * mouth, 0.0, 1.0)
    return np.dstack((base, np.clip(0.15 + 0.8 * base, 0.0, 1.0), np.clip(0.25 + 0.65 * base, 0.0, 1.0)))


def validate_manifests_and_assets() -> tuple[int, float, float]:
    asset_count = 0
    max_equal_cell_sum_error = 0.0
    max_science_weight_rel_error = 0.0
    for mode, spec in (("outreach", OUTREACH_SPEC), ("science", SCIENCE_SPEC)):
        manifest = load_operator_manifest(mode)
        expected = {
            "mode": mode,
            "weighting": spec.weighting,
            "frequency_hz": FREQUENCY_HZ,
            "declination_deg": DECLINATION_DEG,
            "field_deg": spec.field_deg,
            "npix": spec.npix,
            "source_size_deg": SOURCE_SIZE_DEG,
        }
        for key, value in expected.items():
            if manifest.get(key) != value:
                raise AssertionError(f"{mode} manifest {key}: {manifest.get(key)!r} != {value!r}")

        asset_dir = files("skaetch").joinpath("data", "operators", mode)
        for stage in STAGES:
            for duration in DURATIONS:
                record = manifest["operators"][stage][duration]
                asset = asset_dir.joinpath(record["file"])
                digest = sha256_resource(asset)
                if digest != record["sha256"]:
                    raise AssertionError(f"{mode} {stage} {duration}: SHA-256 mismatch")
                op = load_frozen_operator(stage, duration, mode)
                asset_count += 1
                if len(op.touched) != int(record["touched_uv_cells"]):
                    raise AssertionError(f"{mode} {stage} {duration}: touched-cell count mismatch")
                if op.accepted_samples != int(record["accepted_samples"]) or op.total_samples != int(record["total_samples"]):
                    raise AssertionError(f"{mode} {stage} {duration}: sample-count mismatch")
                if op.coeff.dtype != np.float32 or op.touched.dtype != np.int32 or op.input_indices.dtype != np.int32:
                    raise AssertionError(f"{mode} {stage} {duration}: unexpected archive dtypes")

                if mode == "outreach":
                    cell_sum = op.coeff.sum(axis=0, dtype=np.float32)
                    error = float(np.max(np.abs(cell_sum - 1.0)))
                    max_equal_cell_sum_error = max(max_equal_cell_sum_error, error)
                    if error > 5e-5:
                        raise AssertionError(f"{stage} {duration}: equal-cell coefficient sum error {error:.3e}")
                else:
                    coefficient_sum = float(op.coeff.sum(dtype=np.float64))
                    assert op.total_weight is not None
                    rel = abs(coefficient_sum - op.total_weight) / op.total_weight
                    max_science_weight_rel_error = max(max_science_weight_rel_error, rel)
                    if rel > 2e-15:
                        raise AssertionError(f"{stage} {duration}: natural-weight sum error {rel:.3e}")
                    if abs(op.total_weight - float(record["total_weight"])) > 1e-9 * op.total_weight:
                        raise AssertionError(f"{stage} {duration}: manifest total_weight mismatch")
    if asset_count != 20:
        raise AssertionError(f"expected 20 frozen operator assets, found {asset_count}")
    return asset_count, max_equal_cell_sum_error, max_science_weight_rel_error


def reproduce_operator_arrays() -> tuple[float, float, int]:
    max_coeff_relative_error = 0.0
    max_weight_relative_error = 0.0
    reproduced = 0
    for mode, spec in (("outreach", OUTREACH_SPEC), ("science", SCIENCE_SPEC)):
        for stage in STAGES:
            coordinates = np.asarray(load_station_coordinates(stage), dtype=float)
            baselines = station_baselines_enu_m(coordinates)
            for duration in DURATIONS:
                uvw = earth_rotation_uvw_lambda(
                    baselines,
                    duration_hour_angles_h(duration),
                    DECLINATION_DEG,
                    FREQUENCY_HZ,
                )
                built = build_sparse_operator_from_uv(uvw[..., 0], uvw[..., 1], spec)
                frozen = load_frozen_operator(stage, duration, mode)
                reproduced += 1

                if not np.array_equal(built.touched, frozen.touched):
                    raise AssertionError(f"{mode} {stage} {duration}: reproduced touched cells differ")
                if not np.array_equal(built.input_indices, frozen.input_indices):
                    raise AssertionError(f"{mode} {stage} {duration}: reproduced input indices differ")
                if built.accepted_samples != frozen.accepted_samples or built.total_samples != frozen.total_samples:
                    raise AssertionError(f"{mode} {stage} {duration}: reproduced sample counts differ")

                coefficient_error = float(np.max(np.abs(built.coeff - frozen.coeff))) if built.coeff.size else 0.0
                coefficient_scale = max(float(np.max(np.abs(frozen.coeff))), 1e-30)
                coefficient_relative_error = coefficient_error / coefficient_scale
                max_coeff_relative_error = max(max_coeff_relative_error, coefficient_relative_error)
                if coefficient_relative_error > COEFF_REL_TOL:
                    raise AssertionError(
                        f"{mode} {stage} {duration}: coefficient relative error {coefficient_relative_error:.3e}"
                    )

                if mode == "science":
                    assert built.total_weight is not None and frozen.total_weight is not None
                    weight_relative_error = abs(built.total_weight - frozen.total_weight) / frozen.total_weight
                    max_weight_relative_error = max(max_weight_relative_error, weight_relative_error)
                    if weight_relative_error > SCIENCE_WEIGHT_REL_TOL:
                        raise AssertionError(
                            f"{stage} {duration}: total-weight relative error {weight_relative_error:.3e}"
                        )
    return max_coeff_relative_error, max_weight_relative_error, reproduced


def literal_science_preprocess(image) -> np.ndarray:
    image = centre_square_crop(image)
    if image.ndim == 2:
        grey = np.asarray(image, dtype=float)
    else:
        grey = color.rgb2gray(np.asarray(image)[..., :3])
    p1, p99 = np.percentile(grey, [1, 99])
    if p99 - p1 > 1e-6:
        return np.clip((grey - p1) / (p99 - p1), 0.0, 1.0)
    return np.clip(grey, 0.0, 1.0)


def validate_science_preprocess_and_embedding() -> tuple[float, float, int, int]:
    rgb = synthetic_rgb()
    preprocessed = science_preprocess(rgb)
    reference = literal_science_preprocess(rgb)
    preprocess_error = float(np.max(np.abs(preprocessed - reference)))
    if preprocess_error > 5e-12:
        raise AssertionError(f"science preprocessing reference error {preprocess_error:.3e}")

    science_pixels = source_pixels_for_spec(SCIENCE_SPEC)
    outreach_pixels = source_pixels_for_spec(OUTREACH_SPEC)
    if science_pixels != 146 or outreach_pixels != 137:
        raise AssertionError(
            f"unexpected 0.10-degree source sizes: science={science_pixels}, outreach={outreach_pixels}"
        )

    sky = embed_preprocessed_source(
        preprocessed,
        (SCIENCE_SPEC.npix, SCIENCE_SPEC.npix),
        (science_pixels, science_pixels),
        total_flux=1.0,
    )
    flux_error = abs(float(sky.sum()) - 1.0)
    if flux_error > 2e-12:
        raise AssertionError(f"science artificial-source flux error {flux_error:.3e}")
    return preprocess_error, flux_error, outreach_pixels, science_pixels


def validate_operator_application() -> tuple[float, float, float]:
    max_point_error = 0.0
    max_manual_error = 0.0
    max_dirty_centre_error = 0.0
    for mode, stage, duration in (
        ("outreach", "AA2", "6h"),
        ("science", "AA2", "6h"),
    ):
        op = load_frozen_operator(stage, duration, mode)
        source_ft = np.ones((op.spec.npix, op.spec.npix), dtype=np.complex64)
        values = op.values(source_ft)
        manual = np.zeros(len(op.touched), dtype=np.complex64)
        flat = source_ft.ravel()
        for k in range(op.coeff.shape[0]):
            manual += op.coeff[k] * flat[op.input_indices[k]]
        manual_error = float(np.max(np.abs(values - manual)))
        max_manual_error = max(max_manual_error, manual_error)
        if manual_error != 0.0:
            raise AssertionError(f"{mode} sparse application differs from literal stencil by {manual_error:.3e}")

        if mode == "outreach":
            point_error = float(np.max(np.abs(values.real - 1.0)))
        else:
            point_error = float(np.max(np.abs(values.real - op.density)))
        max_point_error = max(max_point_error, point_error)
        if point_error > 5e-5:
            raise AssertionError(f"{mode} point-source Fourier response error {point_error:.3e}")

        dirty = op.dirty_image(source_ft)
        centre = dirty[op.spec.npix // 2, op.spec.npix // 2]
        dirty_error = abs(float(centre) - 1.0)
        max_dirty_centre_error = max(max_dirty_centre_error, dirty_error)
        if dirty_error > 5e-6:
            raise AssertionError(f"{mode} point-source dirty-image centre error {dirty_error:.3e}")
    return max_manual_error, max_point_error, max_dirty_centre_error


def literal_reconstruction(observed, touched, source_pixels: int, iterations: int) -> np.ndarray:
    observed = np.asarray(observed)
    npix = observed.shape[0]
    centre = npix // 2
    half = source_pixels // 2 + 3
    support = np.zeros((npix, npix), dtype=bool)
    support[centre - half : centre + half + 1, centre - half : centre + half + 1] = True
    current = observed.astype(np.complex64, copy=True)
    observed_flat = observed.ravel()
    for _ in range(iterations):
        image = np.real(np.fft.fftshift(np.fft.ifft2(np.fft.ifftshift(current))))
        image = np.maximum(image, 0.0)
        image[~support] = 0.0
        estimate = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(image))).astype(np.complex64)
        estimate.ravel()[touched] = observed_flat[touched]
        current = estimate
    image = np.real(np.fft.fftshift(np.fft.ifft2(np.fft.ifftshift(current))))
    image = np.maximum(image, 0.0)
    image[~support] = 0.0
    return image.astype(np.float32)


def validate_reconstruction() -> tuple[float, float, float]:
    rng = np.random.default_rng(20260830)
    observed = rng.normal(size=(64, 64)) + 1j * rng.normal(size=(64, 64))
    touched = np.sort(rng.choice(observed.size, size=400, replace=False)).astype(np.int32)
    source_pixels = 18
    result = positive_support_reconstruction(observed, touched, source_pixels, iterations=7)
    reference = literal_reconstruction(observed, touched, source_pixels, 7)
    reference_error = float(np.max(np.abs(result - reference)))
    if reference_error > 2e-7:
        raise AssertionError(f"reconstruction literal-reference error {reference_error:.3e}")
    support = central_support_mask(observed.shape, source_pixels)
    outside_error = float(np.max(np.abs(result[~support])))
    negative_error = max(0.0, -float(result.min()))
    if outside_error != 0.0 or negative_error != 0.0:
        raise AssertionError("reconstruction failed positivity/support constraints")
    return reference_error, outside_error, negative_error


def science_end_to_end() -> tuple[np.ndarray, np.ndarray, np.ndarray, float, float]:
    rgb = synthetic_rgb()
    processed = science_preprocess(rgb)
    source_pixels = source_pixels_for_spec(SCIENCE_SPEC)
    sky = embed_preprocessed_source(
        processed,
        (SCIENCE_SPEC.npix, SCIENCE_SPEC.npix),
        (source_pixels, source_pixels),
        total_flux=1.0,
    )
    source_ft = centered_fft2(sky)
    operator = load_frozen_operator("AA2", "6h", "science")
    observed = operator.grid(source_ft, cell_normalized=True)
    restored = positive_support_reconstruction(
        observed,
        operator.touched,
        source_pixels,
        iterations=SCIENCE_RECONSTRUCTION_ITERATIONS,
    )
    reference = literal_reconstruction(
        observed,
        operator.touched,
        source_pixels,
        SCIENCE_RECONSTRUCTION_ITERATIONS,
    )
    reference_error = float(np.max(np.abs(restored - reference)))
    support = central_support_mask(restored.shape, source_pixels)
    outside_error = float(np.max(np.abs(restored[~support])))
    if reference_error > 2e-6 or outside_error != 0.0 or float(restored.min()) < 0.0:
        raise AssertionError(
            f"science end-to-end constraints/reference failed: ref={reference_error:.3e}, outside={outside_error:.3e}"
        )
    return sky, observed, restored, reference_error, outside_error


def centre_crop(array: np.ndarray, size: int) -> np.ndarray:
    centre = array.shape[0] // 2
    half = size // 2
    return array[centre - half : centre + half, centre - half : centre + half]


def symmetric_display(array: np.ndarray) -> np.ndarray:
    limit = np.percentile(np.abs(array), 99.5) + 1e-30
    return np.clip((array / limit + 1.0) / 2.0, 0.0, 1.0)


def positive_display(array: np.ndarray) -> np.ndarray:
    low, high = np.percentile(array, [0.5, 99.5])
    return np.clip((array - low) / (high - low + 1e-30), 0.0, 1.0)


def write_plots(output_dir: Path, science_products: tuple[np.ndarray, np.ndarray, np.ndarray, float, float]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rgb = synthetic_rgb()
    processed = robust_preprocess(rgb)
    source_pixels = source_pixels_for_spec(OUTREACH_SPEC)
    sky = embed_preprocessed_source(
        processed,
        (OUTREACH_SPEC.npix, OUTREACH_SPEC.npix),
        (source_pixels, source_pixels),
        total_flux=1.0,
    )
    source_ft = centered_fft2(sky)
    crop_size = 178
    sequence = [
        ("AA1", "snapshot", "AA1 snapshot"),
        ("AA1", "6h", "AA1 + 6 h"),
        ("AA2", "6h", "AA2 + 6 h"),
        ("AA*", "6h", "AA* + 6 h"),
        ("AA4", "6h", "AA4 + 6 h"),
    ]
    fig, axes = plt.subplots(1, len(sequence) + 1, figsize=(16.0, 3.2), constrained_layout=True)
    axes[0].imshow(positive_display(centre_crop(sky, crop_size)), origin="lower", cmap="magma")
    axes[0].set_title("Artificial source")
    for ax, (stage, duration, title) in zip(axes[1:], sequence, strict=True):
        dirty = load_frozen_operator(stage, duration, "outreach").dirty_image(source_ft)
        ax.imshow(symmetric_display(centre_crop(dirty, crop_size)), origin="lower", cmap="magma")
        ax.set_title(title)
    for ax in axes:
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle("Frozen Outreach operators: build the SKA progression")
    fig.savefig(output_dir / "outreach_operator_progression.png", dpi=220)
    plt.close(fig)

    science_sky, observed, restored, _, _ = science_products
    inverse = np.real(centered_ifft2(observed))
    science_crop = 190
    fig, axes = plt.subplots(1, 4, figsize=(11.0, 3.2), constrained_layout=True)
    fourier_display = np.log10(1.0 + np.abs(observed))
    fourier_scale = np.percentile(fourier_display[fourier_display > 0.0], 99.5)
    fourier_display = np.clip(fourier_display / (fourier_scale + 1e-30), 0.0, 1.0)
    panels = [
        (positive_display(centre_crop(science_sky, science_crop)), "Artificial source"),
        (fourier_display, "Observed Fourier magnitude"),
        (symmetric_display(centre_crop(inverse, science_crop)), "Zero-filled inverse FFT"),
        (positive_display(centre_crop(restored, science_crop)), "20-iteration reconstruction"),
    ]
    for ax, (data, title) in zip(axes, panels, strict=True):
        ax.imshow(data, origin="lower", cmap="magma")
        ax.set_title(title)
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle("Optional Science image: AA2, six-hour sampling")
    fig.savefig(output_dir / "science_reconstruction.png", dpi=220)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("build/operator-validation"),
        help="Directory for ignored validation products",
    )
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()

    asset_count, equal_sum_error, science_weight_error = validate_manifests_and_assets()
    coeff_error, reproduced_weight_error, reproduced = reproduce_operator_arrays()
    preprocess_error, flux_error, outreach_pixels, science_pixels = validate_science_preprocess_and_embedding()
    manual_error, point_error, dirty_error = validate_operator_application()
    reconstruction_error, outside_error, negative_error = validate_reconstruction()
    science_products = science_end_to_end()

    if not args.no_plots:
        write_plots(args.output / "plots", science_products)
        print(f"Wrote validation plots to {args.output / 'plots'}")

    print(
        f"PASS frozen assets: {asset_count} archives, max equal-cell coefficient-sum error "
        f"{equal_sum_error:.3e}, natural-weight closure {science_weight_error:.3e} relative"
    )
    print(
        f"PASS operator reproduction: {reproduced} operators, max coefficient relative error "
        f"{coeff_error:.3e}, max Science total-weight relative error {reproduced_weight_error:.3e}"
    )
    print(
        f"PASS Science preprocessing/source embedding: reference {preprocess_error:.3e}, "
        f"flux {flux_error:.3e}, source pixels Outreach={outreach_pixels}, Science={science_pixels}"
    )
    print(
        f"PASS sparse application: manual {manual_error:.3e}, point response {point_error:.3e}, "
        f"dirty-centre normalization {dirty_error:.3e}"
    )
    print(
        f"PASS constrained reconstruction: literal reference {reconstruction_error:.3e}, "
        f"outside-support {outside_error:.3e}, negativity {negative_error:.3e}"
    )
    print(
        f"PASS Science end-to-end: literal reference {science_products[3]:.3e}, "
        f"outside-support {science_products[4]:.3e}"
    )
    print("PASS SKAetch frozen operators and reconstruction")


if __name__ == "__main__":
    main()
