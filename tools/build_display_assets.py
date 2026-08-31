#!/usr/bin/env python3
"""Reproduce visitor-facing array-layout and Fourier-sampling display assets."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from skaetch.geometry import STAGES, load_geometry_manifest, load_station_coordinates
from skaetch.operators import DECLINATION_DEG, FREQUENCY_HZ, duration_hour_angles_h
from skaetch.sampling import earth_rotation_uvw_lambda, station_baselines_enu_m
from skaetch.uvw import SKA_LOW_LATITUDE_DEG

TRACK_HOURS = duration_hour_angles_h("6h")
TRACK_CENTRE_INDEX = int(np.argmin(np.abs(TRACK_HOURS)))
TRACK_INT16_SCALE = 30_000
TRACK_BASELINE_CAPS = {
    "AA0.5": 6,
    "AA1": 120,
    "AA2": 2_278,
    "AA*": 18_000,
    "AA4": 36_000,
}
STATIC_BASELINE_CAPS = {
    "AA*": 24_000,
    "AA4": 48_000,
}
PRIMARY = "#0b648f"
CONJUGATE = "#e88426"


def slug(stage: str) -> str:
    return stage.replace(".", "p").replace("*", "star")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def deterministic_track_indices(stage: str, n_baselines: int) -> np.ndarray:
    stage_index = STAGES.index(stage)
    cap = min(TRACK_BASELINE_CAPS[stage], n_baselines)
    if cap >= n_baselines:
        return np.arange(n_baselines, dtype=np.int64)
    rng = np.random.default_rng(20260818 + 1009 * stage_index)
    indices = rng.choice(n_baselines, size=cap, replace=False)
    indices.sort()
    return indices.astype(np.int64)


def deterministic_static_indices(stage: str, n_baselines: int) -> np.ndarray:
    cap = min(STATIC_BASELINE_CAPS.get(stage, n_baselines), n_baselines)
    if cap >= n_baselines:
        return np.arange(n_baselines, dtype=np.int64)
    stage_index = STAGES.index(stage)
    rng = np.random.default_rng(20260821 + 4099 * stage_index)
    indices = rng.choice(n_baselines, size=cap, replace=False)
    indices.sort()
    return indices.astype(np.int64)


def marker_style(n_baselines: int, duration: str) -> tuple[float, float]:
    if n_baselines < 20:
        return (20.0 if duration == "snapshot" else 7.0), 0.88
    if n_baselines < 500:
        return (8.0 if duration == "snapshot" else 3.5), 0.78
    if n_baselines < 5_000:
        return (3.2 if duration == "snapshot" else 1.8), 0.66
    if n_baselines <= 12_000:
        return (1.7 if duration == "snapshot" else 1.15), 0.58
    if n_baselines <= 24_000:
        return (1.25 if duration == "snapshot" else 0.85), 0.48
    if n_baselines <= 48_000:
        return (0.90 if duration == "snapshot" else 0.58), 0.40
    return (0.75 if duration == "snapshot" else 0.45), 0.34


def stage_products(stage: str):
    coordinates = np.asarray(load_station_coordinates(stage), dtype=float)
    baselines = station_baselines_enu_m(coordinates)
    six_hour = earth_rotation_uvw_lambda(
        baselines,
        TRACK_HOURS,
        DECLINATION_DEG,
        FREQUENCY_HZ,
    )
    full_max = max(float(np.max(np.abs(six_hour[..., 0]))), float(np.max(np.abs(six_hour[..., 1]))))
    axis_limit_lambda = max(1.0, 1.05 * full_max)
    return coordinates, baselines, six_hour, axis_limit_lambda


def write_layout(stage: str, coordinates: np.ndarray, output_dir: Path) -> Path:
    fig = plt.figure(figsize=(6.4, 5.2), dpi=100)
    ax = fig.add_axes([0.13, 0.15, 0.82, 0.76])
    ax.scatter(coordinates[:, 0] / 1000.0, coordinates[:, 1] / 1000.0, s=8)
    ax.set_aspect("equal")
    ax.set_xlabel("East (km)")
    ax.set_ylabel("North (km)")
    ax.set_title(f"{stage}: {len(coordinates)} stations")
    path = output_dir / f"layout_{slug(stage)}.png"
    fig.savefig(path, dpi=100)
    plt.close(fig)
    return path


def write_static_uv(
    stage: str,
    baselines: np.ndarray,
    six_hour: np.ndarray,
    axis_limit_lambda: float,
    output_dir: Path,
) -> dict[str, dict]:
    indices = deterministic_static_indices(stage, len(baselines))
    products: dict[str, dict] = {}
    samples = {
        "snapshot": earth_rotation_uvw_lambda(
            baselines[indices], np.array([0.0]), DECLINATION_DEG, FREQUENCY_HZ
        ),
        "6h": six_hour[:, indices, :],
    }
    limit_klambda = axis_limit_lambda / 1000.0
    for duration, uvw in samples.items():
        marker_size, marker_alpha = marker_style(len(indices), duration)
        fig = plt.figure(figsize=(6.4, 5.2), dpi=100)
        ax = fig.add_axes([0.135, 0.165, 0.81, 0.73])
        for group in uvw:
            u = group[:, 0] / 1000.0
            v = group[:, 1] / 1000.0
            ax.scatter(u, v, s=marker_size, color=PRIMARY, alpha=marker_alpha, linewidths=0)
            ax.scatter(-u, -v, s=marker_size, color=CONJUGATE, alpha=marker_alpha, linewidths=0)
        ax.set_aspect("equal")
        ax.set_xlim(-limit_klambda, limit_klambda)
        ax.set_ylim(-limit_klambda, limit_klambda)
        ax.set_xlabel("u (kλ)", fontsize=14, labelpad=7)
        ax.set_ylabel("v (kλ)", fontsize=14, labelpad=7)
        ax.tick_params(axis="both", labelsize=12, length=5, width=1)
        label = "snapshot" if duration == "snapshot" else "6 h Earth rotation"
        ax.set_title(f"{stage}: {label}", fontsize=16, pad=10)
        path = output_dir / f"uv_{slug(stage)}_{duration}.png"
        fig.savefig(path, dpi=100)
        plt.close(fig)
        products[path.name] = {
            "sha256": sha256(path),
            "width_px": 640,
            "height_px": 520,
            "stage": stage,
            "duration": duration,
            "total_baseline_pairs": len(baselines),
            "display_baseline_pairs_per_hour": int(len(indices)),
            "display_subset": bool(len(indices) < len(baselines)),
        }
    return products


def write_track(
    stage: str,
    baselines: np.ndarray,
    six_hour: np.ndarray,
    axis_limit_lambda: float,
    output_dir: Path,
) -> tuple[Path, dict]:
    indices = deterministic_track_indices(stage, len(baselines))
    selected = six_hour[:, indices, :2].transpose(1, 0, 2)
    quantized = np.clip(
        np.rint(selected / axis_limit_lambda * TRACK_INT16_SCALE),
        -TRACK_INT16_SCALE,
        TRACK_INT16_SCALE,
    ).astype("<i2")
    payload = {
        "schema_version": 1,
        "stage": stage,
        "frequency_hz": FREQUENCY_HZ,
        "declination_deg": DECLINATION_DEG,
        "site_latitude_deg": SKA_LOW_LATITUDE_DEG,
        "hour_angles_h": TRACK_HOURS.tolist(),
        "centre_index": TRACK_CENTRE_INDEX,
        "axis_limit_klambda": axis_limit_lambda / 1000.0,
        "coordinate_scale_int16": TRACK_INT16_SCALE,
        "total_baseline_pairs": len(baselines),
        "display_baseline_pairs": int(len(indices)),
        "display_subset": bool(len(indices) < len(baselines)),
        "display_selection": (
            "all baselines"
            if len(indices) == len(baselines)
            else f"deterministic {len(indices):,}-baseline animation subset; frozen imaging uses all {len(baselines):,} baselines"
        ),
        "array_shape": [int(len(indices)), int(len(TRACK_HOURS)), 2],
        "array_order": "baseline,time,(u,v)",
        "encoding": "little-endian int16, C-order, base64",
        "uv_int16_base64": base64.b64encode(quantized.tobytes(order="C")).decode("ascii"),
    }
    path = output_dir / f"uv_tracks_{slug(stage)}.json"
    path.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    record = {
        "file": path.name,
        "total_baseline_pairs": len(baselines),
        "display_baseline_pairs": int(len(indices)),
        "display_subset": bool(len(indices) < len(baselines)),
        "axis_limit_klambda": round(axis_limit_lambda / 1000.0, 8),
        "size_mb": round(path.stat().st_size / 1024**2, 4),
        "sha256": sha256(path),
    }
    return path, record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("build/display-assets-reproduction"),
        help="output directory; committed browser assets are never overwritten by default",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    layout_manifest = {"schema_version": 1, "display_only": True, "products": {}}
    uv_products: dict[str, dict] = {}
    track_manifest = {
        "schema_version": 1,
        "engine": "Corrected-UVW browser track assets with stage-dependent display density",
        "frequency_hz": FREQUENCY_HZ,
        "declination_deg": DECLINATION_DEG,
        "site_latitude_deg": SKA_LOW_LATITUDE_DEG,
        "hour_angles_h": TRACK_HOURS.tolist(),
        "centre_index": TRACK_CENTRE_INDEX,
        "animation_sequence": "display animation runs chronologically H=-3 h to +3 h; Snapshot remains H=0",
        "display_baseline_caps": TRACK_BASELINE_CAPS,
        "display_density_note": "Stage-dependent animation subsets are display-only: AA* uses 18,000 and AA4 36,000 representative baseline pairs so construction growth is visually apparent; frozen imaging uses every baseline pair.",
        "static_sampling_note": "Static uv_* PNGs remain available as endpoint sampling visualisations and use their own display-density policy; frozen imaging operators use every baseline pair.",
        "stages": {},
    }

    for stage in STAGES:
        coordinates, baselines, six_hour, axis_limit = stage_products(stage)
        layout = write_layout(stage, coordinates, args.output)
        layout_manifest["products"][layout.name] = {
            "sha256": sha256(layout),
            "bytes": layout.stat().st_size,
        }
        uv_products.update(write_static_uv(stage, baselines, six_hour, axis_limit, args.output))
        track_path, track_record = write_track(stage, baselines, six_hour, axis_limit, args.output)
        track_manifest["stages"][stage] = track_record
        print(
            f"{stage}: {track_record['display_baseline_pairs']:,}/{len(baselines):,} animated display baselines; "
            f"track asset {track_path.stat().st_size / 1024**2:.2f} MiB"
        )

    (args.output / "layout_manifest.json").write_text(json.dumps(layout_manifest, indent=2) + "\n")
    (args.output / "uv_sampling_display_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "display_only": True,
                "colour_semantics": {"baseline_sample": PRIMARY, "complex_conjugate": CONJUGATE},
                "baseline_count_formula": "N(N-1)/2 independent unordered antenna pairs",
                "conjugate_relation": "V(-u,-v) = V*(u,v) for a real sky brightness distribution",
                "geometry_package_version": load_geometry_manifest().get("package_version"),
                "display_baseline_caps": STATIC_BASELINE_CAPS,
                "display_density_note": "Dense static plots use deterministic stage-dependent display subsets: AA* 24,000 and AA4 48,000 baseline pairs per hour-angle sample. Imaging still uses every baseline pair.",
                "products": uv_products,
            },
            indent=2,
        )
        + "\n"
    )
    (args.output / "uv_track_manifest.json").write_text(json.dumps(track_manifest, indent=2) + "\n")
    print(f"Wrote reproduced display assets to {args.output}")


if __name__ == "__main__":
    main()
