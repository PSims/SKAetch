# Interferometric UVW geometry

SKAetch converts local SKA-Low station baselines into a source-aligned interferometric coordinate frame in two rotations: local East/North/Up (ENU) to an equatorial Cartesian baseline frame, then equatorial XYZ to UVW for a chosen source hour angle and declination. The implementation is in `src/skaetch/uvw.py`.

The station positions themselves are documented separately in [`array_geometry.md`](array_geometry.md). A baseline uses the `station_2 - station_1` convention. The UVW basis is right-handed, with W pointing towards the phase centre.

SKAetch distinguishes physical projected baselines from Fourier coordinates in wavelength units. Capital baseline components such as $B_X$ and $B_U$ are lengths, normally in metres. Lowercase $u,v,w$ are reserved for the corresponding dimensionless coordinates measured in wavelengths.

## Hour-angle convention

SKAetch uses conventional local astronomical hour angle

$$
H = \mathrm{LST} - \mathrm{RA}.
$$

A source is therefore at transit when $H=0$, east of the meridian at negative hour angle, and west of it at positive hour angle. This convention matters when a UV track is traversed as a function of time, even when a symmetric set of hour-angle samples would contain the same points in reverse order.

## ENU to equatorial XYZ

For a local physical baseline $(E,N,U)$ at latitude $\phi$, SKAetch defines

$$
\begin{aligned}
B_X &= -N\sin\phi + U\cos\phi,\\
B_Y &= E,\\
B_Z &= N\cos\phi + U\sin\phi.
\end{aligned}
$$

The committed SKA-Low geometry contains East/North offsets only, so station-baseline construction uses $U=0$. The default SKA-Low latitude is

$$
\phi=-26.82472208^\circ.
$$

The same ENU-to-XYZ algebra appears in the SKA SDP coordinate-support implementation, whose source cites Thompson, Moran & Swenson, *Interferometry and Synthesis in Radio Astronomy*, 2nd ed., pp. 86–89.

## Equatorial XYZ to source-aligned UVW

For source declination $\delta$ and hour angle $H$, define

$$
R(H,\delta)=
\begin{bmatrix}
\sin H & \cos H & 0\\
-\sin\delta\cos H & \sin\delta\sin H & \cos\delta\\
\cos\delta\cos H & -\cos\delta\sin H & \sin\delta
\end{bmatrix}.
$$

SKAetch forms this matrix explicitly and applies it to the physical equatorial baseline vector:

$$
\begin{bmatrix}B_U\\B_V\\B_W\end{bmatrix}
=
R(H,\delta)
\begin{bmatrix}B_X\\B_Y\\B_Z\end{bmatrix}.
$$

The matrix is a proper rotation: $R R^\mathsf{T}=I$ and $\det R=+1$. It therefore changes only the coordinate basis, not the physical baseline length or its units.

The SKA SDP coordinate documentation gives useful geometric checks for the adopted convention: when W is on the local meridian U points East, and for a zero-declination phase centre at hour angle -6 h, W points due East.

## From projected baseline to wavelengths

The interferometric coordinates are obtained only after the geometric projection:

$$
(u,v,w)=\frac{1}{\lambda}(B_U,B_V,B_W)
       =\frac{\nu}{c}(B_U,B_V,B_W).
$$

Thus a metre-valued XYZ baseline becomes a metre-valued $(B_U,B_V,B_W)$ baseline under the rotation, while lowercase $(u,v,w)$ depend on observing frequency through $\lambda=c/\nu$.

## Zenith/transit identity

For a planar array at transit, with phase-centre declination equal to the site latitude ($H=0$, $\delta=\phi$, $U=0$), the two rotations reduce exactly to

$$
B_U=E,\qquad B_V=N,\qquad B_W=0.
$$

In wavelengths this becomes $u=E/\lambda$, $v=N/\lambda$, $w=0$. SKAetch uses this transparent identity as an all-stage numerical and visual validation of the transform against the committed station geometry.

Earth-rotation sampling built from this coordinate layer is documented in [`uv_sampling.md`](uv_sampling.md).

## Validation

Run:

```bash
uv run --group geometry tools/verify_uvw_geometry.py
```

The verifier:

- compares `src/skaetch/uvw.py` with a separately expressed literal transformation matrix;
- checks $R R^\mathsf{T}=I$ and $\det R=+1$ over representative hour angles and declinations;
- checks that both coordinate rotations preserve baseline length to floating-point precision;
- checks the zenith/transit identity for AA0.5, AA1, AA2, AA* and AA4;
- checks the hour-angle orientation at transit and at ±6 h for a simple East baseline;
- writes SKAetch-generated zenith UV inspection plots to the ignored `build/uvw-validation/plots/` directory as PNG and PDF files.

The rendered plot bytes are not reproducibility invariants. The numerical equations and geometric identities are the validation targets.

## References

- SKA SDP Python Processing Functions, coordinate-support API: https://developer.skao.int/projects/ska-sdp-func-python/en/latest/ska_sdp_func_api/util/index.html
- SKA SDP published coordinate-support source, including the explicit `enu_to_xyz` and `eci_to_uvw` equations: https://developer.skao.int/projects/ska-sdp-func-python/en/0.5.0/_modules/ska_sdp_func_python/util/coordinate_support.html
- U. Rau, *Convention for UVW calculations in CASA* (NRAO/CASA memo, 2013): https://casa.nrao.edu/Memos/CoordConvention.pdf
- SKAO Low sensitivity-calculator source recording the SKA-Low site coordinates from SKA-TEL-SKO-0000422 revision 04: https://developer.skao.int/projects/ska-ost-senscalc/en/10.1.0/_modules/ska_ost_senscalc/low/calculator.html
- A. R. Thompson, J. M. Moran & G. W. Swenson Jr., *Interferometry and Synthesis in Radio Astronomy*, 2nd ed., Wiley-VCH, 2004, pp. 86–89.
