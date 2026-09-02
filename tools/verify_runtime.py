#!/usr/bin/env python3
"""Validate the live server, browser assets, and optional local demo sources."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from importlib.resources import files
from pathlib import Path

import numpy as np
from PIL import Image

from skaetch.geometry import STAGES, load_station_coordinates
from skaetch.operators import DECLINATION_DEG, DURATIONS, FREQUENCY_HZ, duration_hour_angles_h, load_operator_manifest
from skaetch.sampling import earth_rotation_uvw_lambda, station_baselines_enu_m

TRACK_CAPS = {"AA0.5": 6, "AA1": 120, "AA2": 2278, "AA*": 18000, "AA4": 36000}
STATIC_CAPS = {"AA*": 24000, "AA4": 48000}
TRACK_SCALE = 30000


def resource(*parts: str):
    return files("skaetch").joinpath(*parts)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_resource(item) -> str:
    return sha256_bytes(item.read_bytes())


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(*parts: str) -> dict:
    with resource(*parts).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_source_assets(optional_assets_dir: Path) -> tuple[int, int, int, int]:
    manifest = load_json("data", "sources", "source_manifest.json")
    catalog = load_json("data", "sources", "catalog.json")
    if set(manifest["sources"]) != set(catalog):
        raise AssertionError("source manifest and catalog contain different source modes")

    bundled_count = bundled_bytes = optional_count = optional_bytes = 0
    for mode, record in manifest["sources"].items():
        packaged = resource("data", "sources", record["file"])
        if record.get("bundled"):
            raw = packaged.read_bytes()
            bundled_count += 1
            bundled_bytes += len(raw)
            if len(raw) != int(record["bytes"]):
                raise AssertionError(f"{mode}: bundled source byte count mismatch")
            if sha256_bytes(raw) != record["sha256"]:
                raise AssertionError(f"{mode}: bundled source SHA-256 mismatch")
        else:
            if packaged.is_file():
                raise AssertionError(f"{mode}: optional external raster must not be packaged")
            local = optional_assets_dir / "sources" / record["file"]
            if local.is_file():
                optional_count += 1
                optional_bytes += local.stat().st_size
                if local.stat().st_size != int(record["bytes"]):
                    raise AssertionError(f"{mode}: optional source byte count mismatch")
                if sha256_path(local) != record["sha256"]:
                    raise AssertionError(f"{mode}: optional source SHA-256 mismatch")
    return bundled_count, bundled_bytes, optional_count, optional_bytes


def validate_fornax_cache(optional_assets_dir: Path) -> tuple[int, int]:
    packaged_cache = resource("data", "fornax_cleaned")
    if packaged_cache.is_dir():
        raise AssertionError("Fornax cleaned cache must not be packaged")

    source = optional_assets_dir / "sources" / "fornax_A_nrao.jpg"
    cache = optional_assets_dir / "fornax_cleaned"
    manifest_path = cache / "manifest.json"
    if not source.is_file() or not manifest_path.is_file():
        return 0, 0

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if sha256_path(source) != manifest["source_sha256"]:
        raise AssertionError("Fornax source hash does not match local cleaned-cache manifest")
    sky = cache / manifest["artificial_sky_file"]
    if sha256_path(sky) != manifest["artificial_sky_sha256"]:
        raise AssertionError("Fornax artificial-sky hash mismatch")
    count = 1
    total_bytes = sky.stat().st_size
    outreach_manifest = load_operator_manifest("outreach")
    for stage in STAGES:
        for duration in DURATIONS:
            record = manifest["products"][stage][duration]
            item = cache / record["file"]
            raw = item.read_bytes()
            if sha256_bytes(raw) != record["sha256"]:
                raise AssertionError(f"Fornax {stage} {duration}: PNG hash mismatch")
            reference = outreach_manifest["operators"][stage][duration]
            for key in ("accepted_samples", "total_samples", "touched_uv_cells"):
                if int(record[key]) != int(reference[key]):
                    raise AssertionError(f"Fornax {stage} {duration}: {key} differs from current sampling topology")
            count += 1
            total_bytes += len(raw)
    if count != 11:
        raise AssertionError(f"expected 11 local Fornax PNG products, found {count}")
    return count, total_bytes


def slug(stage: str) -> str:
    return stage.replace(".", "p").replace("*", "star")


def deterministic_track_indices(stage: str, n_baselines: int) -> np.ndarray:
    cap = min(TRACK_CAPS[stage], n_baselines)
    if cap >= n_baselines:
        return np.arange(n_baselines, dtype=np.int64)
    rng = np.random.default_rng(20260818 + 1009 * STAGES.index(stage))
    out = rng.choice(n_baselines, size=cap, replace=False)
    out.sort()
    return out.astype(np.int64)


def validate_browser_story_copy_and_reset() -> int:
    app = resource("web", "app.js").read_text(encoding="utf-8")
    html = resource("web", "index.html").read_text(encoding="utf-8")

    required_app = (
        "const VISITOR_DEFAULTS={stage:'AA1',duration:'snapshot',demoStory:'build',imageRevealMode:'after',imageMode:'outreach',uvDisplayMode:'animated'};",
        "snapshot:'Can four stations recover the image?'",
        "lessonSnapshot:'With 16 stations, the telescope has only 120 independent station pairs, so many spatial patterns are still unsampled.'",
        "lessonSix:'Earth rotation adds sampling directions, but it cannot replace the missing baseline diversity of a small array.'",
        "Object.assign(state,VISITOR_DEFAULTS)",
        "updateVisitorSourceCredit()",
        "Image source: ${active.credit}",
    )
    for phrase in required_app:
        if phrase not in app:
            raise AssertionError(f"browser story/reset contract missing: {phrase}")

    required_html = (
        "Physics at Work 2026</small>",
        "Build the SKA is the default story:",
        'id="visitorSourceCredit"',
    )
    for phrase in required_html:
        if phrase not in html:
            raise AssertionError(f"browser exhibit copy missing: {phrase}")

    reset_start = app.find("function resetForNewImage(){")
    reset_end = app.find("\nfunction toast", reset_start)
    if reset_start < 0 or reset_end < 0:
        raise AssertionError("could not locate New image reset function")
    reset = app[reset_start:reset_end]
    for phrase in (
        "state.capture=null",
        "state.capturedCameraImage=null",
        "state.mode=null",
        "Object.assign(state,VISITOR_DEFAULTS)",
        "showCaptureScreen()",
    ):
        if phrase not in reset:
            raise AssertionError(f"New image reset no longer enforces: {phrase}")

    return len(required_app) + len(required_html) + 5


def validate_static_display_assets() -> tuple[int, int, int]:
    layout_manifest = load_json("web", "assets", "layout_manifest.json")
    uv_manifest = load_json("web", "assets", "uv_sampling_display_manifest.json")
    track_manifest = load_json("web", "assets", "uv_track_manifest.json")

    for name, record in layout_manifest["products"].items():
        item = resource("web", "assets", name)
        if sha256_resource(item) != record["sha256"]:
            raise AssertionError(f"layout asset {name}: hash mismatch")
        with item.open("rb") as handle, Image.open(handle) as image:
            if image.size != (640, 520):
                raise AssertionError(f"layout asset {name}: unexpected dimensions {image.size}")

    if uv_manifest["colour_semantics"] != {
        "baseline_sample": "#0b648f",
        "complex_conjugate": "#e88426",
    }:
        raise AssertionError("static Fourier colour semantics changed")
    for name, record in uv_manifest["products"].items():
        item = resource("web", "assets", name)
        if sha256_resource(item) != record["sha256"]:
            raise AssertionError(f"static Fourier asset {name}: hash mismatch")
        expected_cap = STATIC_CAPS.get(record["stage"])
        expected = min(expected_cap, record["total_baseline_pairs"]) if expected_cap else record["total_baseline_pairs"]
        if record["display_baseline_pairs_per_hour"] != expected:
            raise AssertionError(f"static Fourier asset {name}: unexpected display density")

    if track_manifest["display_baseline_caps"] != TRACK_CAPS:
        raise AssertionError("animated-track display caps changed")
    return (
        len(layout_manifest["products"]),
        len(uv_manifest["products"]),
        len(track_manifest["stages"]),
    )


def validate_track_coordinates() -> tuple[int, float]:
    manifest = load_json("web", "assets", "uv_track_manifest.json")
    hours = duration_hour_angles_h("6h")
    max_quantization_error = 0.0
    checked = 0
    for stage in STAGES:
        record = manifest["stages"][stage]
        item = resource("web", "assets", record["file"])
        if sha256_resource(item) != record["sha256"]:
            raise AssertionError(f"{stage}: track asset hash mismatch")
        payload = json.loads(item.read_text())
        if payload["coordinate_scale_int16"] != TRACK_SCALE:
            raise AssertionError(f"{stage}: unexpected coordinate scale")

        coordinates = np.asarray(load_station_coordinates(stage), dtype=float)
        baselines = station_baselines_enu_m(coordinates)
        uvw = earth_rotation_uvw_lambda(baselines, hours, DECLINATION_DEG, FREQUENCY_HZ)
        axis_limit = 1.05 * max(
            float(np.max(np.abs(uvw[..., 0]))),
            float(np.max(np.abs(uvw[..., 1]))),
        )
        axis_limit = max(axis_limit, 1.0)
        if abs(payload["axis_limit_klambda"] * 1000.0 - axis_limit) > 2e-8 * axis_limit:
            raise AssertionError(f"{stage}: animated-track axis limit mismatch")

        indices = deterministic_track_indices(stage, len(baselines))
        selected = uvw[:, indices, :2].transpose(1, 0, 2)
        expected = np.clip(
            np.rint(selected / axis_limit * TRACK_SCALE),
            -TRACK_SCALE,
            TRACK_SCALE,
        ).astype(np.int16)
        encoded = base64.b64decode(payload["uv_int16_base64"], validate=True)
        actual = np.frombuffer(encoded, dtype="<i2").reshape(payload["array_shape"])
        if not np.array_equal(actual, expected):
            difference = int(np.max(np.abs(actual.astype(np.int32) - expected.astype(np.int32))))
            raise AssertionError(f"{stage}: animated-track coordinate mismatch ({difference} quantized units)")
        max_quantization_error = max(max_quantization_error, 0.5 * axis_limit / TRACK_SCALE)
        checked += actual.shape[0] * actual.shape[1]
    return checked, max_quantization_error


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_health(base: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base + "/api/health", timeout=2) as response:
                return json.loads(response.read())
        except Exception as exc:
            last_error = exc
            time.sleep(0.15)
    raise RuntimeError(f"server did not become healthy: {last_error}")


def post_json(url: str, payload: dict) -> dict:
    raw = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=raw,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def post_json_expect_400(url: str, payload: dict) -> dict:
    raw = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=raw,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(request, timeout=60)
    except urllib.error.HTTPError as exc:
        if exc.code != 400:
            raise
        return json.loads(exc.read())
    raise AssertionError("request unexpectedly succeeded")


def camera_data_url() -> str:
    y, x = np.indices((96, 128), dtype=np.uint16)
    image = np.empty((96, 128, 3), dtype=np.uint8)
    image[..., 0] = (2 * x).astype(np.uint8)
    image[..., 1] = (2 * y).astype(np.uint8)
    image[..., 2] = ((x + y) % 256).astype(np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(image).save(buffer, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def validate_loopback_server(
    output_dir: Path,
    assets_dir: Path,
    *,
    expect_optional: bool,
) -> tuple[int, int]:
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    log_path = output_dir / ("server-optional.log" if expect_optional else "server-public-safe.log")
    output_dir.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "skaetch.server",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--assets-dir",
                str(assets_dir),
                "--no-open",
                "--no-warmup",
                "--lazy",
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            health = wait_health(base)
            if not health["ok"] or health["stages"] != list(STAGES):
                raise AssertionError("unexpected server health response")

            static_checks = {
                "/": "Make a radio portrait",
                "/app.js": "DEMO_STORIES=",
                "/styles.css": ".capture-screen",
                "/favicon.svg": "<svg",
            }
            for path, needle in static_checks.items():
                with urllib.request.urlopen(base + path, timeout=10) as response:
                    body = response.read().decode("utf-8")
                if needle not in body:
                    raise AssertionError(f"static resource {path}: expected marker not found")

            with urllib.request.urlopen(base + "/api/metadata", timeout=10) as response:
                metadata = json.loads(response.read())
            expected_story = [
                ["AA1", "snapshot"],
                ["AA1", "6h"],
                ["AA2", "6h"],
                ["AA*", "6h"],
                ["AA4", "6h"],
            ]
            if metadata["default_demo_story"] != "build":
                raise AssertionError("Build the SKA is not the visitor default")
            if metadata["visitor_story_options"]["build"]["states"] != expected_story:
                raise AssertionError("default Build the SKA visitor sequence changed")
            if metadata["default_fourier_display"] != "animated" or metadata["default_image_reveal"] != "after":
                raise AssertionError("visitor display defaults changed")
            if not metadata["earth_rotation_control"].startswith("free at every"):
                raise AssertionError("Earth-rotation improvisation control is no longer free")

            demos = metadata["demo_sources"]
            if not demos["demo_einstein"]["installed"] or not demos["demo_cat"]["installed"]:
                raise AssertionError("bundled Einstein/Cat demo sources are unavailable")
            optional_ready = demos["demo_fornax"]["installed"] and demos["demo_crab"]["installed"]
            if optional_ready != expect_optional:
                raise AssertionError("optional source availability does not match the selected asset directory")
            if not expect_optional and (demos["demo_fornax"]["available_image_modes"] or demos["demo_crab"]["available_image_modes"]):
                raise AssertionError("public-safe runtime unexpectedly exposes optional source modes")

            requests = [
                {"stage": "AA1", "duration": "snapshot", "mode": "demo_einstein", "image_mode": "outreach"},
                {"stage": "AA2", "duration": "6h", "mode": "demo_cat", "image_mode": "science"},
                {
                    "stage": "AA1",
                    "duration": "snapshot",
                    "mode": "capture",
                    "image_mode": "outreach",
                    "image_data": camera_data_url(),
                },
            ]
            if expect_optional:
                requests.extend(
                    [
                        {"stage": "AA2", "duration": "6h", "mode": "demo_crab", "image_mode": "science"},
                        {"stage": "AA4", "duration": "6h", "mode": "demo_fornax", "image_mode": "science"},
                    ]
                )
            else:
                failure = post_json_expect_400(
                    base + "/api/process",
                    {"stage": "AA1", "duration": "snapshot", "mode": "demo_crab", "image_mode": "outreach"},
                )
                if failure.get("ok") is not False or "not installed" not in failure.get("error", ""):
                    raise AssertionError("missing optional source did not fail cleanly")

            for payload in requests:
                result = post_json(base + "/api/process", payload)
                if not result.get("ok") or not result["radio_portrait"].startswith("data:image/png;base64,"):
                    raise AssertionError(f"runtime request failed: {payload}")
            return len(static_checks), len(requests)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("build/runtime-validation"),
        help="directory for ignored runtime validation products",
    )
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=Path("local_assets"),
        help="optional local-asset root to validate when present",
    )
    args = parser.parse_args()
    optional_assets_dir = args.assets_dir.expanduser().resolve()

    bundled_count, bundled_bytes, optional_count, optional_bytes = validate_source_assets(optional_assets_dir)
    fornax_count, fornax_bytes = validate_fornax_cache(optional_assets_dir)
    browser_contract_checks = validate_browser_story_copy_and_reset()
    layout_count, static_uv_count, track_stage_count = validate_static_display_assets()
    track_points, quantization_error = validate_track_coordinates()

    empty_assets = (args.output / "empty-assets").resolve()
    empty_assets.mkdir(parents=True, exist_ok=True)
    static_http, public_process_http = validate_loopback_server(
        args.output,
        empty_assets,
        expect_optional=False,
    )

    optional_process_http = 0
    optional_ready = optional_count == 2 and fornax_count == 11
    if optional_ready:
        _, optional_process_http = validate_loopback_server(
            args.output,
            optional_assets_dir,
            expect_optional=True,
        )

    print(f"PASS bundled sources: {bundled_count} files, {bundled_bytes / 1024**2:.2f} MiB")
    if optional_count:
        print(f"PASS optional local sources: {optional_count} files, {optional_bytes / 1024**2:.2f} MiB")
    else:
        print("PASS optional local sources: absent from this installation")
    if fornax_count:
        print(f"PASS local Fornax cleaned cache: {fornax_count} PNGs, {fornax_bytes / 1024**2:.2f} MiB")
    else:
        print("PASS local Fornax cleaned cache: absent from this installation")
    print(f"PASS browser exhibit copy/reset contract: {browser_contract_checks} checks")
    print(
        f"PASS browser display assets: {layout_count} layouts, {static_uv_count} static Fourier plots, "
        f"{track_stage_count} animated-track stages"
    )
    print(
        f"PASS animated-track coordinates: {track_points:,} baseline-time points, "
        f"worst half-quantum <= {quantization_error:.3f} wavelengths"
    )
    print(
        f"PASS public-safe loopback runtime: {static_http} static/API metadata checks, "
        f"{public_process_http} image-processing requests"
    )
    if optional_ready:
        print(f"PASS optional-asset loopback runtime: {optional_process_http} image-processing requests")
    print("PASS SKAetch live exhibit runtime")


if __name__ == "__main__":
    main()
