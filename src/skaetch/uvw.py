"""Interferometric coordinate transforms used by SKAetch."""

from __future__ import annotations

from typing import Final

import numpy as np

C_M_S: Final[float] = 299_792_458.0
SKA_LOW_LATITUDE_DEG: Final[float] = -26.82472208


def enu_to_equatorial_xyz_m(
    east_m,
    north_m,
    up_m=0.0,
    *,
    latitude_rad=np.deg2rad(SKA_LOW_LATITUDE_DEG),
):
    """Rotate local ENU baseline components into equatorial Cartesian XYZ metres.

    Inputs may be scalars or NumPy-broadcastable arrays. The output components
    use the same length scale as the inputs; SKAetch supplies metre-valued ENU
    baselines, hence the ``_m`` suffix.
    """
    east_m = np.asarray(east_m, dtype=float)
    north_m = np.asarray(north_m, dtype=float)
    up_m = np.asarray(up_m, dtype=float)
    latitude_rad = np.asarray(latitude_rad, dtype=float)

    sin_lat = np.sin(latitude_rad)
    cos_lat = np.cos(latitude_rad)
    b_x_m = -sin_lat * north_m + cos_lat * up_m
    b_y_m = east_m
    b_z_m = cos_lat * north_m + sin_lat * up_m
    return b_x_m, b_y_m, b_z_m


def xyz_to_uvw_rotation(hour_angle_rad, declination_rad) -> np.ndarray:
    """Return the right-handed equatorial-XYZ to UVW rotation matrix.

    ``hour_angle_rad`` uses the astronomical convention H = LST - RA. Scalar
    inputs return shape ``(3, 3)``. Broadcastable array inputs return the
    broadcast shape followed by ``(3, 3)``.
    """
    hour_angle_rad, declination_rad = np.broadcast_arrays(
        np.asarray(hour_angle_rad, dtype=float),
        np.asarray(declination_rad, dtype=float),
    )

    sin_h = np.sin(hour_angle_rad)
    cos_h = np.cos(hour_angle_rad)
    sin_dec = np.sin(declination_rad)
    cos_dec = np.cos(declination_rad)
    zero = np.zeros_like(sin_h)

    row_u = np.stack((sin_h, cos_h, zero), axis=-1)
    row_v = np.stack(
        (-sin_dec * cos_h, sin_dec * sin_h, cos_dec),
        axis=-1,
    )
    row_w = np.stack(
        (cos_dec * cos_h, -cos_dec * sin_h, sin_dec),
        axis=-1,
    )
    return np.stack((row_u, row_v, row_w), axis=-2)


def equatorial_xyz_to_uvw_m(
    b_x_m,
    b_y_m,
    b_z_m,
    hour_angle_rad,
    declination_rad,
):
    """Project an equatorial XYZ baseline into source-aligned UVW metres.

    The matrix operation is ``b_uvw_m = R(H, declination) @ b_xyz_m``. Inputs
    may be scalars or NumPy-broadcastable arrays; this function performs ordinary
    elementwise broadcasting rather than a time-by-baseline outer product.
    """
    b_x_m, b_y_m, b_z_m = np.broadcast_arrays(
        np.asarray(b_x_m, dtype=float),
        np.asarray(b_y_m, dtype=float),
        np.asarray(b_z_m, dtype=float),
    )
    b_xyz_m = np.stack((b_x_m, b_y_m, b_z_m), axis=-1)
    rotation = xyz_to_uvw_rotation(hour_angle_rad, declination_rad)
    b_uvw_m = np.einsum("...ij,...j->...i", rotation, b_xyz_m)
    return b_uvw_m[..., 0], b_uvw_m[..., 1], b_uvw_m[..., 2]


def enu_baseline_to_uvw_m(
    east_m,
    north_m,
    up_m,
    hour_angle_h,
    declination_deg,
    *,
    latitude_deg=SKA_LOW_LATITUDE_DEG,
):
    """Convert an ENU baseline to source-aligned baseline components in metres."""
    latitude_rad = np.deg2rad(np.asarray(latitude_deg, dtype=float))
    hour_angle_rad = np.deg2rad(np.asarray(hour_angle_h, dtype=float) * 15.0)
    declination_rad = np.deg2rad(np.asarray(declination_deg, dtype=float))
    b_x_m, b_y_m, b_z_m = enu_to_equatorial_xyz_m(
        east_m,
        north_m,
        up_m,
        latitude_rad=latitude_rad,
    )
    return equatorial_xyz_to_uvw_m(
        b_x_m,
        b_y_m,
        b_z_m,
        hour_angle_rad,
        declination_rad,
    )


def enu_baseline_to_uvw_lambda(
    east_m,
    north_m,
    up_m,
    hour_angle_h,
    declination_deg,
    frequency_hz,
    *,
    latitude_deg=SKA_LOW_LATITUDE_DEG,
):
    """Convert an ENU baseline to dimensionless interferometric ``(u, v, w)``.

    Lowercase ``u``, ``v`` and ``w`` are reserved for projected baseline
    coordinates measured in wavelengths. The metre-valued projection is first
    computed as ``(B_U, B_V, B_W)`` and divided by ``lambda = c / frequency``.
    """
    frequency_hz = np.asarray(frequency_hz, dtype=float)
    if np.any(~np.isfinite(frequency_hz)) or np.any(frequency_hz <= 0.0):
        raise ValueError("frequency_hz must contain only finite positive values")

    b_u_m, b_v_m, b_w_m = enu_baseline_to_uvw_m(
        east_m,
        north_m,
        up_m,
        hour_angle_h,
        declination_deg,
        latitude_deg=latitude_deg,
    )
    wavelength_m = C_M_S / frequency_hz
    u_lambda = b_u_m / wavelength_m
    v_lambda = b_v_m / wavelength_m
    w_lambda = b_w_m / wavelength_m
    return u_lambda, v_lambda, w_lambda
