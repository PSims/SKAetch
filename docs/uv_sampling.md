# Baselines and Earth-rotation UV sampling

SKAetch constructs interferometric samples from the frozen SKA-Low station geometry without changing that geometry. The runtime sampling layer is implemented in `src/skaetch/sampling.py` and uses the validated coordinate transforms in `src/skaetch/uvw.py`.

## Station baselines

For $N$ stations there are

$$
\frac{N(N-1)}{2}
$$

independent unordered station pairs. SKAetch enumerates these pairs in deterministic upper-triangle order and defines each physical baseline as

$$
\mathbf b_{12}=\mathbf r_2-\mathbf r_1.
$$

The committed station layouts contain East/North coordinates only, so baseline construction supplies a zero Up component and produces

$$
\mathbf b_{\mathrm{ENU}}=(E,N,0)
$$

in metres. The opposite vector is not counted as another physical station pair.

## Earth rotation

For a fixed physical baseline and phase-centre declination, Earth rotation changes the source hour angle $H$. The equatorial baseline $\mathbf b_{\mathrm{XYZ}}$ is constant, while the source-aligned projection changes through

$$
\mathbf b_{\mathrm{UVW}}(H)=R(H,\delta)\,\mathbf b_{\mathrm{XYZ}}.
$$

`earth_rotation_uvw_m()` forms one rotation matrix per requested hour angle and applies it to every baseline. It returns the physical projected baselines in metres. `earth_rotation_uvw_lambda()` then divides that result by wavelength. Both functions return arrays with shape

```text
(n_times, n_baselines, 3)
```

For `earth_rotation_uvw_m()` the final axis is $(B_U,B_V,B_W)$ in metres; for `earth_rotation_uvw_lambda()` it is lowercase $(u,v,w)$ in wavelengths.

The sampling API does not impose an observing schedule. Callers provide the hour-angle sequence explicitly. A six-hour synthesis used in SKAetch validation samples from $-3$ h to $+3$ h inclusive at 37 evenly spaced points, matching the six-hour sampling configuration used by the imaging calculations while keeping the runtime function generic.

## Frequency scaling

The physical projected baseline $(B_U,B_V,B_W)$ is independent of observing frequency. Fourier coordinates are

$$
(u,v,w)=\frac{\nu}{c}(B_U,B_V,B_W),
$$

so the same baseline traces a geometrically similar track at every frequency, scaled radially in proportion to $\nu$.

## Conjugate samples

For a real sky-brightness distribution, visibility sampling has the Hermitian relation

$$
V(-u,-v)=V^*(u,v).
$$

Plots may therefore show both each physical baseline sample and its $(-u,-v)$ conjugate counterpart. Those conjugate points are not additional station pairs and are not produced by `station_baselines_enu_m()`.

Weighting, gridding, reconstruction operators, browser track assets and display-density policies are separate layers and are not part of this sampling foundation.

## Validation

Run:

```bash
uv run --group geometry tools/verify_uv_sampling.py
```

The verifier:

- checks the exact $N(N-1)/2$ baseline count and deterministic pair order for every staged array;
- checks `station_2 - station_1` against direct coordinate differences;
- compares vectorized Earth-rotation sampling with fresh per-hour calls to the validated single-baseline UVW transform;
- checks the six-hour synthesis at 150 MHz and declination $-26.7^\circ$ for all five stages;
- checks that the metre-valued projection is frequency-independent and that doubling frequency doubles $(u,v,w)$;
- writes SKAetch-generated six-hour UV inspection plots to the ignored `build/uv-sampling-validation/plots/` directory as PNG and PDF files.

Dense validation plots use deterministic display subsets for readability only. All numerical checks use every physical baseline.
