# Demonstration-source provenance

The live exhibit includes two bundled demonstration images and can optionally use
additional local-only radio-source rasters.  All are used as brightness
templates for the interferometry activity.

## Albert Einstein (1921)

- Photographer: Ferdinand Schmutzer (1870–1928)
- Date: 1921
- Source: Wikimedia Commons, *Albert Einstein 1921 by F Schmutzer*
- Recorded status: public domain / Public Domain Mark 1.0
- Repository status: bundled
- Exhibit use: recognisable portrait used as an artificial radio-sky test
  pattern at an intentionally artificial 12-arcmin angular size.

## Fornax A

- Source: NRAO's public *Interferometry Explained* educational activity
- Repository status: optional local-only asset; the raster is not committed or
  packaged by SKAetch
- Exhibit use: extended double-lobed radio-source morphology
- Angular convention: approximately 72 arcmin east–west on the 1.5° Outreach
  field, motivated by the published low-frequency extent
- Cleaned view: locally generated 1.5° natural-weighted
  positive/support-constrained reconstruction for responsive live switching

The exact expected filename, byte count and SHA-256 hash are recorded in
`src/skaetch/data/sources/source_manifest.json`.  A local exhibit installation
can place the raster at:

```text
local_assets/sources/fornax_A_nrao.jpg
```

The source and derived cleaned products under `local_assets/` are intentionally
ignored by Git.  This keeps the public repository independent of the unresolved
source-specific redistribution question while retaining a reproducible local
exhibit path.

## M1: Crab Nebula

- Source: NRAO's public *Interferometry Explained* educational activity
- Repository status: optional local-only asset; the raster is not committed or
  packaged by SKAetch
- Exhibit use: contrasting extended nebular morphology
- Angular convention: 6 arcmin, close to its observed several-arcminute extent

The expected local path is:

```text
local_assets/sources/M1Crab_nrao.jpg
```

Its exact byte count and SHA-256 hash are likewise recorded in the source
manifest.

## Cat silhouette

- Source: original synthetic exhibit illustration
- Repository status: bundled
- Exhibit use: high-contrast artificial radio-sky test pattern
- Angular convention: deliberately artificial 12 arcmin

## Optional local assets

SKAetch looks for optional assets in `local_assets/` by default.  A different
root can be selected with:

```bash
uv run skaetch --assets-dir /path/to/assets
```

or by setting `SKAETCH_ASSETS_DIR`.

Fornax A and Crab controls are disabled automatically when their local rasters
are absent.  If the Fornax raster is present but its cleaned cache has not been
generated, the Outreach view remains available while the Cleaned image mode is
disabled.

To regenerate the local Fornax cleaned cache from an installed raster:

```bash
uv run --group geometry tools/build_fornax_cleaned.py --assets-dir local_assets
```

## Scientific scope

These rasters are not calibrated attempts to reproduce particular SKA-Low
observations.  They do not carry a calibrated observing model or WCS.  Where a
real-source angular scale is adopted it is documented explicitly; otherwise the
source size is an outreach choice selected for the Fourier-sampling activity.
