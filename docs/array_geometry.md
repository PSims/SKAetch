# SKA-Low array geometry

SKAetch includes frozen local station coordinates for five staged SKA-Low array configurations. Keeping the geometry inside the Python package means the simulator can use it without installing the larger SKAO array-configuration software at runtime, and the same files are included when SKAetch is built as a wheel.

| Stage | Stations | Maximum baseline |
| --- | ---: | ---: |
| AA0.5 | 4 | 5.592 km |
| AA1 | 16 | 5.802 km |
| AA2 | 68 | 64.805 km |
| AA* | 307 | 73.393 km |
| AA4 | 512 | 73.442 km |

The CSV files under `src/skaetch/data/geometry/` contain the package-provided station name and local East/North offsets in metres, together with an explicit zero-based row index. The index records the frozen station order; the station name preserves traceability to the staged SKAO configuration. These are station-layout coordinates, not Fourier-plane coordinates. Conversion from station baselines to interferometric UVW coordinates is documented in [`uvw_geometry.md`](uvw_geometry.md).

## Source

The geometry is extracted from `ska-ost-array-config==4.5.0` using the staged `LowSubArray` configurations exposed by that release. For each stage, the reproduction tool reads station names directly from `LowSubArray.array_config.names` and the local ENU station-coordinate array directly from `LowSubArray.array_config.xyz`, retaining both in the package-provided order. Station count and maximum baseline are checked against the corresponding subarray metadata when available.

The upstream references are:

- SKAO, *SKA staged delivery, array assemblies and subarrays*: https://www.skao.int/en/science-users/ska-tools/494/ska-staged-delivery-array-assemblies-and-subarrays
- *SKAO Staged Delivery, Array Assemblies And Layouts*, SKAO-TEL-0002299 Revision 04: https://doi.org/10.5281/zenodo.16951020
- `ska_ost_array_config`: https://gitlab.com/ska-telescope/ost/ska-ost-array-config

The `ska_ost_array_config` software is distributed under the BSD 3-Clause licence. SKAetch is an independent outreach project and is not an SKAO software product.

## Reproducing the geometry

The simulator itself does not depend on `ska-ost-array-config`. Reproduction tooling is kept in the non-runtime `geometry` dependency group in `pyproject.toml`, pinned to the release used for these files. SKAO distributes the package and parts of its dependency chain through its artefact repository, which is configured as an additional `uv` index for this project.

Generate a fresh copy under the ignored `build/` directory with:

```bash
uv run --group geometry tools/generate_array_geometry.py
```

This writes:

- five normalized LF-terminated CSV files containing index, station name and East/North coordinates;
- a deterministic geometry manifest containing source fields, station counts, maximum baselines and file hashes;
- five station-layout figures created directly by SKAetch from the reproduced coordinates, as 300 dpi PNG and vector PDF files.

The layout plots are intended for visual scientific inspection as well as reuse in documentation or presentations. They use equal axis scaling and consistent, readable labelling so the array geometry is not visually distorted. Individual stations are not text-labelled on the figures because doing so would obscure the dense AA* and AA4 layouts. Their rendered bytes are not treated as reproducibility invariants because plotting-library versions and output metadata can change without changing the underlying coordinates.

After inspecting the plots in `build/geometry-reproduction/plots/`, compare the regenerated geometry with the committed package data using:

```bash
uv run tools/verify_array_geometry.py \
  --candidate build/geometry-reproduction/geometry
```

The verifier checks the station names and their order exactly, compares East/North values numerically, checks expected station counts and maximum baselines, and validates both the packaged and regenerated manifests against their files. Coordinate comparison allows only a micrometre-level difference by default. SHA-256 values in the manifests provide normalized-file integrity checks; they are not the scientific definition of the geometry.
