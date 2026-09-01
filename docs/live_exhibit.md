# Live exhibit runtime

SKAetch's live exhibit is a local browser application backed by the committed
Python imaging package.  The browser provides camera capture, visitor controls,
and display animation; all radio-image calculations are performed by the local
Python process using the frozen operators described in
[`operators_and_reconstruction.md`](operators_and_reconstruction.md).

## Start the exhibit

From the repository root:

```bash
uv run skaetch
```

The command loads the frozen operators, pre-warms the Outreach and Science
processing paths, starts a local HTTP server, and opens the exhibit at
`http://localhost:8765/`.

Useful options are:

```bash
uv run skaetch --no-open
uv run skaetch --no-warmup
uv run skaetch --lazy
uv run skaetch --port 8766
uv run skaetch --assets-dir /path/to/local_assets
```

The server intentionally accepts loopback hosts only.  It is not designed to be
a network-facing web service.

## Default visitor story

The current visitor defaults are:

- **Demo story:** Build the SKA
- **Sequence:** AA1 snapshot → AA1 6 h → AA2 6 h → AA* 6 h → AA4 6 h
- **Fourier display:** Animated tracks
- **Image reveal:** After observation
- **Artificial camera/Einstein/Cat source size:** 12 arcmin

The opening AA1 snapshot → AA1 6 h transition introduces Earth-rotation
synthesis.  The intended lesson is not that rotation fixes the small array:
Earth rotation adds sampling directions to the same 120 AA1 station pairs, but
cannot replace the missing diversity of baseline lengths and directions.

Snapshot and six-hour sampling remain freely selectable at every construction
stage.  Forward/Back returns to the recommended visitor sequence after an
improvised duration change.  **New image** clears the retained capture and
restores the complete default visitor state at AA1 snapshot.

## Runtime data flow

For camera, Einstein, Cat and any installed optional radio-source paths:

```text
camera frame or bundled source
        ↓
deterministic source preprocessing
        ↓
source-specific angular scale
        ↓
artificial sky + centred FFT
        ↓
committed frozen sparse operator
        ↓
Outreach dirty image OR optional Science reconstruction
        ↓
false-colour PNG data URL returned to the local browser
```

Fornax A and the Crab Nebula are optional local-only assets rather than
packaged repository files.  By default SKAetch looks under `local_assets/`;
missing optional sources are disabled automatically in the facilitator UI.

Fornax A's optional **Cleaned image** uses a locally generated 1.5° product for
live responsiveness.  With `local_assets/sources/fornax_A_nrao.jpg` installed,
regenerate the cache with:

```bash
uv run --group geometry tools/build_fornax_cleaned.py --assets-dir local_assets
```

This writes under the ignored `local_assets/fornax_cleaned/` directory.

## Display-only Fourier assets

The browser's station-layout images, static Fourier-sampling plots and animated
track JSON are display assets only.  Image formation always uses the complete
frozen operators.

Animated tracks use all baselines through AA2, then deterministic display
subsets of 18,000 AA* and 36,000 AA4 baselines.  Static sampling plots use
24,000 AA* and 48,000 AA4 baselines per hour-angle sample.  The denser display
subsets make the increasing Fourier coverage visible while keeping browser
rendering responsive.

To reproduce the display assets without overwriting the committed files:

```bash
uv run --group geometry tools/build_display_assets.py
```

The default output is `build/display-assets-reproduction/`.

## Validation

The complete runtime integration check is:

```bash
uv run --group geometry tools/verify_runtime.py
```

It verifies bundled-source hashes, confirms that optional external rasters and
Fornax cleaned products are absent from the package, validates any installed
local optional assets, validates the browser track coordinates against the
current corrected UV sampling implementation, starts the actual loopback server
in both public-safe and optional-asset configurations, exercises representative
camera/demo API requests, and checks the visitor defaults and static resources.
