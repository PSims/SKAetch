#!/usr/bin/env python3
"""Validate SKAetch station baselines and Earth-rotation UVW sampling."""

from __future__ import annotations

import argparse
from itertools import combinations
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from skaetch.geometry import STAGES, load_station_coordinates
from skaetch.sampling import (
    earth_rotation_uvw_lambda,
    earth_rotation_uvw_m,
    station_baseline_pairs,
    station_baselines_enu_m,
)
from skaetch.uvw import C_M_S, enu_baseline_to_uvw_lambda

FREQUENCY_HZ = 150e6
DECLINATION_DEG = -26.7
HOUR_ANGLES_H = np.linspace(-3.0, 3.0, 37, dtype=float)
TRACK_TOLERANCE_LAMBDA = 1e-9
METRE_PROJECTION_TOLERANCE_M = 1e-9
FREQUENCY_SCALING_TOLERANCE = 1e-12
PLOT_BASELINE_CAP = 4_000
STAGE_SLUGS = {
    "AA0.5": "AA0p5",
    "AA1": "AA1",
    "AA2": "AA2",
    "AA*": "AAstar",
    "AA4": "AA4",
}


def maximum_abs_difference(left, right) -> float:
    left = np.asarray(left, dtype=float)
    right = np.asarray(right, dtype=float)
    if left.size == 0 and right.size == 0:
        return 0.0
    return float(np.max(np.abs(left - right)))


def validate_baseline_construction(
    stage: str,
) -> tuple[np.ndarray, int]:
    coordinates = np.asarray(load_station_coordinates(stage), dtype=float)
    pairs = station_baseline_pairs(len(coordinates))
    expected_pairs = np.asarray(list(combinations(range(len(coordinates)), 2)), dtype=np.int64)
    expected_count = len(coordinates) * (len(coordinates) - 1) // 2

    if pairs.shape != (expected_count, 2):
        raise AssertionError(
            f"{stage}: baseline-pair shape {pairs.shape} != ({expected_count}, 2)"
        )
    if not np.array_equal(pairs, expected_pairs):
        raise AssertionError(f"{stage}: baseline-pair order differs from lexicographic pairs")

    b_enu_m = station_baselines_enu_m(coordinates)
    expected_enu_m = np.column_stack(
        (
            coordinates[pairs[:, 1]] - coordinates[pairs[:, 0]],
            np.zeros(expected_count, dtype=float),
        )
    )
    if not np.array_equal(b_enu_m, expected_enu_m):
        error = maximum_abs_difference(b_enu_m, expected_enu_m)
        raise AssertionError(f"{stage}: station_2 - station_1 baseline error {error:.3e} m")

    return b_enu_m, expected_count


def validate_track_against_single_time_transform(b_enu_m: np.ndarray) -> tuple[np.ndarray, float]:
    sampled = earth_rotation_uvw_lambda(
        b_enu_m,
        HOUR_ANGLES_H,
        DECLINATION_DEG,
        FREQUENCY_HZ,
    )
    max_error = 0.0
    for time_index, hour_angle_h in enumerate(HOUR_ANGLES_H):
        reference = enu_baseline_to_uvw_lambda(
            b_enu_m[:, 0],
            b_enu_m[:, 1],
            b_enu_m[:, 2],
            hour_angle_h,
            DECLINATION_DEG,
            FREQUENCY_HZ,
        )
        reference_array = np.column_stack(reference)
        max_error = max(
            max_error,
            maximum_abs_difference(sampled[time_index], reference_array),
        )

    if max_error >= TRACK_TOLERANCE_LAMBDA:
        raise AssertionError(
            f"Earth-rotation sampling error {max_error:.3e} wavelengths exceeds "
            f"{TRACK_TOLERANCE_LAMBDA:.1e}"
        )
    return sampled, max_error


def validate_frequency_scaling(b_enu_m: np.ndarray) -> tuple[float, float]:
    sample = b_enu_m[: min(len(b_enu_m), 2048)]
    hour_angles_h = np.array([-2.5, 0.0, 1.75])
    b_uvw_m = earth_rotation_uvw_m(
        sample,
        hour_angles_h,
        DECLINATION_DEG,
    )
    low = earth_rotation_uvw_lambda(
        sample,
        hour_angles_h,
        DECLINATION_DEG,
        FREQUENCY_HZ,
    )
    high = earth_rotation_uvw_lambda(
        sample,
        hour_angles_h,
        DECLINATION_DEG,
        2.0 * FREQUENCY_HZ,
    )

    wavelength_m = C_M_S / FREQUENCY_HZ
    metre_error = maximum_abs_difference(low * wavelength_m, b_uvw_m)
    scale_denominator = np.maximum(np.abs(2.0 * low), np.finfo(float).tiny)
    scaling_error = float(np.max(np.abs(high - 2.0 * low) / scale_denominator))
    if metre_error >= METRE_PROJECTION_TOLERANCE_M:
        raise AssertionError(
            f"metre projection error {metre_error:.3e} m exceeds "
            f"{METRE_PROJECTION_TOLERANCE_M:.1e}"
        )
    if scaling_error >= FREQUENCY_SCALING_TOLERANCE:
        raise AssertionError(
            f"frequency-scaling error {scaling_error:.3e} exceeds "
            f"{FREQUENCY_SCALING_TOLERANCE:.1e}"
        )
    return metre_error, scaling_error


def display_indices(stage: str, baseline_count: int) -> np.ndarray:
    if baseline_count <= PLOT_BASELINE_CAP:
        return np.arange(baseline_count, dtype=np.int64)
    stage_index = STAGES.index(stage)
    rng = np.random.default_rng(20260824 + 1009 * stage_index)
    indices = rng.choice(baseline_count, size=PLOT_BASELINE_CAP, replace=False)
    indices.sort()
    return indices.astype(np.int64)


def write_track_plot(stage: str, sampled: np.ndarray, output_dir: Path) -> None:
    baseline_count = sampled.shape[1]
    indices = display_indices(stage, baseline_count)
    uv_klambda = sampled[:, indices, :2].reshape(-1, 2) / 1000.0
    full_uv_klambda = sampled[..., :2] / 1000.0
    limit = max(float(np.max(np.abs(full_uv_klambda))) * 1.05, 1e-9)
    rasterized = len(uv_klambda) > 20_000
    marker_size = 6.0 if baseline_count <= 20 else 1.0

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
        scatter_kwargs = {
            "s": marker_size,
            "linewidths": 0,
            "rasterized": rasterized,
        }
        axes.scatter(
            uv_klambda[:, 0],
            uv_klambda[:, 1],
            label="physical baseline",
            **scatter_kwargs,
        )
        axes.scatter(
            -uv_klambda[:, 0],
            -uv_klambda[:, 1],
            label="conjugate",
            **scatter_kwargs,
        )
        axes.set_aspect("equal", adjustable="box")
        axes.set_xlim(-limit, limit)
        axes.set_ylim(-limit, limit)
        axes.set_xlabel("u (kλ)")
        axes.set_ylabel("v (kλ)")
        subset_note = "all baselines" if len(indices) == baseline_count else f"{len(indices):,}-baseline display subset"
        axes.set_title(
            f"SKA-Low {stage}: -3 h to +3 h at 150 MHz\n"
            f"{baseline_count:,} physical baselines; {subset_note} plotted"
        )
        axes.legend(loc="best", markerscale=3.0)
        axes.grid(alpha=0.2, linewidth=0.5)
        slug = STAGE_SLUGS[stage]
        figure.savefig(output_dir / f"{slug}_six_hour_uv.png", dpi=300)
        figure.savefig(output_dir / f"{slug}_six_hour_uv.pdf")
        plt.close(figure)


def validate_stages(plot_dir: Path | None) -> list[dict[str, float | int | str]]:
    rows: list[dict[str, float | int | str]] = []
    for stage in STAGES:
        b_enu_m, baseline_count = validate_baseline_construction(stage)
        sampled, track_error = validate_track_against_single_time_transform(b_enu_m)
        metre_error, frequency_error = validate_frequency_scaling(b_enu_m)

        row = {
            "stage": stage,
            "baselines": baseline_count,
            "track_error_lambda": track_error,
            "metre_projection_error_m": metre_error,
            "frequency_error_relative": frequency_error,
            "max_abs_u_klambda": float(np.max(np.abs(sampled[..., 0])) / 1000.0),
            "max_abs_v_klambda": float(np.max(np.abs(sampled[..., 1])) / 1000.0),
            "max_abs_w_klambda": float(np.max(np.abs(sampled[..., 2])) / 1000.0),
        }
        rows.append(row)
        if plot_dir is not None:
            write_track_plot(stage, sampled, plot_dir)

    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("build/uv-sampling-validation"),
        help="Directory for ignored visual validation products",
    )
    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="Run numerical checks without creating validation plots",
    )
    args = parser.parse_args()

    plot_dir = None
    if not args.no_plots:
        plot_dir = args.output / "plots"
        plot_dir.mkdir(parents=True, exist_ok=True)

    rows = validate_stages(plot_dir)
    print(
        "PASS six-hour sampling setup: "
        f"{len(HOUR_ANGLES_H)} hour angles from {HOUR_ANGLES_H[0]:+.1f} h "
        f"to {HOUR_ANGLES_H[-1]:+.1f} h at {FREQUENCY_HZ / 1e6:.0f} MHz, "
        f"declination {DECLINATION_DEG:+.1f} deg"
    )
    for row in rows:
        print(
            f"PASS {row['stage']:5s}: {row['baselines']:6d} baselines, "
            f"track error {row['track_error_lambda']:.3e} λ, "
            f"metre error {row['metre_projection_error_m']:.3e} m, "
            f"frequency error {row['frequency_error_relative']:.3e}, "
            f"|u|max {row['max_abs_u_klambda']:.3f} kλ, "
            f"|v|max {row['max_abs_v_klambda']:.3f} kλ, "
            f"|w|max {row['max_abs_w_klambda']:.3f} kλ"
        )
    if plot_dir is not None:
        print(f"Wrote visual validation plots to {plot_dir}")
    print("PASS SKAetch UV sampling")


if __name__ == "__main__":
    main()
