"""Access the frozen staged SKA-Low station geometries used by SKAetch."""

from __future__ import annotations

import csv
import json
from importlib.resources import files
from typing import Final

STAGES: Final[tuple[str, ...]] = ("AA0.5", "AA1", "AA2", "AA*", "AA4")

_STAGE_FILES: Final[dict[str, str]] = {
    "AA0.5": "AA0p5_east_north_m.csv",
    "AA1": "AA1_east_north_m.csv",
    "AA2": "AA2_east_north_m.csv",
    "AA*": "AAstar_east_north_m.csv",
    "AA4": "AA4_east_north_m.csv",
}

_CSV_COLUMNS: Final[list[str]] = ["index", "station_name", "east_m", "north_m"]


def _geometry_dir():
    return files("skaetch").joinpath("data", "geometry")


def _stage_filename(stage: str) -> str:
    try:
        return _STAGE_FILES[stage]
    except KeyError as exc:
        choices = ", ".join(STAGES)
        raise ValueError(f"Unknown SKA-Low stage {stage!r}; choose one of {choices}") from exc


def load_station_geometry(stage: str) -> tuple[tuple[str, float, float], ...]:
    """Return ``(station_name, east_m, north_m)`` rows for one SKA-Low stage."""
    path = _geometry_dir().joinpath(_stage_filename(stage))
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != _CSV_COLUMNS:
            raise ValueError(f"Unexpected geometry CSV columns in {path.name}: {reader.fieldnames}")

        geometry: list[tuple[str, float, float]] = []
        names: set[str] = set()
        for expected_index, row in enumerate(reader):
            index = int(row["index"])
            if index != expected_index:
                raise ValueError(
                    f"Unexpected station index {index} in {path.name}; expected {expected_index}"
                )
            name = row["station_name"].strip()
            if not name:
                raise ValueError(f"Empty station name at index {index} in {path.name}")
            if name in names:
                raise ValueError(f"Duplicate station name {name!r} in {path.name}")
            names.add(name)
            geometry.append((name, float(row["east_m"]), float(row["north_m"])))

    return tuple(geometry)


def load_station_coordinates(stage: str) -> tuple[tuple[float, float], ...]:
    """Return local ``(east_m, north_m)`` station offsets for one SKA-Low stage."""
    return tuple((east_m, north_m) for _, east_m, north_m in load_station_geometry(stage))


def load_geometry_manifest() -> dict:
    """Return metadata describing the frozen staged geometry files."""
    path = _geometry_dir().joinpath("authoritative_geometry_manifest.json")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
