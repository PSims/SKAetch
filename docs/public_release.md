# Public release checklist

This checklist is intended for making the SKAetch GitHub repository public and
for preparing the corresponding `v0.1.0` exhibit release.

## Release boundary

A public checkout must work with only the repository contents.  Camera,
Einstein and Cat are the public-safe source paths.  Fornax A, the Crab Nebula
and locally generated Fornax cleaned products remain optional external assets
under ignored `local_assets/` storage and must not be present in Git or a built
wheel.

## Before changing repository visibility

From a clean `main` checkout:

```bash
git status
git --no-pager diff --check
uv lock --check
uv run tools/verify_release.py
uv run --group geometry tools/verify_runtime.py
uv build
```

Then validate the built wheel as well:

```bash
uv run tools/verify_release.py --wheel dist/skaetch-0.1.0-py3-none-any.whl
```

The release verifier checks licence/notices metadata, public source manifests,
forbidden local-asset paths, machine-specific absolute paths, and—when a wheel
is supplied—the absence of optional NRAO rasters/cache products and the presence
of the declared licence files.

The established geometry, UVW, UV-sampling, imaging, preprocessing and frozen
operator validators should also remain green.  Their commands and regeneration
workflows are documented in the corresponding files under `docs/`.

## Fresh-clone check

Before tagging a release, exercise a fresh clone rather than relying only on the
development working tree:

```bash
git clone https://github.com/PSims/SKAetch.git SKAetch-release-check
cd SKAetch-release-check
uv run --group geometry tools/verify_runtime.py
uv run tools/verify_release.py
uv run skaetch
```

Check the camera path if appropriate, the Einstein fallback, the complete
Build-the-SKA visitor progression, New image reset, Facilitator mode, and a
no-network run.

## Tagging

The package version is currently `0.1.0`.  Once the public-safe fresh-clone and
actual exhibit-hardware checks pass, an appropriate first exhibit tag is:

```text
v0.1.0
```

The public release should link to the Physics at Work exhibit context, state the
educational scope clearly, and point readers to `THIRD_PARTY_NOTICES.md` and
`docs/source_provenance.md` for external-source provenance.
