# Third-party notices and external-source provenance

SKAetch source code and original project assets are distributed under the
BSD 3-Clause licence in [`LICENSE`](LICENSE), except where material has a
separate status or provenance described below.

## SKA-Low staged array geometry

The frozen station geometry under `src/skaetch/data/geometry/` was generated
from `ska-ost-array-config==4.5.0`, using the staged SKA-Low configurations
provided by that package.  The upstream Python source remains in its own
project and is used through the declared reproduction dependency.

Upstream project:
https://gitlab.com/ska-telescope/ost/ska-ost-array-config

Upstream licence: BSD 3-Clause

Upstream copyright notice: Copyright 2020 SKA Observatory

The scientific source and reproduction procedure for the frozen coordinates are
documented in [`docs/array_geometry.md`](docs/array_geometry.md).

## Albert Einstein portrait

Bundled file:
`src/skaetch/data/sources/einstein_schmutzer_1921.jpg`

Photographer: Ferdinand Schmutzer (1870–1928)

Source page:
https://commons.wikimedia.org/wiki/File:Albert_Einstein_1921_by_F_Schmutzer.jpg

Wikimedia Commons records the work as public domain and identifies it with the
Creative Commons Public Domain Mark 1.0.  The Public Domain Mark describes the
copyright status of the image; it is not the SKAetch software licence.

## Optional NRAO source images

SKAetch can optionally use Fornax A and M1/Crab Nebula raster images from
NRAO's *Interferometry Explained* educational activity:
https://public.nrao.edu/interferometry-explained/

SKAetch keeps those raster files and the locally generated Fornax cleaned
products outside the repository and distribution archives.  The exhibit loads
them from an ignored local asset directory when present.

NRAO's current Media Resources policy states that NRAO-produced images and
videos on its site are licensed under Creative Commons Attribution 4.0,
subject to conditions including visible credit and additional checks where a
credit identifies a third-party creator or institution:
https://public.nrao.edu/media-resources/

SKAetch therefore treats the source-specific ownership and preferred credit
for these exact educational rasters as unresolved.  They remain optional
external assets rather than redistributed project files.  Their expected
filenames and SHA-256 hashes are recorded in
`src/skaetch/data/sources/source_manifest.json` for reproducible local exhibit
use.

## Python dependencies

SKAetch depends on third-party Python packages including NumPy, SciPy,
scikit-image, Matplotlib and Pillow.  Reproduction tooling additionally uses
`ska-ost-array-config`.  These packages are installed separately by the Python
package manager, and each retains its own upstream licence.
