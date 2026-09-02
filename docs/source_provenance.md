# Demonstration-source provenance

The live exhibit includes two bundled demonstration images and can optionally use
additional local-only radio-source rasters.  All are used as brightness
templates for the interferometry activity.  When an optional external NRAO
source is selected, its catalogue credit is displayed in the ordinary visitor
interface as well as in Facilitator controls.

A compact redistribution/provenance summary for the public repository is also
provided in [`../THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md).

## Albert Einstein (1921)

- Photographer: Ferdinand Schmutzer (1870–1928)
- Date: 1921
- Source: Wikimedia Commons, *Albert Einstein 1921 by F Schmutzer*
- Source page:
  https://commons.wikimedia.org/wiki/File:Albert_Einstein_1921_by_F_Schmutzer.jpg
- Recorded status: public domain / Public Domain Mark 1.0
- Repository status: bundled
- Exhibit use: recognisable portrait used as an artificial radio-sky test
  pattern at an intentionally artificial 12-arcmin angular size.

Wikimedia Commons records the work as public domain in its country of origin and
in the United States and identifies the file with the Creative Commons Public
Domain Mark 1.0.

## Fornax A

- Source: NRAO's public *Interferometry Explained* educational activity
- Source page: https://public.nrao.edu/interferometry-explained/
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
ignored by Git.  NRAO's current Media Resources policy states that NRAO-produced
images on its site are licensed under Creative Commons Attribution 4.0, subject
to visible credit and additional checks where a credit identifies third-party
ownership:

https://public.nrao.edu/media-resources/

The *Interferometry Explained* source chooser identifies Fornax A but does not,
in the page text used by SKAetch, provide a file-specific creator/ownership
credit for the raster.  SKAetch therefore treats the source-specific
redistribution status as unresolved and keeps the raster external to the public
repository.

## M1: Crab Nebula

- Source: NRAO's public *Interferometry Explained* educational activity
- Source page: https://public.nrao.edu/interferometry-explained/
- Repository status: optional local-only asset; the raster is not committed or
  packaged by SKAetch
- Exhibit use: contrasting extended nebular morphology
- Angular convention: 6 arcmin, close to its observed several-arcminute extent

The expected local path is:

```text
local_assets/sources/M1Crab_nrao.jpg
```

Its exact byte count and SHA-256 hash are likewise recorded in the source
manifest.  The same conservative redistribution policy described for Fornax A
is used for the Crab raster.

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

Fornax A and Crab controls are enabled automatically when their local rasters
are installed.  Installing the Fornax raster enables the Outreach view;
generating its local cleaned cache additionally enables Cleaned image mode.

To regenerate the local Fornax cleaned cache from an installed raster:

```bash
uv run --group geometry tools/build_fornax_cleaned.py --assets-dir local_assets
```

## Scientific scope

These rasters serve as brightness templates for illustrating Fourier sampling
and image formation.  Their angular-scale conventions are documented
explicitly: real-source scales are adopted where stated, while other source
sizes are outreach choices selected for the activity.  Calibration and WCS are
outside the scope of these templates.
