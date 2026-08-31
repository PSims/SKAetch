#!/usr/bin/env python3
"""Reproduce the optional local 1.5-degree Fornax A cleaned-image products."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from importlib.resources import files
from pathlib import Path

import numpy as np
from PIL import Image

from skaetch.geometry import STAGES, load_geometry_manifest, load_station_coordinates
from skaetch.imaging import centered_fft2
from skaetch.operators import (
    DECLINATION_DEG,
    DURATIONS,
    FREQUENCY_HZ,
    OperatorSpec,
    SparseFourierOperator,
    build_sparse_operator_from_uv,
    duration_hour_angles_h,
    source_pixels_for_spec,
)
from skaetch.preprocessing import embed_preprocessed_source, science_preprocess
from skaetch.reconstruction import positive_support_reconstruction
from skaetch.runtime import centre_crop, display_crop_size, display_positive
from skaetch.sampling import earth_rotation_uvw_lambda, station_baselines_enu_m

FORNAX_SIZE_DEG = 72.0 / 60.0
FIELD_DEG = 1.5
NPIX = 2048
ITERATIONS = 8
DEFAULT_ASSETS_DIR = Path(os.environ.get("SKAETCH_ASSETS_DIR", "local_assets"))
FORNAX_SPEC = OperatorSpec(
    mode="science",
    weighting="natural",
    npix=NPIX,
    field_deg=FIELD_DEG,
    source_size_deg=FORNAX_SIZE_DEG,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def slug(stage: str) -> str:
    return stage.replace(".", "p").replace("*", "star")


def expected_fornax_source() -> dict:
    resource = files("skaetch").joinpath("data", "sources", "source_manifest.json")
    with resource.open("r", encoding="utf-8") as handle:
        return json.load(handle)["sources"]["demo_fornax"]


def build_operator(stage: str, duration: str) -> SparseFourierOperator:
    coordinates = np.asarray(load_station_coordinates(stage), dtype=float)
    baselines = station_baselines_enu_m(coordinates)
    uvw = earth_rotation_uvw_lambda(
        baselines,
        duration_hour_angles_h(duration),
        DECLINATION_DEG,
        FREQUENCY_HZ,
    )
    arrays = build_sparse_operator_from_uv(uvw[..., 0], uvw[..., 1], FORNAX_SPEC)
    return SparseFourierOperator(
        spec=FORNAX_SPEC,
        touched=arrays.touched,
        coeff=arrays.coeff,
        input_indices=arrays.input_indices,
        accepted_samples=arrays.accepted_samples,
        total_samples=arrays.total_samples,
        total_weight=arrays.total_weight,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=DEFAULT_ASSETS_DIR,
        help="optional local-asset root containing sources/fornax_A_nrao.jpg",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="output directory; default: <assets-dir>/fornax_cleaned",
    )
    parser.add_argument("--stages", nargs="+", choices=STAGES, default=list(STAGES))
    parser.add_argument("--durations", nargs="+", choices=DURATIONS, default=list(DURATIONS))
    args = parser.parse_args()

    assets_dir = args.assets_dir.expanduser().resolve()
    output = args.output.expanduser().resolve() if args.output is not None else assets_dir / "fornax_cleaned"
    source_path = assets_dir / "sources" / "fornax_A_nrao.jpg"
    if not source_path.is_file():
        raise SystemExit(
            f"Fornax source not found at {source_path}. Place the optional raster there before rebuilding."
        )

    expected = expected_fornax_source()
    source_sha = sha256(source_path)
    if source_sha != expected["sha256"] or source_path.stat().st_size != int(expected["bytes"]):
        raise SystemExit("optional Fornax raster does not match the source recorded in source_manifest.json")

    output.mkdir(parents=True, exist_ok=True)
    with Image.open(source_path) as image:
        image.load()
        source_rgb = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0

    processed = science_preprocess(source_rgb)
    source_pixels = source_pixels_for_spec(FORNAX_SPEC, FORNAX_SIZE_DEG)
    sky = embed_preprocessed_source(
        processed,
        (NPIX, NPIX),
        (source_pixels, source_pixels),
        total_flux=1.0,
    )
    source_fourier = centered_fft2(sky)
    crop_size = display_crop_size(source_pixels, NPIX)
    sky_name = "fornax_artificial_sky_72arcmin.png"
    display_positive(centre_crop(sky, crop_size)).save(output / sky_name, compress_level=1)

    geometry_manifest = load_geometry_manifest()
    manifest = {
        "schema_version": 1,
        "purpose": "Locally reproduced cleaned-image products for the optional approximately true-scale Fornax A outreach demo.",
        "source_sha256": source_sha,
        "artificial_sky_file": sky_name,
        "artificial_sky_sha256": sha256(output / sky_name),
        "source_size_arcmin": 72.0,
        "field_deg": FIELD_DEG,
        "npix": NPIX,
        "frequency_hz": FREQUENCY_HZ,
        "declination_deg": DECLINATION_DEG,
        "weighting": "natural sparse bilinear operator, cell-normalised measured Fourier values",
        "reconstruction": f"{ITERATIONS}-iteration positive support-constrained Fourier projection",
        "geometry_package_version": geometry_manifest.get("package_version"),
        "products": {stage: {} for stage in args.stages},
    }

    for stage in args.stages:
        for duration in args.durations:
            print(f"Fornax cleaned reproduction: {stage} {duration}", flush=True)
            operator = build_operator(stage, duration)
            observed = operator.grid(source_fourier, cell_normalized=True)
            restored = positive_support_reconstruction(
                observed,
                operator.touched,
                source_pixels,
                iterations=ITERATIONS,
            )
            filename = f"fornax_cleaned_{slug(stage)}_{duration}.png"
            path = output / filename
            display_positive(centre_crop(restored, crop_size)).save(path, compress_level=1)
            manifest["products"][stage][duration] = {
                "file": filename,
                "sha256": sha256(path),
                "accepted_samples": operator.accepted_samples,
                "total_samples": operator.total_samples,
                "touched_uv_cells": int(len(operator.touched)),
            }
            print(f"  {len(operator.touched):,} touched cells", flush=True)

    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote reproduced Fornax cleaned products to {output}")


if __name__ == "__main__":
    main()
