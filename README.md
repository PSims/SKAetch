# SKAetch: an interactive SKA-Low radio interferometry outreach simulator

SKAetch is a local browser-based exhibit for exploring how a radio
interferometer builds an image from incomplete Fourier-plane sampling.  It uses
validated staged SKA-Low station geometries, Earth-rotation synthesis and frozen
sparse imaging operators to turn a camera image or demonstration source into an
interactive radio-imaging experiment.

SKAetch was developed for the University of Cambridge Cavendish Laboratory's
**Physics at Work 2026** outreach exhibition.  The default visitor progression
is:

```text
AA1 snapshot → AA1 6 h → AA2 6 h → AA* 6 h → AA4 6 h
```

SKAetch is an educational interferometry demonstrator designed to make Fourier
sampling and image formation visible.  The Outreach view exposes dirty-image
structure directly; the optional Science image uses an idealised constrained
reconstruction for the controlled artificial-source activity.  See
[`docs/operators_and_reconstruction.md`](docs/operators_and_reconstruction.md)
for the scientific scope, assumptions and intended use.

## Quick start

Requirements:

- Python 3.13 or later;
- [`uv`](https://docs.astral.sh/uv/);
- a modern browser. Camera access is optional.

From a clone of the repository:

```bash
git clone https://github.com/PSims/SKAetch.git
cd SKAetch
uv run skaetch
```

SKAetch starts a loopback-only HTTP server and opens the exhibit in the local
browser.  Camera captures are processed in memory and are not saved by SKAetch.
A bundled Einstein portrait and Cat test pattern provide non-camera routes
through the activity.

For runtime options and the facilitator workflow, see:

- [`docs/live_exhibit.md`](docs/live_exhibit.md)
- [`docs/facilitator_runbook.md`](docs/facilitator_runbook.md)
- [`docs/privacy.md`](docs/privacy.md)

## What is reproduced and validated

The repository contains frozen, validated data and operators for five staged
SKA-Low configurations: AA0.5, AA1, AA2, AA* and AA4.  The implementation is
split into documented layers:

- [`docs/array_geometry.md`](docs/array_geometry.md) — authoritative staged
  station geometry and reproduction from `ska-ost-array-config==4.5.0`;
- [`docs/uvw_geometry.md`](docs/uvw_geometry.md) — ENU → equatorial XYZ → UVW
  coordinate conventions;
- [`docs/uv_sampling.md`](docs/uv_sampling.md) — deterministic baselines and
  Earth-rotation sampling;
- [`docs/imaging.md`](docs/imaging.md) — bilinear Fourier sampling,
  cloud-in-cell gridding and weighting;
- [`docs/preprocessing.md`](docs/preprocessing.md) — deterministic artificial
  source preprocessing;
- [`docs/operators_and_reconstruction.md`](docs/operators_and_reconstruction.md)
  — frozen live operators, constrained reconstruction and regeneration.

The full live-runtime integration check is:

```bash
uv run --group geometry tools/verify_runtime.py
```

Release-specific repository/package checks are:

```bash
uv run tools/verify_release.py
```

The individual scientific validators and reproducible asset builders live under
`tools/`; the documentation above records the corresponding commands and
expected outputs.

## Optional external radio-source images

Fornax A and the Crab Nebula can be added as optional local demonstration
sources.  SKAetch keeps their NRAO raster files outside the public repository
and distribution archives; when installed under the ignored `local_assets/`
directory, the facilitator controls enable them automatically.

See [`docs/source_provenance.md`](docs/source_provenance.md) for expected local
paths, source URLs, hashes and the Fornax cleaned-image regeneration workflow.
The public repository and built wheel contain the complete core exhibit;
installing the optional files adds the real-source examples.

## Privacy and offline operation

The exhibit server accepts loopback hosts only.  Browser requests are confined
to the local SKAetch application, and captured camera frames are processed in
memory.  The technical design and event-use caveats are documented in
[`docs/privacy.md`](docs/privacy.md).

## Licence and third-party material

SKAetch source code and original project assets are distributed under the
**BSD 3-Clause licence**.  See [`LICENSE`](LICENSE).

External source material and upstream geometry provenance are documented in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and
[`docs/source_provenance.md`](docs/source_provenance.md).  The bundled Ferdinand
Schmutzer Einstein image is recorded by Wikimedia Commons as public domain;
optional NRAO rasters remain external to the project distributions.

SKAetch is an independent outreach project as opposed to an SKAO software product.
