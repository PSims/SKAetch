"""Station-baseline construction and Earth-rotation UVW sampling."""

from __future__ import annotations

import numpy as np

from skaetch.uvw import (
    C_M_S,
    SKA_LOW_LATITUDE_DEG,
    enu_to_equatorial_xyz_m,
    xyz_to_uvw_rotation,
)


def station_baseline_pairs(n_stations: int) -> np.ndarray:
    """Return all unordered station-index pairs in deterministic upper-triangle order."""
    if isinstance(n_stations, bool) or not isinstance(n_stations, (int, np.integer)):
        raise TypeError("n_stations must be an integer")
    if n_stations < 0:
        raise ValueError("n_stations must be non-negative")
    station_1, station_2 = np.triu_indices(int(n_stations), 1)
    return np.column_stack((station_1, station_2)).astype(np.int64, copy=False)


def station_baselines_enu_m(station_coordinates_m) -> np.ndarray:
    """Construct all ``station_2 - station_1`` ENU baselines in metres.

    ``station_coordinates_m`` must have shape ``(n_stations, 2)`` for East/North
    geometry or ``(n_stations, 3)`` for East/North/Up geometry. A zero Up
    coordinate is supplied for the committed two-dimensional SKA-Low layouts.
    """
    coordinates = np.asarray(station_coordinates_m, dtype=float)
    if coordinates.ndim != 2 or coordinates.shape[1] not in (2, 3):
        raise ValueError("station_coordinates_m must have shape (n_stations, 2 or 3)")
    if np.any(~np.isfinite(coordinates)):
        raise ValueError("station_coordinates_m must contain only finite values")

    if coordinates.shape[1] == 2:
        coordinates = np.column_stack((coordinates, np.zeros(len(coordinates), dtype=float)))

    pairs = station_baseline_pairs(len(coordinates))
    if len(pairs) == 0:
        return np.empty((0, 3), dtype=float)
    return coordinates[pairs[:, 1]] - coordinates[pairs[:, 0]]


def earth_rotation_uvw_m(
    b_enu_m,
    hour_angles_h,
    declination_deg,
    *,
    latitude_deg=SKA_LOW_LATITUDE_DEG,
) -> np.ndarray:
    """Project ENU baselines over hour angle as ``(B_U, B_V, B_W)`` metres.

    The result has shape ``(n_times, n_baselines, 3)``. Physical baselines are
    first converted to equatorial XYZ metres. For every hour angle a single
    source-aligned rotation matrix is then applied to every baseline.
    """
    b_enu_m = np.asarray(b_enu_m, dtype=float)
    if b_enu_m.ndim != 2 or b_enu_m.shape[1] != 3:
        raise ValueError("b_enu_m must have shape (n_baselines, 3)")
    if np.any(~np.isfinite(b_enu_m)):
        raise ValueError("b_enu_m must contain only finite values")

    hour_angles_h = np.asarray(hour_angles_h, dtype=float)
    if hour_angles_h.ndim == 0:
        hour_angles_h = hour_angles_h.reshape(1)
    if hour_angles_h.ndim != 1 or np.any(~np.isfinite(hour_angles_h)):
        raise ValueError("hour_angles_h must be a one-dimensional finite sequence")

    declination_deg = float(declination_deg)
    latitude_deg = float(latitude_deg)
    if not np.isfinite(declination_deg):
        raise ValueError("declination_deg must be finite")
    if not np.isfinite(latitude_deg):
        raise ValueError("latitude_deg must be finite")

    b_x_m, b_y_m, b_z_m = enu_to_equatorial_xyz_m(
        b_enu_m[:, 0],
        b_enu_m[:, 1],
        b_enu_m[:, 2],
        latitude_rad=np.deg2rad(latitude_deg),
    )
    b_xyz_m = np.column_stack((b_x_m, b_y_m, b_z_m))

    rotation = xyz_to_uvw_rotation(
        np.deg2rad(hour_angles_h * 15.0),
        np.deg2rad(declination_deg),
    )
    return np.einsum("tij,bj->tbi", rotation, b_xyz_m)


def earth_rotation_uvw_lambda(
    b_enu_m,
    hour_angles_h,
    declination_deg,
    frequency_hz,
    *,
    latitude_deg=SKA_LOW_LATITUDE_DEG,
) -> np.ndarray:
    """Sample ENU baselines over hour angle as dimensionless ``(u, v, w)``.

    The metre-valued projection is computed by ``earth_rotation_uvw_m()`` and
    divided by ``lambda = c / frequency``. The result has shape
    ``(n_times, n_baselines, 3)``.
    """
    frequency_hz = float(frequency_hz)
    if not np.isfinite(frequency_hz) or frequency_hz <= 0.0:
        raise ValueError("frequency_hz must be finite and positive")

    b_uvw_m = earth_rotation_uvw_m(
        b_enu_m,
        hour_angles_h,
        declination_deg,
        latitude_deg=latitude_deg,
    )
    wavelength_m = C_M_S / frequency_hz
    return b_uvw_m / wavelength_m
