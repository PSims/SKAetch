# Frozen operators and constrained reconstruction

The live SKAetch exhibit repeatedly applies the same interferometric sampling
patterns to changing artificial sources.  Recomputing the complete bilinear
sampling and cloud-in-cell accumulation for every visitor image would repeat a
large amount of geometry-independent work.  SKAetch therefore stores that
linear mapping as compact **frozen sparse Fourier operators**.

The committed operators are an acceleration of the imaging method described in
[`imaging.md`](imaging.md), not a second UVW convention.  Their construction
uses the authoritative station geometry and the Earth-rotation sampling layer,
then algebraically collapses bilinear source-Fourier sampling and cloud-in-cell
output gridding into a local nine-term stencil.

## Fixed observing configurations

Both operator families use

- observing frequency: 150 MHz;
- declination: -26.7 degrees;
- snapshot sampling: transit (`H = 0`);
- six-hour sampling: 37 equally spaced hour angles from -3 h to +3 h;
- explicit Hermitian conjugate samples;
- the SKAetch convention of clearing the exact Fourier-origin cell.

Every SKA-Low stage (`AA0.5`, `AA1`, `AA2`, `AA*`, and `AA4`) has both a
snapshot and a six-hour operator.

## Sparse local stencil

For each touched output Fourier cell, the frozen operator stores nine
coefficients corresponding to relative source-Fourier offsets

```text
(-1,-1) (-1,0) (-1,+1)
( 0,-1) ( 0,0) ( 0,+1)
(+1,-1) (+1,0) (+1,+1)
```

These coefficients combine two bilinear operations: interpolation of the source
Fourier transform at a continuous `(u, v)` coordinate and deposition of that
sample onto its four neighbouring output cells.  Because each operation reaches
only a 2x2 neighbourhood, their composition reaches at most this 3x3 stencil.

The arrays store only touched output cells and their corresponding source-grid
indices.  Applying an operator therefore consists of nine indexed
multiply-accumulate operations per touched cell rather than repeating the
baseline geometry and gridding calculation.

`tools/build_frozen_operators.py` reproduces the operator arrays from the
committed station geometry and current Earth-rotation sampling implementation.
By default it writes only under `build/`, leaving the committed runtime assets
unchanged.

## Outreach operators

The Outreach family uses a 2048x2048 grid spanning 1.5 degrees and the
**equal-cell** weighting defined in [`imaging.md`](imaging.md).  After the
sampling density has been divided out, each occupied Fourier cell carries equal
imaging weight.  A central unit-flux point source therefore has a dirty-image
peak of one when the inverse transform is divided by

```text
number of touched cells / npix^2.
```

These operators provide the fast dirty-image progression used to show how
additional stations and Earth rotation fill the Fourier plane.

## Science operators

The optional Science family uses a 1024x1024 grid spanning 0.7 degrees and
retains the **natural** accumulated coefficients.  The stored coefficient sum
at each touched cell is its natural sampling density, and the PSF normalisation
uses

```text
total accumulated weight / npix^2.
```

For the constrained reconstruction below, measured Fourier values are first
cell-normalised by this density.  This preserves the sampled complex Fourier
value while avoiding multiplicity-dependent amplitudes in the projection
constraint.

## Positive support-constrained reconstruction

The optional Science image uses a deliberately idealised iterative Fourier
projection.  The activity controls the artificial source construction, so two
strong pieces of prior information are known exactly:

1. radio brightness is non-negative;
2. the source is confined to the central artificial-source box, with a
   three-pixel margin.

Starting from the measured, cell-normalised Fourier grid, each iteration:

1. transforms to the image plane;
2. sets negative pixels to zero;
3. sets pixels outside the known support to zero;
4. transforms back to the Fourier plane;
5. restores the measured values at all touched Fourier cells.

SKAetch performs 20 iterations and applies the positivity/support constraints
once more to the final image.

This is useful in the exhibit because it makes the role of additional prior
information visible and produces a contrasting reconstruction from the same
incomplete Fourier measurements.  It is **not** presented as a generic
production imaging algorithm for SKA observations: a real astronomical sky does
not normally come with an exactly known compact support, and operational radio
imaging must address many additional instrumental and calibration effects.

## Frozen data integrity

The operator manifests under `src/skaetch/data/operators/` record the numerical
configuration, sample/touched-cell counts, and SHA-256 digest of every frozen
archive.  `tools/verify_operators.py` checks those digests, validates the sparse
array structure, independently rebuilds the operators from current geometry and
UV sampling, exercises sparse application and normalisation, and checks the
Science reconstruction against a literal implementation of the projection
steps.

## Regenerating derived outputs

Validation products and reproduced operator archives are written under the
ignored `build/` directory.  The commands below do not modify the committed
frozen operator assets.

To rerun the complete operator and reconstruction validation and regenerate the
inspection plots:

```bash
uv run --group geometry tools/verify_operators.py
```

This writes:

```text
build/operator-validation/plots/outreach_operator_progression.png
build/operator-validation/plots/science_reconstruction.png
```

The validation also checks all 20 committed frozen archives and independently
rebuilds their numerical operators from the committed station geometry and
current Earth-rotation sampling implementation.

To reproduce all frozen operators on disk without overwriting the committed
assets:

```bash
uv run --group geometry tools/build_frozen_operators.py
```

By default this writes the reproduced Outreach and Science archives, together
with a summary containing their counts and SHA-256 digests, under:

```text
build/operator-reproduction/
```

The output covers both operator modes, all five SKA-Low stages, and both the
snapshot and six-hour sampling configurations.

For a quicker check of the serializer and regeneration path, a representative
Outreach and Science pair can instead be generated with:

```bash
uv run --group geometry tools/build_frozen_operators.py \
  --output build/operator-regeneration-check \
  --modes outreach science \
  --stages AA0.5 \
  --durations snapshot
```

This produces:

```text
build/operator-regeneration-check/outreach/operator_AA0p5_snapshot.npz
build/operator-regeneration-check/science/science_operator_AA0p5_snapshot.npz
build/operator-regeneration-check/reproduction_summary.json
```

Because these outputs live under `build/`, running the validation or
regeneration commands should leave the Git working tree clean.
