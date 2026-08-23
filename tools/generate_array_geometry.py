#!/usr/bin/env python3
"""Regenerate staged SKA-Low geometry from the pinned SKAO package."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PACKAGE_NAME = "ska-ost-array-config"
PACKAGE_VERSION = "4.5.0"
STAGES = ("AA0.5", "AA1", "AA2", "AA*", "AA4")
STAGE_SLUGS = {
    "AA0.5": "AA0p5",
    "AA1": "AA1",
    "AA2": "AA2",
    "AA*": "AAstar",
    "AA4": "AA4",
}
CSV_COLUMNS = ("index", "station_name", "east_m", "north_m")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def package_value(subarray, name: str):
    value = getattr(subarray, name, None)
    if value is None:
        return None
    return value() if callable(value) else value


def maximum_baseline_m(xy_m: np.ndarray) -> float:
    maximum_squared = 0.0
    for index in range(len(xy_m) - 1):
        delta = xy_m[index + 1 :] - xy_m[index]
        if len(delta):
            maximum_squared = max(
                maximum_squared,
                float(np.max(np.sum(delta * delta, axis=1))),
            )
    return math.sqrt(maximum_squared)


def package_max_baseline_m(subarray) -> float | None:
    value = package_value(subarray, "max_bl")
    if value is None:
        return None
    if hasattr(value, "to_value"):
        for unit in ("m", "meter", "metre"):
            try:
                return float(value.to_value(unit))
            except Exception:
                continue
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_geometry(subarray, stage: str) -> tuple[tuple[str, ...], np.ndarray]:
    """Return package station names and local East/North offsets in package order."""
    xyz = np.asarray(subarray.array_config.xyz.values, dtype=float)
    if xyz.ndim != 2 or xyz.shape[1] < 2:
        raise RuntimeError(f"{stage}: unexpected array_config.xyz shape {xyz.shape}")

    xy_m = xyz[:, :2].copy()
    if not np.isfinite(xy_m).all():
        raise RuntimeError(f"{stage}: array_config.xyz contains non-finite East/North values")

    raw_names = np.asarray(subarray.array_config.names.values)
    if raw_names.ndim != 1:
        raise RuntimeError(f"{stage}: unexpected array_config.names shape {raw_names.shape}")
    station_names = tuple(str(name).strip() for name in raw_names)

    if len(station_names) != len(xy_m):
        raise RuntimeError(
            f"{stage}: array_config.names contains {len(station_names)} names "
            f"for {len(xy_m)} coordinate rows"
        )
    if any(not name for name in station_names):
        raise RuntimeError(f"{stage}: array_config.names contains an empty station name")
    if len(set(station_names)) != len(station_names):
        raise RuntimeError(f"{stage}: array_config.names contains duplicate station names")

    expected = package_value(subarray, "n_station")
    if expected is not None and len(xy_m) != int(expected):
        raise RuntimeError(
            f"{stage}: array_config.xyz contains {len(xy_m)} stations "
            f"but the package reports {int(expected)}"
        )

    return station_names, xy_m


def write_geometry_csv(path: Path, station_names: tuple[str, ...], xy_m: np.ndarray) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(CSV_COLUMNS)
        for index, (station_name, (east_m, north_m)) in enumerate(
            zip(station_names, xy_m, strict=True)
        ):
            writer.writerow((index, station_name, f"{east_m:.12f}", f"{north_m:.12f}"))


def station_marker_size(station_count: int) -> float:
    if station_count <= 16:
        return 30.0
    if station_count <= 80:
        return 18.0
    if station_count <= 320:
        return 9.0
    return 6.5


def write_layout_plot(stage: str, xy_m: np.ndarray, maximum_baseline: float, output_stem: Path) -> None:
    """Write publication-quality PNG and vector PDF station-layout figures."""
    xy_km = xy_m / 1000.0
    station_count = len(xy_km)

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
        axes.scatter(
            xy_km[:, 0],
            xy_km[:, 1],
            s=station_marker_size(station_count),
            marker="o",
            linewidths=0,
        )
        axes.set_aspect("equal", adjustable="box")
        axes.margins(x=0.08, y=0.08)
        axes.set_xlabel("East offset (km)")
        axes.set_ylabel("North offset (km)")
        axes.set_title(
            f"SKA-Low {stage} station layout\n"
            f"{station_count} stations · maximum baseline {maximum_baseline / 1000:.3f} km",
            pad=10,
        )
        axes.grid(True, linewidth=0.6, alpha=0.25)

        figure.savefig(output_stem.with_suffix(".png"), dpi=300)
        figure.savefig(output_stem.with_suffix(".pdf"))
        plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regenerate the staged SKA-Low geometry and visual inspection plots."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("build/geometry-reproduction"),
        help="Output root (default: build/geometry-reproduction)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing output directory",
    )
    args = parser.parse_args()

    installed = importlib.metadata.version(PACKAGE_NAME)
    if installed != PACKAGE_VERSION:
        raise RuntimeError(f"Expected {PACKAGE_NAME}=={PACKAGE_VERSION}, found {installed}")

    if args.output_dir.exists():
        if not args.force:
            raise SystemExit(f"Output directory already exists: {args.output_dir} (use --force)")
        shutil.rmtree(args.output_dir)

    geometry_dir = args.output_dir / "geometry"
    plot_dir = args.output_dir / "plots"
    geometry_dir.mkdir(parents=True)
    plot_dir.mkdir(parents=True)

    from ska_ost_array_config.array_config import LowSubArray

    manifest = {
        "source": {
            "package": PACKAGE_NAME,
            "package_version": PACKAGE_VERSION,
            "coordinate_source": "LowSubArray.array_config.xyz",
            "station_name_source": "LowSubArray.array_config.names",
            "coordinate_frame": "local ENU",
            "csv_columns": list(CSV_COLUMNS),
        },
        "stages": {},
    }

    for stage in STAGES:
        print(f"Generating {stage}")
        subarray = LowSubArray(subarray_type=stage)
        station_names, xy_m = extract_geometry(subarray, stage)
        slug = STAGE_SLUGS[stage]
        csv_path = geometry_dir / f"{slug}_east_north_m.csv"
        write_geometry_csv(csv_path, station_names, xy_m)

        maximum_baseline = maximum_baseline_m(xy_m)
        package_maximum = package_max_baseline_m(subarray)
        if package_maximum is not None:
            direct_error = abs(package_maximum - maximum_baseline)
            kilometre_error = abs(1000.0 * package_maximum - maximum_baseline)
            if kilometre_error < direct_error:
                package_maximum *= 1000.0
            if abs(package_maximum - maximum_baseline) / maximum_baseline > 0.02:
                raise RuntimeError(
                    f"{stage}: extracted maximum baseline {maximum_baseline:.3f} m disagrees "
                    f"with package max_bl {package_maximum:.3f} m"
                )

        write_layout_plot(
            stage,
            xy_m,
            maximum_baseline,
            plot_dir / f"{slug}_station_layout",
        )

        manifest["stages"][stage] = {
            "file": csv_path.name,
            "station_count": int(len(xy_m)),
            "maximum_baseline_m": float(f"{maximum_baseline:.9f}"),
            "file_sha256": sha256_file(csv_path),
        }

    manifest_path = geometry_dir / "authoritative_geometry_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {geometry_dir}")
    print(f"Wrote {plot_dir}")


if __name__ == "__main__":
    main()
