#!/usr/bin/env python3
"""Validate deterministic SKAetch artificial-source preprocessing."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import gaussian_filter
from skimage import color, exposure, transform

from skaetch.preprocessing import (
    CLAHE_BLEND,
    CLAHE_CLIP_LIMIT,
    GAUSSIAN_SIGMA_PIXELS,
    TAPER_INNER_FRACTION,
    artificial_radio_source,
    centre_square_crop,
    cosine_edge_taper,
    robust_preprocess,
)

ATOL = 5e-12


def synthetic_rgb(height: int = 83, width: int = 127) -> np.ndarray:
    y, x = np.indices((height, width), dtype=float)
    x /= max(width - 1, 1)
    y /= max(height - 1, 1)
    rgb = np.empty((height, width, 3), dtype=float)
    rgb[..., 0] = 0.15 + 0.75 * x
    rgb[..., 1] = 0.10 + 0.65 * y
    rgb[..., 2] = 0.20 + 0.45 * np.exp(-((x - 0.55) ** 2 + (y - 0.45) ** 2) / 0.03)
    return np.clip(rgb, 0.0, 1.0)


def _assert_contract(name: str, result: np.ndarray, expected_shape: tuple[int, int]) -> None:
    if result.shape != expected_shape:
        raise AssertionError(f"{name}: shape {result.shape} != {expected_shape}")
    if not np.all(np.isfinite(result)):
        raise AssertionError(f"{name}: non-finite output")
    if float(result.min()) < -ATOL or float(result.max()) > 1.0 + ATOL:
        raise AssertionError(f"{name}: output escaped [0, 1]")


def literal_reference_preprocess(image) -> np.ndarray:
    """Separately express the preprocessing specification for numeric comparison."""
    image = np.asarray(image)
    h, w = image.shape[:2]
    side = min(h, w)
    y0 = (h - side) // 2
    x0 = (w - side) // 2
    image = image[y0 : y0 + side, x0 : x0 + side]

    if image.ndim == 2:
        grey = np.asarray(image, dtype=float)
    elif image.ndim == 3 and image.shape[2] in (3, 4):
        grey = color.rgb2gray(image[..., :3])
    else:
        raise ValueError("reference input must be greyscale, RGB, or RGBA")

    grey = gaussian_filter(grey, sigma=0.6)
    p2, p98 = np.percentile(grey, [2, 98])
    if p98 - p2 > 1e-6:
        normalised = np.clip((grey - p2) / (p98 - p2), 0.0, 1.0)
    else:
        normalised = np.clip(grey, 0.0, 1.0)

    kernel = max(16, min(64, int(min(normalised.shape) / 8)))
    local = exposure.equalize_adapthist(
        normalised,
        kernel_size=kernel,
        clip_limit=0.012,
        nbins=256,
    )
    return np.clip(0.65 * normalised + 0.35 * local, 0.0, 1.0)


def literal_reference_taper(shape: tuple[int, int]) -> np.ndarray:
    y = np.linspace(-1.0, 1.0, shape[0])
    x = np.linspace(-1.0, 1.0, shape[1])
    radius = np.maximum(np.abs(y)[:, None], np.abs(x)[None, :])
    taper = np.ones(shape, dtype=float)
    edge = radius > 0.86
    taper[edge] = 0.5 * (
        1.0 + np.cos(np.pi * (radius[edge] - 0.86) / (1.0 - 0.86))
    )
    taper[radius >= 1.0] = 0.0
    return taper


def validate_reference_constants() -> None:
    expected = {
        "sigma": (GAUSSIAN_SIGMA_PIXELS, 0.6),
        "clip_limit": (CLAHE_CLIP_LIMIT, 0.012),
        "blend": (CLAHE_BLEND, 0.35),
        "taper_inner_fraction": (TAPER_INNER_FRACTION, 0.86),
    }
    for name, (actual, target) in expected.items():
        if actual != target:
            raise AssertionError(f"{name}: {actual!r} != {target!r}")


def validate_input_forms() -> tuple[float, float, float, float]:
    rgb = synthetic_rgb()
    grey = 0.2125 * rgb[..., 0] + 0.7154 * rgb[..., 1] + 0.0721 * rgb[..., 2]
    rgba = np.dstack((rgb, np.ones(rgb.shape[:2])))
    rgba[..., 3] = np.linspace(0.0, 1.0, rgba.shape[1])[None, :]

    grey_result = robust_preprocess(grey)
    rgb_result = robust_preprocess(rgb)
    rgba_result = robust_preprocess(rgba)
    for name, result in (("greyscale", grey_result), ("RGB", rgb_result), ("RGBA", rgba_result)):
        _assert_contract(name, result, (83, 83))

    rgb_rgba_error = float(np.max(np.abs(rgb_result - rgba_result)))
    if rgb_rgba_error > ATOL:
        raise AssertionError(f"RGB/RGBA mismatch {rgb_rgba_error:.3e}; alpha should not modulate brightness")

    grey_rgb_error = float(np.max(np.abs(grey_result - rgb_result)))
    if grey_rgb_error > 2e-11:
        raise AssertionError(f"greyscale/RGB luminance mismatch {grey_rgb_error:.3e}")

    repeat_error = float(np.max(np.abs(rgb_result - robust_preprocess(rgb))))
    if repeat_error != 0.0:
        raise AssertionError(f"preprocessing is not deterministic; repeat error {repeat_error:.3e}")

    reference_error = float(np.max(np.abs(rgb_result - literal_reference_preprocess(rgb))))
    if reference_error > ATOL:
        raise AssertionError(f"literal preprocessing-reference error {reference_error:.3e}")
    return rgb_rgba_error, grey_rgb_error, repeat_error, reference_error


def validate_centre_crop_first() -> float:
    core = synthetic_rgb(60, 60)
    padded = np.zeros((60, 100, 3), dtype=float)
    padded[:, 20:80] = core
    padded[:, :20, 0] = 1.0
    padded[:, 80:, 2] = 1.0

    cropped = centre_square_crop(padded)
    if not np.array_equal(cropped, core):
        raise AssertionError("centre_square_crop did not recover the expected central square")
    direct = robust_preprocess(core)
    padded_result = robust_preprocess(padded)
    crop_order_error = float(np.max(np.abs(direct - padded_result)))
    if crop_order_error > ATOL:
        raise AssertionError(f"centre-crop-first preprocessing error {crop_order_error:.3e}")
    return crop_order_error


def validate_contrast_and_constant_cases() -> tuple[float, float]:
    y, x = np.indices((72, 72), dtype=float)
    low_contrast = 0.5 + 2e-3 * np.sin(x / 7.0) * np.cos(y / 9.0)
    low = robust_preprocess(low_contrast)
    _assert_contract("low contrast", low, (72, 72))
    low_span = float(np.ptp(low))
    if low_span < 0.5:
        raise AssertionError(f"robust normalisation did not recover low contrast; span {low_span:.3f}")

    max_reference_error = 0.0
    for name, image in (
        ("constant dark", np.zeros((50, 90))),
        ("constant mid-grey", np.full((50, 90), 0.4)),
        ("nearly constant", np.full((50, 90), 0.4)),
    ):
        if name == "nearly constant":
            image = image.copy()
            image[25, 45] += 1e-14
        result = robust_preprocess(image)
        _assert_contract(name, result, (50, 50))
        reference = literal_reference_preprocess(image)
        error = float(np.max(np.abs(result - reference)))
        max_reference_error = max(max_reference_error, error)
        if error > ATOL:
            raise AssertionError(f"{name}: literal reference error {error:.3e}")
    return low_span, max_reference_error


def validate_taper_and_source_embedding() -> tuple[float, float, float, float]:
    shape = (48, 40)
    taper = cosine_edge_taper(shape)
    reference_taper = literal_reference_taper(shape)
    taper_reference_error = float(np.max(np.abs(taper - reference_taper)))
    if taper_reference_error > ATOL:
        raise AssertionError(f"cosine-taper reference error {taper_reference_error:.3e}")
    if taper.min() < 0.0 or taper.max() > 1.0 + ATOL:
        raise AssertionError("cosine taper escaped [0, 1]")
    edge_max = max(
        float(taper[0].max()),
        float(taper[-1].max()),
        float(taper[:, 0].max()),
        float(taper[:, -1].max()),
    )
    if edge_max > ATOL:
        raise AssertionError(f"cosine taper does not reach zero at the edge; max edge {edge_max:.3e}")

    total_flux = 7.25
    rgb = synthetic_rgb()
    source_shape = (72, 64)
    source = artificial_radio_source(
        rgb,
        sky_shape=(128, 144),
        source_shape=source_shape,
        total_flux=total_flux,
    )
    if source.shape != (128, 144) or not np.all(np.isfinite(source)):
        raise AssertionError("artificial source has invalid output contract")
    flux_error = abs(float(source.sum()) - total_flux)
    if flux_error > 2e-12:
        raise AssertionError(f"artificial-source total-flux error {flux_error:.3e}")

    processed = literal_reference_preprocess(rgb)
    reference_cutout = transform.resize(processed, source_shape, anti_aliasing=True)
    reference_cutout *= literal_reference_taper(source_shape)
    reference_cutout *= total_flux / float(reference_cutout.sum())
    reference_sky = np.zeros((128, 144), dtype=float)
    y0 = 128 // 2 - source_shape[0] // 2
    x0 = 144 // 2 - source_shape[1] // 2
    reference_sky[y0 : y0 + source_shape[0], x0 : x0 + source_shape[1]] = reference_cutout
    source_reference_error = float(np.max(np.abs(source - reference_sky)))
    if source_reference_error > ATOL:
        raise AssertionError(f"artificial-source literal reference error {source_reference_error:.3e}")

    nonzero = np.argwhere(source > 0.0)
    centre_y = 0.5 * (nonzero[:, 0].min() + nonzero[:, 0].max())
    centre_x = 0.5 * (nonzero[:, 1].min() + nonzero[:, 1].max())
    embedding_error = max(abs(centre_y - 63.5), abs(centre_x - 71.5))
    if embedding_error > 0.5:
        raise AssertionError(f"artificial source is not centred; error {embedding_error:.3f} pixel")

    odd_shape = (73, 73)
    odd_source = artificial_radio_source(
        rgb,
        sky_shape=(128, 128),
        source_shape=odd_shape,
        total_flux=1.0,
    )
    odd_cutout = transform.resize(processed, odd_shape, anti_aliasing=True)
    odd_cutout *= literal_reference_taper(odd_shape)
    odd_cutout /= float(odd_cutout.sum())
    odd_reference = np.zeros((128, 128), dtype=float)
    odd_y0 = 128 // 2 - odd_shape[0] // 2
    odd_x0 = 128 // 2 - odd_shape[1] // 2
    odd_reference[
        odd_y0 : odd_y0 + odd_shape[0],
        odd_x0 : odd_x0 + odd_shape[1],
    ] = odd_cutout
    odd_alignment_error = float(np.max(np.abs(odd_source - odd_reference)))
    if odd_alignment_error > ATOL:
        raise AssertionError(
            f"odd-source FFT-origin alignment error {odd_alignment_error:.3e}"
        )

    dark_source = artificial_radio_source(
        np.zeros((60, 80)),
        sky_shape=(96, 96),
        source_shape=(48, 48),
        total_flux=total_flux,
    )
    dark_flux_error = abs(float(dark_source.sum()) - total_flux)
    if dark_flux_error > 2e-12:
        raise AssertionError(f"constant dark source does not retain fixed total flux; error {dark_flux_error:.3e}")

    return taper_reference_error, max(source_reference_error, odd_alignment_error), flux_error, max(embedding_error, dark_flux_error)


def write_inspection_plot(output_dir: Path) -> None:
    rgb = synthetic_rgb()
    cropped = centre_square_crop(rgb)
    preprocessed = robust_preprocess(rgb)
    source_shape = (72, 72)
    resized = transform.resize(preprocessed, source_shape, anti_aliasing=True)
    taper = cosine_edge_taper(source_shape)
    source = artificial_radio_source(
        rgb,
        sky_shape=(128, 128),
        source_shape=source_shape,
        total_flux=1.0,
    )

    fig, axes = plt.subplots(1, 6, figsize=(17.5, 3.4), constrained_layout=True)
    panels = [
        (rgb, "Input RGB"),
        (cropped, "Centre crop"),
        (preprocessed, "Robust greyscale"),
        (resized, "Resized source"),
        (taper, "Cosine taper"),
        (source, "Artificial radio source"),
    ]
    for ax, (data, title) in zip(axes, panels, strict=True):
        ax.imshow(data, origin="upper", cmap=None if data.ndim == 3 else "gray")
        ax.set_title(title)
        ax.set_xticks([])
        ax.set_yticks([])
    fig.savefig(output_dir / "preprocessing_pipeline.png", dpi=220)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("build/preprocessing-validation"),
        help="Directory for ignored visual validation products",
    )
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()

    validate_reference_constants()
    rgb_rgba_error, grey_rgb_error, repeat_error, reference_error = validate_input_forms()
    crop_error = validate_centre_crop_first()
    low_span, constant_reference_error = validate_contrast_and_constant_cases()
    taper_error, source_reference_error, flux_error, embedding_error = validate_taper_and_source_embedding()

    if not args.no_plots:
        plot_dir = args.output / "plots"
        plot_dir.mkdir(parents=True, exist_ok=True)
        write_inspection_plot(plot_dir)
        print(f"Wrote visual validation plot to {plot_dir}")

    print(
        f"PASS input forms/determinism: RGB-RGBA {rgb_rgba_error:.3e}, "
        f"greyscale-RGB {grey_rgb_error:.3e}, repeat {repeat_error:.3e}, "
        f"literal reference {reference_error:.3e}"
    )
    print(f"PASS centre crop first: error {crop_error:.3e}")
    print(
        f"PASS contrast/constant handling: low-contrast span {low_span:.3f}, "
        f"constant reference error {constant_reference_error:.3e}"
    )
    print(
        f"PASS taper/source embedding: taper reference {taper_error:.3e}, "
        f"source reference {source_reference_error:.3e}, flux error {flux_error:.3e}, "
        f"centring/fixed-flux error {embedding_error:.3e}"
    )
    print("PASS SKAetch deterministic source preprocessing")


if __name__ == "__main__":
    main()
