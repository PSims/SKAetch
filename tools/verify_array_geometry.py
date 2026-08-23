#!/usr/bin/env python3
"""Validate frozen SKA-Low geometry and optionally compare regenerated data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from importlib.resources import files
from pathlib import Path
from typing import Iterable

from skaetch.geometry import STAGES, load_geometry_manifest, load_station_geometry

EXPECTED = {
    "AA0.5": (4, 5591.760871614204),
    "AA1": (16, 5802.487387818477),
    "AA2": (68, 64805.302212565075),
    "AA*": (307, 73393.21544101616),
    "AA4": (512, 73441.63646176794),
}

STAGE_FILES = {
    "AA0.5": "AA0p5_east_north_m.csv",
    "AA1": "AA1_east_north_m.csv",
    "AA2": "AA2_east_north_m.csv",
    "AA*": "AAstar_east_north_m.csv",
    "AA4": "AA4_east_north_m.csv",
}

EXPECTED_SOURCE = {
    "package": "ska-ost-array-config",
    "package_version": "4.5.0",
    "coordinate_source": "LowSubArray.array_config.xyz",
    "station_name_source": "LowSubArray.array_config.names",
    "coordinate_frame": "local ENU",
    "csv_columns": ["index", "station_name", "east_m", "north_m"],
}

StationGeometry = tuple[tuple[str, float, float], ...]


def maximum_baseline(geometry: Iterable[tuple[str, float, float]]) -> float:
    rows = tuple(geometry)
    maximum = 0.0
    for index, (_, east_a, north_a) in enumerate(rows[:-1]):
        for _, east_b, north_b in rows[index + 1 :]:
            maximum = max(maximum, math.hypot(east_b - east_a, north_b - north_a))
    return maximum


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_geometry_csv(path: Path) -> StationGeometry:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != EXPECTED_SOURCE["csv_columns"]:
            raise AssertionError(f"{path}: unexpected CSV columns {reader.fieldnames}")

        geometry: list[tuple[str, float, float]] = []
        names: set[str] = set()
        for expected_index, row in enumerate(reader):
            index = int(row["index"])
            if index != expected_index:
                raise AssertionError(f"{path}: row index {index}, expected {expected_index}")
            name = row["station_name"].strip()
            if not name:
                raise AssertionError(f"{path}: empty station name at index {index}")
            if name in names:
                raise AssertionError(f"{path}: duplicate station name {name!r}")
            names.add(name)
            geometry.append((name, float(row["east_m"]), float(row["north_m"])))

    return tuple(geometry)


def validate_manifest_source(manifest: dict, label: str) -> None:
    if manifest.get("source") != EXPECTED_SOURCE:
        raise AssertionError(f"{label}: unexpected geometry source metadata")
    if set(manifest.get("stages", {})) != set(STAGES):
        raise AssertionError(f"{label}: unexpected stage set in manifest")


def validate_stage_record(
    stage: str,
    geometry: StationGeometry,
    manifest: dict,
    file_digest: str,
    label: str,
) -> float:
    expected_count, expected_max = EXPECTED[stage]
    if len(geometry) != expected_count:
        raise AssertionError(f"{stage}: {label} has {len(geometry)} stations, expected {expected_count}")

    maximum = maximum_baseline(geometry)
    if abs(maximum - expected_max) > 1e-6:
        raise AssertionError(
            f"{stage}: {label} max baseline {maximum:.9f} m, expected {expected_max:.9f} m"
        )

    record = manifest["stages"][stage]
    if record.get("file") != STAGE_FILES[stage]:
        raise AssertionError(f"{stage}: {label} manifest filename mismatch")
    if record.get("station_count") != expected_count:
        raise AssertionError(f"{stage}: {label} manifest station count mismatch")
    if abs(float(record.get("maximum_baseline_m")) - maximum) > 1e-6:
        raise AssertionError(f"{stage}: {label} manifest maximum-baseline mismatch")
    if record.get("file_sha256") != file_digest:
        raise AssertionError(f"{stage}: {label} geometry file hash does not match manifest")

    return maximum


def compare_geometry(
    reference: StationGeometry,
    candidate: StationGeometry,
    stage: str,
    tolerance_m: float,
) -> None:
    if len(reference) != len(candidate):
        raise AssertionError(f"{stage}: candidate has {len(candidate)} stations, expected {len(reference)}")

    for index, (expected, actual) in enumerate(zip(reference, candidate, strict=True)):
        expected_name, expected_east, expected_north = expected
        actual_name, actual_east, actual_north = actual
        if actual_name != expected_name:
            raise AssertionError(
                f"{stage}: station {index} name {actual_name!r}, expected {expected_name!r}"
            )
        error = max(abs(expected_east - actual_east), abs(expected_north - actual_north))
        if error > tolerance_m:
            raise AssertionError(
                f"{stage}: station {index} differs by {error:.3e} m "
                f"(limit {tolerance_m:.3e} m)"
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--candidate",
        type=Path,
        help="Optional regenerated geometry directory to compare with the packaged reference",
    )
    parser.add_argument("--tolerance-m", type=float, default=1e-6)
    args = parser.parse_args()

    reference_manifest = load_geometry_manifest()
    validate_manifest_source(reference_manifest, "packaged reference")

    candidate_manifest = None
    if args.candidate:
        candidate_manifest_path = args.candidate / "authoritative_geometry_manifest.json"
        with candidate_manifest_path.open("r", encoding="utf-8") as handle:
            candidate_manifest = json.load(handle)
        validate_manifest_source(candidate_manifest, "candidate")

    for stage in STAGES:
        reference = load_station_geometry(stage)
        reference_resource = files("skaetch").joinpath("data", "geometry", STAGE_FILES[stage])
        reference_digest = hashlib.sha256(reference_resource.read_bytes()).hexdigest()
        maximum = validate_stage_record(
            stage,
            reference,
            reference_manifest,
            reference_digest,
            "packaged reference",
        )

        suffix = ""
        if args.candidate:
            assert candidate_manifest is not None
            candidate_path = args.candidate / STAGE_FILES[stage]
            candidate = read_geometry_csv(candidate_path)
            validate_stage_record(
                stage,
                candidate,
                candidate_manifest,
                sha256_path(candidate_path),
                "candidate",
            )
            compare_geometry(reference, candidate, stage, args.tolerance_m)
            suffix = "; regenerated station names and coordinates match"

        print(
            f"PASS {stage:5s}: {len(reference):3d} stations, "
            f"max baseline {maximum / 1000:7.3f} km{suffix}"
        )

    print("PASS authoritative SKA-Low geometry")


if __name__ == "__main__":
    main()
