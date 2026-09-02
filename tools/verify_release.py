#!/usr/bin/env python3
"""Check that a SKAetch checkout or wheel is ready for public release."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "README.md",
    "docs/public_release.md",
    "docs/privacy.md",
    "docs/source_provenance.md",
)

FORBIDDEN_TRACKED_PATTERNS = (
    re.compile(r"(^|/)local_assets/", re.IGNORECASE),
    re.compile(r"fornax_A_nrao\.jpg$", re.IGNORECASE),
    re.compile(r"M1Crab_nrao\.jpg$", re.IGNORECASE),
    re.compile(r"(^|/)fornax_cleaned/", re.IGNORECASE),
)

LOCAL_PATH_PATTERN = re.compile(
    r"(?:/(?:Users|home)/[^/\s]+/|[A-Za-z]:\\Users\\[^\\\s]+\\)"
)

TEXT_SUFFIXES = {".md", ".py", ".js", ".html", ".css", ".toml", ".json", ".txt", ".svg"}


def git_tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def validate_required_files() -> int:
    missing = [name for name in REQUIRED_FILES if not (ROOT / name).is_file()]
    if missing:
        raise AssertionError(f"missing public-release files: {missing}")
    return len(REQUIRED_FILES)


def validate_project_metadata() -> int:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    expected = {
        "readme": "README.md",
        "license": "BSD-3-Clause",
    }
    for key, value in expected.items():
        if project.get(key) != value:
            raise AssertionError(f"pyproject project.{key} must be {value!r}")
    licence_files = set(project.get("license-files", ()))
    if not {"LICENSE", "THIRD_PARTY_NOTICES.md"}.issubset(licence_files):
        raise AssertionError("pyproject must package LICENSE and THIRD_PARTY_NOTICES.md")
    urls = project.get("urls", {})
    if urls.get("Repository") != "https://github.com/PSims/SKAetch":
        raise AssertionError("pyproject Repository URL is missing or unexpected")
    return 4


def validate_source_manifest() -> int:
    manifest = json.loads((ROOT / "src/skaetch/data/sources/source_manifest.json").read_text(encoding="utf-8"))
    sources = manifest["sources"]
    expected = {
        "demo_einstein": True,
        "demo_cat": True,
        "demo_fornax": False,
        "demo_crab": False,
    }
    for mode, bundled in expected.items():
        if bool(sources[mode].get("bundled")) != bundled:
            raise AssertionError(f"{mode}: unexpected bundled status")
    if "Public domain" not in sources["demo_einstein"]["licence"]:
        raise AssertionError("Einstein source is no longer recorded as public domain")
    return len(expected) + 1


def validate_tracked_paths(tracked: list[str]) -> int:
    bad = []
    for path in tracked:
        if any(pattern.search(path) for pattern in FORBIDDEN_TRACKED_PATTERNS):
            bad.append(path)
    if bad:
        raise AssertionError(f"optional/private exhibit assets are tracked: {bad}")
    return len(tracked)


def validate_text_paths(tracked: list[str]) -> int:
    candidates = {ROOT / rel for rel in tracked}
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if relative.parts and relative.parts[0] in {".git", ".venv", "build", "dist", "local_assets"}:
            continue
        candidates.add(path)

    checked = 0
    for path in sorted(candidates):
        if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
            continue
        rel = str(path.relative_to(ROOT))
        text = path.read_text(encoding="utf-8")
        if LOCAL_PATH_PATTERN.search(text):
            raise AssertionError(f"machine-specific absolute path found in {rel}")
        checked += 1
    return checked


def validate_wheel(path: Path) -> int:
    if not path.is_file():
        raise AssertionError(f"wheel not found: {path}")
    with zipfile.ZipFile(path) as wheel:
        names = wheel.namelist()
        forbidden = [
            name
            for name in names
            if "fornax_a_nrao.jpg" in name.lower()
            or "m1crab_nrao.jpg" in name.lower()
            or "/fornax_cleaned/" in name.lower()
            or name.lower().startswith("local_assets/")
        ]
        if forbidden:
            raise AssertionError(f"optional NRAO assets leaked into wheel: {forbidden}")
        if not any(name.endswith("LICENSE") or "/LICENSE" in name for name in names):
            raise AssertionError("LICENSE is absent from wheel metadata")
        if not any("THIRD_PARTY_NOTICES.md" in name for name in names):
            raise AssertionError("THIRD_PARTY_NOTICES.md is absent from wheel metadata")
        if not any(name.endswith("skaetch/data/sources/einstein_schmutzer_1921.jpg") for name in names):
            raise AssertionError("bundled Einstein source is absent from wheel")
        return len(names)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path, help="optional built wheel to inspect")
    args = parser.parse_args()

    tracked = git_tracked_files()
    required = validate_required_files()
    metadata = validate_project_metadata()
    source_checks = validate_source_manifest()
    tracked_count = validate_tracked_paths(tracked)
    text_count = validate_text_paths(tracked)

    print(f"PASS release files: {required} required files")
    print(f"PASS package metadata: {metadata} checks")
    print(f"PASS public source manifest: {source_checks} checks")
    print(f"PASS tracked paths: {tracked_count} files, no optional NRAO/local assets")
    print(f"PASS text path hygiene: {text_count} text files")

    if args.wheel is not None:
        wheel_count = validate_wheel(args.wheel.resolve())
        print(f"PASS wheel release boundary: {wheel_count} archive members")

    print("PASS SKAetch public-release checks")


if __name__ == "__main__":
    main()
