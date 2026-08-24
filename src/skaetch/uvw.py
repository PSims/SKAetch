"""Interferometric coordinate transforms used by SKAetch."""

from __future__ import annotations

from typing import Final

import numpy as np

C_M_S: Final[float] = 299_792_458.0
SKA_LOW_LATITUDE_DEG: Final[float] = -26.82472208


def enu_to_equatorial_xyz(
    east_m,
    north_m,
    up_m=0.0,
    *,
    latitude_rad=np.deg2rad(SKA_LOW_LATITUDE_DEG),
):
    """Rotate local ENU baseline components into equatorial Cartesian XYZ.

    Inputs may be scalars or NumPy-broadcastable arrays and are returned in the
    same length unit as the inputs. The default latitude is the SKA-Low site.
    """
    east_m = np.asarray(east_m, dtype=float)
    north_m = np.asarray(north_m, dtype=float)
    up_m = np.asarray(up_m, dtype=float)
    latitude_rad = np.asarray(latitude_rad, dtype=float)

    sin_lat = np.sin(latitude_rad)
    cos_lat = np.cos(latitude_rad)
    x_m = -sin_lat * north_m + cos_lat * up_m
    y_m = east_m
    z_m = cos_lat * north_m + sin_lat * up_m
    return x_m, y_m, z_m


def equatorial_xyz_to_uvw(
    x_m,
    y_m,
    z_m,
    hour_angle_rad,
    declination_rad,
):
    """Rotate equatorial XYZ baseline components into right-handed UVW.

    ``hour_angle_rad`` uses the astronomical convention H = LST - RA: negative
    before transit and positive after transit. W points towards the phase
    centre. Inputs may be scalars or NumPy-broadcastable arrays.
    """
    x_m = np.asarray(x_m, dtype=float)
    y_m = np.asarray(y_m, dtype=float)
    z_m = np.asarray(z_m, dtype=float)
    hour_angle_rad = np.asarray(hour_angle_rad, dtype=float)
    declination_rad = np.asarray(declination_rad, dtype=float)

    sin_h = np.sin(hour_angle_rad)
    cos_h = np.cos(hour_angle_rad)
    sin_dec = np.sin(declination_rad)
    cos_dec = np.cos(declination_rad)

    u_m = sin_h * x_m + cos_h * y_m
    v_m = (
        -sin_dec * cos_h * x_m
        + sin_dec * sin_h * y_m
        + cos_dec * z_m
    )
    w_m = (
        cos_dec * cos_h * x_m
        - cos_dec * sin_h * y_m
        + sin_dec * z_m
    )
    return u_m, v_m, w_m


def enu_baseline_to_uvw_m(
    east_m,
    north_m,
    up_m,
    hour_angle_h,
    declination_deg,
    *,
    latitude_deg=SKA_LOW_LATITUDE_DEG,
):
    """Convert an ENU baseline to UVW components in metres."""
    latitude_rad = np.deg2rad(np.asarray(latitude_deg, dtype=float))
    hour_angle_rad = np.deg2rad(np.asarray(hour_angle_h, dtype=float) * 15.0)
    declination_rad = np.deg2rad(np.asarray(declination_deg, dtype=float))
    x_m, y_m, z_m = enu_to_equatorial_xyz(
        east_m,
        north_m,
        up_m,
        latitude_rad=latitude_rad,
    )
    return equatorial_xyz_to_uvw(
        x_m,
        y_m,
        z_m,
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
    """Convert an ENU baseline to UVW components measured in wavelengths."""
    frequency_hz = np.asarray(frequency_hz, dtype=float)
    if np.any(~np.isfinite(frequency_hz)) or np.any(frequency_hz <= 0.0):
        raise ValueError("frequency_hz must contain only finite positive values")

    u_m, v_m, w_m = enu_baseline_to_uvw_m(
        east_m,
        north_m,
        up_m,
        hour_angle_h,
        declination_deg,
        latitude_deg=latitude_deg,
    )
    wavelength_m = C_M_S / frequency_hz
    return u_m / wavelength_m, v_m / wavelength_m, w_m / wavelength_m
