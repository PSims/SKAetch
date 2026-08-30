"""Fourier-plane sampling, bilinear gridding, and dirty imaging."""

from __future__ import annotations

from typing import Literal

import numpy as np

Weighting = Literal["natural", "equal-cell"]


def centered_fft2(image) -> np.ndarray:
    """Return a centred two-dimensional Fourier transform.

    The input image is interpreted with its origin at the central pixel.  The
    returned Fourier grid has zero spatial frequency at its central pixel.
    NumPy's unnormalised forward-transform convention is retained, so the
    central Fourier value equals the sum of the image pixels.
    """
    image = np.asarray(image)
    if image.ndim != 2:
        raise ValueError("image must be a two-dimensional array")
    if np.any(~np.isfinite(image)):
        raise ValueError("image must contain only finite values")
    return np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(image)))


def centered_ifft2(fourier_grid) -> np.ndarray:
    """Invert ``centered_fft2`` while keeping the image origin centred."""
    fourier_grid = np.asarray(fourier_grid)
    if fourier_grid.ndim != 2:
        raise ValueError("fourier_grid must be a two-dimensional array")
    if np.any(~np.isfinite(fourier_grid)):
        raise ValueError("fourier_grid must contain only finite values")
    return np.fft.fftshift(np.fft.ifft2(np.fft.ifftshift(fourier_grid)))


def fourier_axes_lambda(
    shape: tuple[int, int],
    field_of_view_rad: float | tuple[float, float],
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(u, v)`` axes in wavelengths for a small-angle image grid.

    ``shape`` is ``(n_y, n_x)``.  ``field_of_view_rad`` may be a scalar or
    ``(fov_y, fov_x)``.  Image pixels are treated as uniformly spaced direction
    cosines over the requested angular extent, giving Fourier coordinates in
    cycles per radian, numerically equivalent to wavelengths for the usual
    small-field interferometric transform.
    """
    if len(shape) != 2:
        raise ValueError("shape must contain exactly two dimensions")
    n_y, n_x = (int(shape[0]), int(shape[1]))
    if n_y < 2 or n_x < 2:
        raise ValueError("both Fourier-grid dimensions must be at least 2")

    if np.isscalar(field_of_view_rad):
        fov_y = fov_x = float(field_of_view_rad)
    else:
        if len(field_of_view_rad) != 2:
            raise ValueError("field_of_view_rad must be a scalar or (fov_y, fov_x)")
        fov_y, fov_x = (float(field_of_view_rad[0]), float(field_of_view_rad[1]))
    if not np.isfinite(fov_y) or not np.isfinite(fov_x) or fov_y <= 0.0 or fov_x <= 0.0:
        raise ValueError("field_of_view_rad values must be finite and positive")

    v_axis = np.fft.fftshift(np.fft.fftfreq(n_y, d=fov_y / n_y))
    u_axis = np.fft.fftshift(np.fft.fftfreq(n_x, d=fov_x / n_x))
    return u_axis, v_axis


def _validate_axis(axis, expected_size: int, name: str) -> np.ndarray:
    axis = np.asarray(axis, dtype=float)
    if axis.ndim != 1 or len(axis) != expected_size:
        raise ValueError(f"{name} must be one-dimensional with length {expected_size}")
    if np.any(~np.isfinite(axis)) or np.any(np.diff(axis) <= 0.0):
        raise ValueError(f"{name} must contain finite, strictly increasing values")
    return axis


def _bilinear_coordinates(axis: np.ndarray, values: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return lower indices, fractional offsets, and an inclusive-domain mask."""
    valid = np.isfinite(values) & (values >= axis[0]) & (values <= axis[-1])
    lower = np.searchsorted(axis, values, side="right") - 1
    lower = np.clip(lower, 0, len(axis) - 2)
    denominator = axis[lower + 1] - axis[lower]
    fraction = (values - axis[lower]) / denominator
    fraction = np.clip(fraction, 0.0, 1.0)
    return lower.astype(np.int64, copy=False), fraction, valid


def bilinear_sample_fourier_grid(
    fourier_grid,
    u_lambda,
    v_lambda,
    u_axis_lambda,
    v_axis_lambda,
    *,
    fill_value: complex = 0.0j,
) -> tuple[np.ndarray, np.ndarray]:
    """Sample a complex Fourier grid bilinearly at continuous ``(u, v)`` positions.

    The first Fourier-grid axis is ``v`` and the second is ``u``.  Samples on
    the inclusive boundary are accepted.  Values outside the grid receive
    ``fill_value`` and are marked false in the returned validity mask.
    """
    grid = np.asarray(fourier_grid)
    if grid.ndim != 2:
        raise ValueError("fourier_grid must be a two-dimensional array")
    if np.any(~np.isfinite(grid)):
        raise ValueError("fourier_grid must contain only finite values")
    u_axis = _validate_axis(u_axis_lambda, grid.shape[1], "u_axis_lambda")
    v_axis = _validate_axis(v_axis_lambda, grid.shape[0], "v_axis_lambda")

    u, v = np.broadcast_arrays(np.asarray(u_lambda, dtype=float), np.asarray(v_lambda, dtype=float))
    original_shape = u.shape
    u_flat = u.reshape(-1)
    v_flat = v.reshape(-1)

    i_u, f_u, valid_u = _bilinear_coordinates(u_axis, u_flat)
    i_v, f_v, valid_v = _bilinear_coordinates(v_axis, v_flat)
    valid = valid_u & valid_v

    w00 = (1.0 - f_u) * (1.0 - f_v)
    w10 = f_u * (1.0 - f_v)
    w01 = (1.0 - f_u) * f_v
    w11 = f_u * f_v

    sampled = (
        w00 * grid[i_v, i_u]
        + w10 * grid[i_v, i_u + 1]
        + w01 * grid[i_v + 1, i_u]
        + w11 * grid[i_v + 1, i_u + 1]
    ).astype(np.result_type(grid.dtype, complex), copy=False)
    if np.any(~valid):
        sampled = sampled.copy()
        sampled[~valid] = fill_value
    return sampled.reshape(original_shape), valid.reshape(original_shape)


def _accumulate_cic(
    accumulated: np.ndarray,
    density: np.ndarray,
    u: np.ndarray,
    v: np.ndarray,
    values: np.ndarray,
    u_axis: np.ndarray,
    v_axis: np.ndarray,
) -> int:
    i_u, f_u, valid_u = _bilinear_coordinates(u_axis, u)
    i_v, f_v, valid_v = _bilinear_coordinates(v_axis, v)
    valid = valid_u & valid_v & np.isfinite(values.real) & np.isfinite(values.imag)
    if not np.any(valid):
        return 0

    i_u = i_u[valid]
    i_v = i_v[valid]
    f_u = f_u[valid]
    f_v = f_v[valid]
    values = values[valid]

    weights = (
        (1.0 - f_u) * (1.0 - f_v),
        f_u * (1.0 - f_v),
        (1.0 - f_u) * f_v,
        f_u * f_v,
    )
    targets = (
        (i_v, i_u),
        (i_v, i_u + 1),
        (i_v + 1, i_u),
        (i_v + 1, i_u + 1),
    )
    for weight, target in zip(weights, targets, strict=True):
        np.add.at(accumulated, target, weight * values)
        np.add.at(density, target, weight)
    return int(np.count_nonzero(valid))


def cloud_in_cell_grid(
    u_lambda,
    v_lambda,
    visibilities,
    u_axis_lambda,
    v_axis_lambda,
    *,
    include_conjugates: bool = False,
    clear_fourier_origin: bool = True,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Grid continuous visibility samples by four-cell cloud-in-cell accumulation.

    Each accepted sample contributes a total sampling weight of one, split
    bilinearly among its four neighbouring Fourier cells.  The returned arrays
    are the complex visibility sum and the real sampling-density sum.

    If ``include_conjugates`` is true, each accepted physical sample is also
    accumulated at ``(-u, -v)`` with its complex-conjugate visibility.  The
    returned count records accepted gridded points, so it includes accepted
    conjugate points when requested.

    By default, the exact Fourier-origin cell is cleared after accumulation.
    SKAetch does not retain a gridded DC/zero-spacing coefficient in its
    artificial interferometric imaging convention.  Set
    ``clear_fourier_origin=False`` for diagnostic weight-conservation tests.
    """
    u_axis = np.asarray(u_axis_lambda, dtype=float)
    v_axis = np.asarray(v_axis_lambda, dtype=float)
    if u_axis.ndim != 1 or len(u_axis) < 2:
        raise ValueError("u_axis_lambda must be a one-dimensional axis of length at least 2")
    if v_axis.ndim != 1 or len(v_axis) < 2:
        raise ValueError("v_axis_lambda must be a one-dimensional axis of length at least 2")
    _validate_axis(u_axis, len(u_axis), "u_axis_lambda")
    _validate_axis(v_axis, len(v_axis), "v_axis_lambda")

    u, v, values = np.broadcast_arrays(
        np.asarray(u_lambda, dtype=float),
        np.asarray(v_lambda, dtype=float),
        np.asarray(visibilities, dtype=complex),
    )
    u = u.reshape(-1)
    v = v.reshape(-1)
    values = values.reshape(-1)

    accumulated = np.zeros((len(v_axis), len(u_axis)), dtype=complex)
    density = np.zeros((len(v_axis), len(u_axis)), dtype=float)
    accepted = _accumulate_cic(accumulated, density, u, v, values, u_axis, v_axis)
    if include_conjugates:
        accepted += _accumulate_cic(
            accumulated,
            density,
            -u,
            -v,
            np.conjugate(values),
            u_axis,
            v_axis,
        )

    if clear_fourier_origin:
        u_zero = np.flatnonzero(u_axis == 0.0)
        v_zero = np.flatnonzero(v_axis == 0.0)
        if len(u_zero) == 1 and len(v_zero) == 1:
            origin = (int(v_zero[0]), int(u_zero[0]))
            accumulated[origin] = 0.0j
            density[origin] = 0.0

    return accumulated, density, accepted


def apply_imaging_weighting(
    accumulated_visibilities,
    sampling_density,
    weighting: Weighting,
) -> tuple[np.ndarray, np.ndarray]:
    """Return weighted Fourier values and the corresponding PSF-weight grid.

    ``natural`` retains the cloud-in-cell accumulation, so multiply sampled
    cells carry proportionally more weight.  ``equal-cell`` first divides each
    occupied cell by its accumulated sampling density and then assigns every
    occupied cell unit imaging weight.
    """
    accumulated = np.asarray(accumulated_visibilities, dtype=complex)
    density = np.asarray(sampling_density, dtype=float)
    if accumulated.shape != density.shape or accumulated.ndim != 2:
        raise ValueError("accumulated_visibilities and sampling_density must be matching 2-D arrays")
    if np.any(~np.isfinite(accumulated)) or np.any(~np.isfinite(density)) or np.any(density < 0.0):
        raise ValueError("gridded inputs must be finite and sampling density non-negative")

    if weighting == "natural":
        return accumulated.copy(), density.copy()
    if weighting == "equal-cell":
        occupied = density > 0.0
        weighted = np.zeros_like(accumulated)
        weighted[occupied] = accumulated[occupied] / density[occupied]
        return weighted, occupied.astype(float)
    raise ValueError("weighting must be 'natural' or 'equal-cell'")


def dirty_image_and_psf(
    accumulated_visibilities,
    sampling_density,
    weighting: Weighting,
) -> tuple[np.ndarray, np.ndarray]:
    """Form a PSF-peak-normalised dirty image and point-spread function.

    The same Fourier convention is used for both products.  Dividing by the
    central PSF value gives unit response at the image centre for a unit-flux
    point source under either weighting scheme.  Complex values are retained;
    for Hermitian visibility grids the imaginary components are round-off only.
    """
    weighted_visibilities, psf_weights = apply_imaging_weighting(
        accumulated_visibilities,
        sampling_density,
        weighting,
    )
    if not np.any(psf_weights > 0.0):
        raise ValueError("cannot form an image from an empty sampling grid")

    dirty = centered_ifft2(weighted_visibilities)
    psf = centered_ifft2(psf_weights)
    centre = (psf.shape[0] // 2, psf.shape[1] // 2)
    psf_peak = psf[centre]
    if not np.isfinite(psf_peak) or abs(psf_peak) <= np.finfo(float).tiny:
        raise ValueError("PSF central response is zero or non-finite")
    return dirty / psf_peak, psf / psf_peak
