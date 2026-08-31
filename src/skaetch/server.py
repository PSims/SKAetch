"""Loopback-only HTTP server for the live SKAetch browser exhibit."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import threading
import webbrowser
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from PIL import Image

from skaetch.geometry import STAGES
from skaetch.operators import DURATIONS, load_operator_manifest
from skaetch.runtime import (
    DEFAULT_TEST_PATTERN_SIZE_ARCMIN,
    IMAGE_MODES,
    RadioPortraitEngine,
    decode_image_data_url,
)

MAX_REQUEST_BYTES = 10_000_000
SERVER_VERSION = "1"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
DEFAULT_ASSETS_DIR = Path(os.environ.get("SKAETCH_ASSETS_DIR", "local_assets"))


def _package_resource(*parts: str):
    return files("skaetch").joinpath(*parts)


def _asset_key(optional_assets_dir: Path | str | None) -> str:
    if optional_assets_dir is None:
        return ""
    return str(Path(optional_assets_dir).expanduser().resolve())


def _optional_source_path(optional_assets_dir: Path | str | None, filename: str) -> Path | None:
    key = _asset_key(optional_assets_dir)
    if not key:
        return None
    return Path(key) / "sources" / filename


def _fornax_cache_dir(optional_assets_dir: Path | str | None) -> Path | None:
    key = _asset_key(optional_assets_dir)
    if not key:
        return None
    return Path(key) / "fornax_cleaned"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fornax_cache_available(optional_assets_dir: Path | str | None) -> bool:
    cache_dir = _fornax_cache_dir(optional_assets_dir)
    source_path = _optional_source_path(optional_assets_dir, "fornax_A_nrao.jpg")
    if cache_dir is None or source_path is None or not source_path.is_file():
        return False
    manifest_path = cache_dir / "manifest.json"
    if not manifest_path.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("source_sha256") != _sha256(source_path):
            return False
        sky = cache_dir / manifest["artificial_sky_file"]
        if not sky.is_file():
            return False
        for stage in STAGES:
            for duration in DURATIONS:
                if not (cache_dir / manifest["products"][stage][duration]["file"]).is_file():
                    return False
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return False
    return True


@lru_cache(maxsize=8)
def _source_catalog_for_key(optional_assets_key: str) -> dict:
    resource = _package_resource("data", "sources", "catalog.json")
    with resource.open("r", encoding="utf-8") as handle:
        catalog = json.load(handle)

    optional_assets_dir = Path(optional_assets_key) if optional_assets_key else None
    for mode, record in catalog.items():
        optional = bool(record.get("optional_external"))
        if optional:
            path = _optional_source_path(optional_assets_dir, record["filename"])
            source_present = bool(path and path.is_file())
        else:
            source_present = _package_resource("data", "sources", record["filename"]).is_file()

        supported = list(record.get("supported_image_modes", IMAGE_MODES))
        available = supported if source_present else []
        if mode == "demo_fornax" and "science" in available and not _fornax_cache_available(optional_assets_dir):
            available = [value for value in available if value != "science"]

        record["installed"] = bool(available)
        record["available_image_modes"] = available
        record["asset_scope"] = "optional-local" if optional else "bundled"
    return catalog


def source_catalog(optional_assets_dir: Path | str | None = None) -> dict:
    return _source_catalog_for_key(_asset_key(optional_assets_dir))


def _read_json_resource(*parts: str) -> dict:
    resource = _package_resource(*parts)
    with resource.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _png_resource_data_url(resource) -> str:
    return "data:image/png;base64," + base64.b64encode(resource.read_bytes()).decode("ascii")


def _png_path_data_url(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _load_source_image(mode: str, optional_assets_dir: Path | str | None = None) -> Image.Image:
    record = source_catalog(optional_assets_dir)[mode]
    if record.get("optional_external"):
        path = _optional_source_path(optional_assets_dir, record["filename"])
        if path is None or not path.is_file():
            raise ValueError(f"optional demonstration source {record['label']!r} is not installed")
        with Image.open(path) as image:
            image.load()
            return image.convert("RGB")

    resource = _package_resource("data", "sources", record["filename"])
    with resource.open("rb") as handle, Image.open(handle) as image:
        image.load()
        return image.convert("RGB")


def fornax_cleaned_result(
    stage: str,
    duration: str,
    optional_assets_dir: Path | str | None = None,
) -> dict:
    cache_dir = _fornax_cache_dir(optional_assets_dir)
    source_path = _optional_source_path(optional_assets_dir, "fornax_A_nrao.jpg")
    if cache_dir is None or source_path is None or not _fornax_cache_available(optional_assets_dir):
        raise ValueError("Fornax cleaned-image cache is not installed")

    manifest_path = cache_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    record = manifest["products"][stage][duration]
    return {
        "artificial_sky": _png_path_data_url(cache_dir / manifest["artificial_sky_file"]),
        "radio_portrait": _png_path_data_url(cache_dir / record["file"]),
        "timing_ms": {
            "preprocess": 0.0,
            "fft_embed": 0.0,
            "imaging": 0.0,
            "restoration": 0.0,
            "total": 0.0,
        },
        "stage": stage,
        "duration": duration,
        "image_mode": "science",
        "stage_metadata": load_operator_manifest("outreach")["stages"][stage],
        "precomputed": True,
        "reproducible_with": "uv run --group geometry tools/build_fornax_cleaned.py --assets-dir local_assets",
        "precomputed_manifest": str(manifest_path),
        "source_size_arcmin": float(manifest["source_size_arcmin"]),
    }


def runtime_metadata(optional_assets_dir: Path | str | None = None) -> dict:
    outreach = load_operator_manifest("outreach")
    science = load_operator_manifest("science")
    track_manifest = _read_json_resource("web", "assets", "uv_track_manifest.json")
    fornax_manifest = None
    cache_dir = _fornax_cache_dir(optional_assets_dir)
    if cache_dir is not None and _fornax_cache_available(optional_assets_dir):
        fornax_manifest = json.loads((cache_dir / "manifest.json").read_text(encoding="utf-8"))
    return {
        **outreach,
        "demo_sources": source_catalog(optional_assets_dir),
        "image_modes": list(IMAGE_MODES),
        "science_mode": science,
        "uv_track_animation": track_manifest,
        "default_test_pattern_size_arcmin": DEFAULT_TEST_PATTERN_SIZE_ARCMIN,
        "visitor_stage_order": ["AA1", "AA2", "AA*", "AA4"],
        "visitor_story_options": {
            "interferometry": {
                "label": "Build + Earth rotation",
                "states": [["AA1", "snapshot"], ["AA4", "snapshot"], ["AA4", "6h"]],
            },
            "build": {
                "label": "Build the SKA",
                "states": [
                    ["AA1", "snapshot"],
                    ["AA1", "6h"],
                    ["AA2", "6h"],
                    ["AA*", "6h"],
                    ["AA4", "6h"],
                ],
            },
        },
        "default_demo_story": "build",
        "default_fourier_display": "animated",
        "default_image_reveal": "after",
        "earth_rotation_control": (
            "free at every construction stage; Forward/Back preserve the recommended story path"
        ),
        "fornax_cleaned_cache": fornax_manifest,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "SKAetchLocal/1"

    def log_message(self, fmt: str, *args) -> None:
        print("[web] " + (fmt % args))

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True

    def _serve_static(self, relative_path: str) -> None:
        path = PurePosixPath(relative_path)
        if path.is_absolute() or ".." in path.parts:
            self.send_error(403)
            return
        resource = _package_resource("web", *path.parts)
        if not resource.is_file():
            self.send_error(404)
            return
        body = resource.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        try:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            self._json(
                {
                    "ok": True,
                    "version": SERVER_VERSION,
                    "stages": list(STAGES),
                    "durations": list(DURATIONS),
                    "image_modes": list(IMAGE_MODES),
                    "prewarmed": self.server.prewarmed,
                }
            )
            return
        if path == "/api/metadata":
            self._json(runtime_metadata(self.server.optional_assets_dir))
            return
        if path == "/api/prewarm":
            result = self.server.engine.warmup()
            self.server.prewarmed = True
            self._json({"ok": True, **result})
            return
        if path == "/":
            self._serve_static("index.html")
            return
        if path.startswith("/assets/"):
            self._serve_static(path.lstrip("/"))
            return
        if path in ("/app.js", "/styles.css", "/favicon.svg"):
            self._serve_static(path.lstrip("/"))
            return
        if path == "/favicon.ico":
            self._serve_static("favicon.svg")
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/process":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("invalid request size")
            payload = json.loads(self.rfile.read(length))
            stage = payload.get("stage", "AA1")
            duration = payload.get("duration", "snapshot")
            mode = payload.get("mode", "capture")
            image_mode = payload.get("image_mode", "outreach")
            if stage not in STAGES or duration not in DURATIONS:
                raise ValueError("unknown stage or duration")
            if image_mode not in IMAGE_MODES:
                raise ValueError("unknown image mode")

            catalog = source_catalog(self.server.optional_assets_dir)
            if mode in catalog:
                record = catalog[mode]
                if not record.get("installed"):
                    raise ValueError(f"demonstration source {record['label']!r} is not installed")
                supported = record.get("available_image_modes", [])
                if image_mode not in supported:
                    raise ValueError(
                        f"{record['label']} is available in {', '.join(supported) or 'no'} image modes"
                    )
                if mode == "demo_fornax" and image_mode == "science":
                    result = fornax_cleaned_result(stage, duration, self.server.optional_assets_dir)
                    self._json({"ok": True, "source_label": record["label"], **result})
                    return
                image = _load_source_image(mode, self.server.optional_assets_dir)
                source_label = record["label"]
                preprocess_mode = record.get("preprocess", "robust")
                source_size_deg = float(record[f"source_size_arcmin_{image_mode}"]) / 60.0
                cache_key = mode
            elif mode == "capture":
                image = decode_image_data_url(payload["image_data"])
                source_label = "Camera image"
                preprocess_mode = "robust"
                source_size_deg = DEFAULT_TEST_PATTERN_SIZE_ARCMIN / 60.0
                cache_key = None
            else:
                raise ValueError(f"unknown source mode {mode!r}")

            result = self.server.engine.process_pil(
                image,
                stage,
                duration,
                preprocess_mode=preprocess_mode,
                image_mode=image_mode,
                source_size_deg=source_size_deg,
                cache_key=cache_key,
            ).as_dict()
            self._json(
                {
                    "ok": True,
                    "source_label": source_label,
                    "source_size_arcmin": round(source_size_deg * 60.0, 6),
                    "stage_metadata": load_operator_manifest("outreach")["stages"][stage],
                    **result,
                }
            )
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True
        except Exception as exc:
            self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status=400)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the local SKAetch outreach exhibit")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=DEFAULT_ASSETS_DIR,
        help=(
            "directory containing optional local-only assets; default: local_assets "
            "or $SKAETCH_ASSETS_DIR"
        ),
    )
    parser.add_argument("--no-open", action="store_true", help="do not open a browser automatically")
    parser.add_argument("--lazy", action="store_true", help="load frozen operators on first use")
    parser.add_argument("--no-warmup", action="store_true", help="skip processing-path warm-up")
    args = parser.parse_args(argv)
    if args.host not in LOOPBACK_HOSTS:
        parser.error("SKAetch intentionally serves only on loopback; use 127.0.0.1, localhost, or ::1")
    if not 0 < args.port < 65536:
        parser.error("port must lie between 1 and 65535")

    optional_assets_dir = args.assets_dir.expanduser().resolve()
    print("Loading frozen SKA imaging operators...", flush=True)
    engine = RadioPortraitEngine(preload=not args.lazy)
    prewarmed = False
    if not args.no_warmup:
        print("Pre-warming image-processing and reconstruction paths...", flush=True)
        info = engine.warmup()
        prewarmed = True
        print(
            f"Warm-up complete in {info['warmup_ms']} ms "
            f"(Outreach {info['outreach_ms']} ms; Science {info['science_ms']} ms).",
            flush=True,
        )

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.daemon_threads = True
    httpd.engine = engine
    httpd.prewarmed = prewarmed
    httpd.optional_assets_dir = optional_assets_dir
    url = f"http://localhost:{args.port}/"
    print(f"SKAetch running locally at {url}")
    optional = source_catalog(optional_assets_dir)
    enabled = [record["short_label"] for record in optional.values() if record.get("optional_external") and record["installed"]]
    if enabled:
        print(f"Optional local demonstration sources enabled from {optional_assets_dir}: {', '.join(enabled)}")
    else:
        print(f"No optional local demonstration sources enabled from {optional_assets_dir}.")
    print("Camera frames are processed in memory by this local Python process and are not saved.")
    print("Press Ctrl-C to stop.")
    if not args.no_open:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
