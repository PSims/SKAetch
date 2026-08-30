"""Idealised constrained reconstruction for the SKAetch artificial-source activity."""

from __future__ import annotations

from typing import Final

import numpy as np

from skaetch.imaging import centered_fft2, centered_ifft2

SCIENCE_RECONSTRUCTION_ITERATIONS: Final[int] = 20
SCIENCE_SUPPORT_MARGIN_PIXELS: Final[int] = 3


def central_support_mask(
    shape: tuple[int, int],
    source_pixels: int,
    *,
    margin_pixels: int = SCIENCE_SUPPORT_MARGIN_PIXELS,
) -> np.ndarray:
    """Return the square support region known for the centred artificial source."""
    if len(shape) != 2 or shape[0] != shape[1]:
        raise ValueError("shape must describe a square two-dimensional grid")
    npix = int(shape[0])
    source_pixels = int(source_pixels)
    margin_pixels = int(margin_pixels)
    if npix < 2 or source_pixels < 1 or source_pixels > npix:
        raise ValueError("source_pixels must lie between 1 and the grid size")
    if margin_pixels < 0:
        raise ValueError("margin_pixels must be non-negative")

    centre = npix // 2
    half = source_pixels // 2 + margin_pixels
    start = max(0, centre - half)
    stop = min(npix, centre + half + 1)
    support = np.zeros((npix, npix), dtype=bool)
    support[start:stop, start:stop] = True
    return support


def positive_support_reconstruction(
    observed_fourier_grid,
    touched_cells,
    source_pixels: int,
    *,
    iterations: int = SCIENCE_RECONSTRUCTION_ITERATIONS,
    margin_pixels: int = SCIENCE_SUPPORT_MARGIN_PIXELS,
) -> np.ndarray:
    """Reconstruct a non-negative source inside a known central support.

    The algorithm alternates between the image and Fourier planes. In the image
    plane it enforces positivity and the known support of the artificial source;
    in the Fourier plane it restores the measured gridded samples. These are
    deliberately strong assumptions that are valid for this controlled exhibit
    test pattern, not a generic production interferometric imaging method.
    """
    observed = np.asarray(observed_fourier_grid)
    if observed.ndim != 2 or observed.shape[0] != observed.shape[1]:
        raise ValueError("observed_fourier_grid must be a square two-dimensional array")
    if np.any(~np.isfinite(observed)):
        raise ValueError("observed_fourier_grid must contain only finite values")
    touched = np.asarray(touched_cells, dtype=np.int64)
    if touched.ndim != 1:
        raise ValueError("touched_cells must be one-dimensional")
    if np.any(touched < 0) or np.any(touched >= observed.size):
        raise ValueError("touched_cells contains an out-of-range Fourier-cell index")
    iterations = int(iterations)
    if iterations < 0:
        raise ValueError("iterations must be non-negative")

    support = central_support_mask(
        observed.shape,
        source_pixels,
        margin_pixels=margin_pixels,
    )
    current = observed.astype(np.complex64, copy=True)
    observed_flat = observed.ravel()

    for _ in range(iterations):
        image = np.real(centered_ifft2(current))
        image = np.maximum(image, 0.0)
        image[~support] = 0.0
        estimate = centered_fft2(image).astype(np.complex64)
        estimate.ravel()[touched] = observed_flat[touched]
        current = estimate

    image = np.real(centered_ifft2(current))
    image = np.maximum(image, 0.0)
    image[~support] = 0.0
    return image.astype(np.float32)
