# Artificial-source preprocessing

SKAetch converts an input image into a deterministic artificial radio-source
brightness distribution.  This layer is intentionally transparent: it performs
only fixed image conditioning and source embedding, without face detection,
background removal, deblurring, or other content-dependent inference.

## Robust preprocessing

`robust_preprocess()` performs the following operations in order:

1. take the largest centred square crop;
2. convert greyscale, RGB, or RGBA input to luminance;
3. apply mild Gaussian denoising with `sigma = 0.6` pixels;
4. normalise robustly between the 2nd and 98th percentiles;
5. apply contrast-limited adaptive histogram equalisation (CLAHE) with
   `clip_limit = 0.012`, `256` histogram bins, and a kernel size
   `max(16, min(64, floor(min(image_shape)/8)))`;
6. blend 35% of the CLAHE result with 65% of the robustly normalised image;
7. clip the result to `[0, 1]`.

The centre crop is performed before luminance conversion so that a non-square
frame cannot preferentially retain material from one side.  RGB conversion uses
the standard scikit-image luminance transform.  For RGBA input, the first three
channels are treated as RGB and alpha does not modulate artificial radio
brightness.

For an input with negligible 2nd-to-98th-percentile range, the denoised
luminance is clipped directly into `[0, 1]` before the fixed CLAHE blend.  The
pipeline therefore remains finite and deterministic for constant and nearly
constant images.

`robust_preprocess()` does not resize the image.  Resizing belongs to the
artificial-source embedding step, so the conditioning operation can be tested
independently from later choices of source and Fourier-grid size.

## Edge taper and source embedding

`cosine_edge_taper()` uses normalised image coordinates from `-1` to `+1` on
both axes.  Define

```text
r = max(|x|, |y|).
```

The taper is unity for `r <= 0.86`, falls as a half cosine between `r = 0.86`
and `r = 1`, and is zero at the outer boundary.  This box-radius taper reduces
the sharp discontinuity that would otherwise be introduced when a finite source
cutout is embedded in a larger zero-valued sky.

`artificial_radio_source()`:

1. runs the robust preprocessing above;
2. resizes the processed image to a caller-selected source shape using
   anti-aliased interpolation;
3. applies the cosine edge taper;
4. normalises the tapered source to a fixed requested total artificial flux;
5. centres it inside a caller-selected larger sky grid.

The default total flux is one.  Fixing total artificial flux isolates source
morphology from arbitrary optical exposure in the outreach analogy.

The sky and source dimensions remain caller-supplied.  This layer therefore
defines the numerical preprocessing method without fixing the later live
application's deployment-specific image or operator sizes.
