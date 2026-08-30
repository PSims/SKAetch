# Fourier sampling and dirty imaging

SKAetch represents an artificial sky source on a regular small-angle image grid and samples its Fourier transform at continuous interferometric `(u, v)` coordinates. The physical coordinates are supplied by the Earth-rotation sampling layer described in [`uv_sampling.md`](uv_sampling.md); the imaging layer does not implement a separate baseline or UVW calculation.

## Fourier convention

For a two-dimensional image `I`, `centered_fft2()` applies NumPy's unnormalised forward transform with the image origin and zero spatial frequency shifted to their central pixels. Consequently, the zero-frequency Fourier value is the sum of the image pixels.

For an image spanning angular extents `L_y` and `L_x` radians with shape `(N_y, N_x)`, the Fourier axes are obtained with the usual discrete frequencies

```text
v = fftfreq(N_y, d=L_y/N_y)
u = fftfreq(N_x, d=L_x/N_x)
```

and then shifted so that zero frequency lies at the centre. In the small-field interferometric transform, cycles per radian are numerically equivalent to baseline coordinates measured in wavelengths.

## Bilinear sampling at continuous UV coordinates

A physical `(u, v)` sample normally lies between Fourier-grid cells. Let its fractional position inside the surrounding cell be `(f_u, f_v)`, with both fractions in `[0, 1]`. Bilinear interpolation samples the four neighbouring Fourier values using

```text
w00 = (1 - f_u)(1 - f_v)
w10 =      f_u (1 - f_v)
w01 = (1 - f_u)     f_v
w11 =      f_u      f_v
```

so the four weights sum to one. Samples outside the finite Fourier grid are rejected explicitly rather than clipped onto an edge.

## Cloud-in-cell accumulation

Each sampled complex visibility is deposited back onto the same four surrounding Fourier cells with the bilinear weights above. Two grids are accumulated independently:

- the complex visibility sum;
- the real sampling-density sum.

An accepted physical sample therefore contributes a total sampling weight of one. For a real sky brightness distribution, the negative-baseline visibility obeys

```text
V(-u, -v) = conjugate(V(u, v)).
```

`cloud_in_cell_grid(..., include_conjugates=True)` can add that conjugate sample explicitly. Keeping the conjugate operation visible is useful both for validating Hermitian symmetry and for forming real-valued dirty images to floating-point precision.



## Fourier origin

After cloud-in-cell accumulation, SKAetch clears the exact Fourier-origin cell
by default.  The artificial interferometric imaging convention therefore does
not retain a gridded DC/zero-spacing coefficient.  This is the same convention
used for both natural and equal-cell imaging.

The accepted-sample count is recorded before this origin cell is cleared.  For
diagnostic weight-conservation tests, callers can set
`clear_fourier_origin=False` and inspect the raw cloud-in-cell accumulation.

This is a deliberately simple exhibit-imaging convention rather than a general
prescription for production convolutional gridding.

## Natural and equal-cell weighting

The two weighting modes expose a simple educational distinction.

### Natural weighting

Natural weighting retains the accumulated grid directly. Cells reached repeatedly by UV samples therefore contribute in proportion to their accumulated sampling density.

### Equal-cell weighting

For each occupied Fourier cell, equal-cell weighting first divides its accumulated complex value by its accumulated sampling density. Every occupied cell is then assigned unit imaging weight. This removes multiplicity after cell averaging, reducing the dominance of densely sampled cells.

This is an intentionally transparent uniform-like weighting rule. It is not a general-purpose implementation of all weighting schemes used in production radio-interferometric imaging.

## Dirty image and PSF normalisation

The dirty image is the centred inverse Fourier transform of the weighted visibility grid. The point-spread function (PSF) is formed with the same inverse transform applied to the corresponding imaging-weight grid.

Both are divided by the central PSF response. A unit-flux point source at the image centre therefore has unit peak response under either weighting mode. Complex arrays are retained by the API; when the Fourier grids are Hermitian, the imaginary image components should be round-off only.
