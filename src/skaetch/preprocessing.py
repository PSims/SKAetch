"""Deterministic preprocessing for artificial radio-source images."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter
from skimage import color, exposure, transform

LOW_PERCENTILE = 2.0
HIGH_PERCENTILE = 98.0
GAUSSIAN_SIGMA_PIXELS = 0.6
CLAHE_CLIP_LIMIT = 0.012
CLAHE_BLEND = 0.35
CLAHE_NBINS = 256
TAPER_INNER_FRACTION = 0.86


def _shape_pair(shape, name: str) -> tuple[int, int]:
    if len(shape) != 2:
        raise ValueError(f"{name} must contain exactly two dimensions")
    result = (int(shape[0]), int(shape[1]))
    if result[0] < 2 or result[1] < 2:
        raise ValueError(f"{name} dimensions must both be at least 2")
    return result


def centre_square_crop(image) -> np.ndarray:
    """Return the largest centred square crop without changing channel count."""
    image = np.asarray(image)
    if image.ndim not in (2, 3):
        raise ValueError("image must be greyscale, RGB, or RGBA")
    height, width = image.shape[:2]
    if height < 2 or width < 2:
        raise ValueError("image dimensions must both be at least 2 pixels")
    side = min(height, width)
    y0 = (height - side) // 2
    x0 = (width - side) // 2
    return image[y0 : y0 + side, x0 : x0 + side]


def _luminance(image) -> np.ndarray:
    """Convert greyscale/RGB/RGBA input to floating-point luminance."""
    image = np.asarray(image)
    if image.ndim == 2:
        grey = np.asarray(image, dtype=float)
    elif image.ndim == 3 and image.shape[2] in (3, 4):
        # Alpha is intentionally not used as a brightness multiplier. Camera
        # and decoded-image RGBA inputs are treated by their RGB content.
        grey = color.rgb2gray(image[..., :3])
    else:
        raise ValueError("image must be greyscale, RGB, or RGBA")
    if np.any(~np.isfinite(grey)):
        raise ValueError("image must contain only finite values")
    return np.asarray(grey, dtype=float)


def _clahe_kernel(shape: tuple[int, int]) -> int:
    """Return the deterministic local-contrast scale used by SKAetch."""
    return max(16, min(64, int(min(shape) / 8)))


def robust_preprocess(image) -> np.ndarray:
    """Centre-crop, denoise, robustly normalise, and enhance an input image.

    Processing is deterministic and accepts greyscale, RGB, or RGBA arrays.
    The returned floating-point square image lies in ``[0, 1]``.  Resizing into
    the artificial radio-source representation is handled separately by
    ``artificial_radio_source()``.
    """
    cropped = centre_square_crop(image)
    grey = _luminance(cropped)
    denoised = gaussian_filter(grey, sigma=GAUSSIAN_SIGMA_PIXELS)

    low, high = np.percentile(denoised, (LOW_PERCENTILE, HIGH_PERCENTILE))
    if high - low > 1e-6:
        normalised = np.clip((denoised - low) / (high - low), 0.0, 1.0)
    else:
        normalised = np.clip(denoised, 0.0, 1.0)

    local = exposure.equalize_adapthist(
        normalised,
        kernel_size=_clahe_kernel(normalised.shape),
        clip_limit=CLAHE_CLIP_LIMIT,
        nbins=CLAHE_NBINS,
    )
    result = (1.0 - CLAHE_BLEND) * normalised + CLAHE_BLEND * local
    return np.clip(np.asarray(result, dtype=float), 0.0, 1.0)


def science_preprocess(image) -> np.ndarray:
    """Centre-crop and percentile-normalise an image without local enhancement.

    This intentionally lighter preprocessing is used by the optional idealised
    science reconstruction. It preserves the mature exhibit convention: RGB
    and RGBA inputs are converted to luminance, then the 1st and 99th
    percentiles are mapped to ``[0, 1]``.
    """
    cropped = centre_square_crop(image)
    grey = _luminance(cropped)
    low, high = np.percentile(grey, (1.0, 99.0))
    if high - low > 1e-6:
        return np.clip((grey - low) / (high - low), 0.0, 1.0)
    return np.clip(grey, 0.0, 1.0)


def cosine_edge_taper(
    shape: tuple[int, int],
    inner_fraction: float = TAPER_INNER_FRACTION,
) -> np.ndarray:
    """Return the deterministic box-radius cosine taper used for source edges.

    Coordinates on each image axis run from -1 to +1.  The taper is unity while
    ``max(|x|, |y|) <= inner_fraction``, falls with a half-cosine outside that
    box, and reaches zero at the outer boundary.
    """
    n_y, n_x = _shape_pair(shape, "shape")
    inner_fraction = float(inner_fraction)
    if not np.isfinite(inner_fraction) or not 0.0 <= inner_fraction < 1.0:
        raise ValueError("inner_fraction must lie in [0, 1)")

    y = np.linspace(-1.0, 1.0, n_y)
    x = np.linspace(-1.0, 1.0, n_x)
    radius = np.maximum(np.abs(y)[:, None], np.abs(x)[None, :])
    taper = np.ones((n_y, n_x), dtype=float)
    edge = radius > inner_fraction
    taper[edge] = 0.5 * (
        1.0
        + np.cos(
            np.pi
            * (radius[edge] - inner_fraction)
            / (1.0 - inner_fraction)
        )
    )
    taper[radius >= 1.0] = 0.0
    return taper


def embed_preprocessed_source(
    processed,
    sky_shape: tuple[int, int],
    source_shape: tuple[int, int],
    *,
    total_flux: float = 1.0,
    taper_inner_fraction: float = TAPER_INNER_FRACTION,
) -> np.ndarray:
    """Resize, taper, flux-normalise, and centre an already processed source."""
    sky_shape = _shape_pair(sky_shape, "sky_shape")
    source_shape = _shape_pair(source_shape, "source_shape")
    if source_shape[0] > sky_shape[0] or source_shape[1] > sky_shape[1]:
        raise ValueError("source_shape must fit inside sky_shape")

    processed = np.asarray(processed, dtype=float)
    if processed.ndim != 2 or np.any(~np.isfinite(processed)):
        raise ValueError("processed must be a finite two-dimensional array")

    total_flux = float(total_flux)
    if not np.isfinite(total_flux) or total_flux <= 0.0:
        raise ValueError("total_flux must be finite and positive")

    source = transform.resize(
        processed,
        source_shape,
        anti_aliasing=True,
    )
    source = np.asarray(source, dtype=float)
    source *= cosine_edge_taper(
        source_shape,
        inner_fraction=taper_inner_fraction,
    )

    flux = float(np.sum(source))
    if not np.isfinite(flux) or flux <= np.finfo(float).tiny:
        raise ValueError("artificial source has no positive finite flux after preprocessing")
    source *= total_flux / flux

    sky = np.zeros(sky_shape, dtype=float)
    # Align the source's central pixel with the sky's FFT-origin pixel.  This
    # matters when an even-sized sky contains an odd-sized source cutout.
    y0 = sky_shape[0] // 2 - source_shape[0] // 2
    x0 = sky_shape[1] // 2 - source_shape[1] // 2
    sky[y0 : y0 + source_shape[0], x0 : x0 + source_shape[1]] = source
    return sky


def artificial_radio_source(
    image,
    sky_shape: tuple[int, int],
    source_shape: tuple[int, int],
    *,
    total_flux: float = 1.0,
    taper_inner_fraction: float = TAPER_INNER_FRACTION,
) -> np.ndarray:
    """Embed a robustly preprocessed artificial radio source in a larger sky."""
    return embed_preprocessed_source(
        robust_preprocess(image),
        sky_shape,
        source_shape,
        total_flux=total_flux,
        taper_inner_fraction=taper_inner_fraction,
    )
