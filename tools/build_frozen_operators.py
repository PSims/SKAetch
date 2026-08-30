#!/usr/bin/env python3
"""Reproduce SKAetch frozen sparse Fourier operators from committed geometry."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from skaetch.geometry import STAGES, load_station_coordinates
from skaetch.operators import (
    DECLINATION_DEG,
    DURATIONS,
    FREQUENCY_HZ,
    OUTREACH_SPEC,
    SCIENCE_SPEC,
    OperatorSpec,
    build_sparse_operator_from_uv,
    duration_hour_angles_h,
)
from skaetch.sampling import earth_rotation_uvw_lambda, station_baselines_enu_m


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stage_slug(stage: str) -> str:
    return stage.replace(".", "p").replace("*", "star")


def filename(stage: str, duration: str, spec: OperatorSpec) -> str:
    prefix = "science_operator" if spec.mode == "science" else "operator"
    return f"{prefix}_{stage_slug(stage)}_{duration}.npz"


def build_one(stage: str, duration: str, spec: OperatorSpec):
    coordinates = np.asarray(load_station_coordinates(stage), dtype=float)
    baselines = station_baselines_enu_m(coordinates)
    hour_angles = duration_hour_angles_h(duration)
    uvw = earth_rotation_uvw_lambda(
        baselines,
        hour_angles,
        DECLINATION_DEG,
        FREQUENCY_HZ,
    )
    return build_sparse_operator_from_uv(uvw[..., 0], uvw[..., 1], spec)


def write_operator(path: Path, arrays, spec: OperatorSpec) -> None:
    payload = {
        "touched": arrays.touched,
        "coeff": arrays.coeff,
        "input_indices": arrays.input_indices,
        "accepted_samples": np.array(arrays.accepted_samples, dtype=np.int64),
        "total_samples": np.array(arrays.total_samples, dtype=np.int64),
    }
    if arrays.total_weight is not None:
        payload["total_weight"] = np.array(arrays.total_weight, dtype=np.float64)
    if spec.mode == "science":
        np.savez_compressed(path, **payload)
    else:
        np.savez(path, **payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("build/operator-reproduction"),
        help="Output directory; committed frozen assets are never overwritten by default",
    )
    parser.add_argument("--modes", nargs="+", choices=("outreach", "science"), default=["outreach", "science"])
    parser.add_argument("--stages", nargs="+", choices=STAGES, default=list(STAGES))
    parser.add_argument("--durations", nargs="+", choices=DURATIONS, default=list(DURATIONS))
    args = parser.parse_args()

    specs = {"outreach": OUTREACH_SPEC, "science": SCIENCE_SPEC}
    summary: dict[str, dict] = {}
    for mode in args.modes:
        spec = specs[mode]
        mode_dir = args.output / mode
        mode_dir.mkdir(parents=True, exist_ok=True)
        summary[mode] = {}
        for stage in args.stages:
            summary[mode][stage] = {}
            for duration in args.durations:
                print(f"Building {mode} {stage} {duration}...", flush=True)
                arrays = build_one(stage, duration, spec)
                path = mode_dir / filename(stage, duration, spec)
                write_operator(path, arrays, spec)
                summary[mode][stage][duration] = {
                    "file": path.name,
                    "touched_uv_cells": int(len(arrays.touched)),
                    "accepted_samples": int(arrays.accepted_samples),
                    "total_samples": int(arrays.total_samples),
                    "total_weight": arrays.total_weight,
                    "sha256": sha256(path),
                }
                print(
                    f"  {len(arrays.touched):,} cells; "
                    f"{arrays.accepted_samples:,}/{arrays.total_samples:,} accepted",
                    flush=True,
                )
    (args.output / "reproduction_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Wrote reproduced operators to {args.output}")


if __name__ == "__main__":
    main()
