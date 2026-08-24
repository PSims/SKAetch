# Interferometric UVW geometry

SKAetch converts local SKA-Low station baselines into interferometric UVW coordinates in two explicit rotations: local East/North/Up (ENU) to an equatorial Cartesian baseline frame, then equatorial XYZ to UVW for a chosen source hour angle and declination. The implementation is in `src/skaetch/uvw.py`.

The station positions themselves are documented separately in [`array_geometry.md`](array_geometry.md). A baseline uses the `station_2 - station_1` convention. UVW is right-handed, with W pointing towards the phase centre.

## Hour-angle convention

SKAetch uses conventional local astronomical hour angle

\[
H = \mathrm{LST} - \mathrm{RA}.
\]

A source is therefore at transit when \(H=0\), east of the meridian at negative hour angle, and west of it at positive hour angle. This convention matters when a UV track is traversed as a function of time, even when a symmetric set of hour-angle samples would contain the same points in reverse order.

## ENU to equatorial XYZ

For a local baseline \((E,N,U)\) at latitude \(\phi\), SKAetch defines the intermediate equatorial Cartesian components by

\[
\begin{aligned}
X &= -N\sin\phi + U\cos\phi,\\
Y &= E,\\
Z &= N\cos\phi + U\sin\phi.
\end{aligned}
\]

The committed SKA-Low geometry contains East/North offsets only, so later station-baseline construction will normally use \(U=0\). The default SKA-Low latitude is

\[
\phi=-26.82472208^\circ.
\]

The same ENU-to-XYZ algebra appears in the SKA SDP coordinate-support implementation, whose source cites Thompson, Moran & Swenson, *Interferometry and Synthesis in Radio Astronomy*, 2nd ed., pp. 86–89.

## Equatorial XYZ to UVW

For source declination \(\delta\) and hour angle \(H\),

\[
\begin{bmatrix}u\\v\\w\end{bmatrix}
=
\begin{bmatrix}
\sin H & \cos H & 0\\
-\sin\delta\cos H & \sin\delta\sin H & \cos\delta\\
\cos\delta\cos H & -\cos\delta\sin H & \sin\delta
\end{bmatrix}
\begin{bmatrix}X\\Y\\Z\end{bmatrix}.
\]

The result is in the same length unit as XYZ. Dividing by wavelength gives UVW in wavelengths.

The SKA SDP coordinate documentation gives useful geometric checks for the adopted convention: when W is on the local meridian U points East, and for a zero-declination phase centre at hour angle -6 h, W points due East.

## Zenith/transit identity

For a planar array at transit, with phase-centre declination equal to the site latitude (\(H=0\), \(\delta=\phi\), \(U=0\)), the two rotations reduce exactly to

\[
u=E,\qquad v=N,\qquad w=0.
\]

In wavelengths this becomes \(u=E/\lambda\), \(v=N/\lambda\), \(w=0\). SKAetch uses this transparent identity as an all-stage numerical and visual validation of the transform against the committed station geometry.

## Validation

Run:

```bash
uv run --group geometry tools/verify_uvw_geometry.py
```

The verifier:

- compares `src/skaetch/uvw.py` with a separately expressed literal transformation matrix;
- checks that both rotations preserve baseline length to floating-point precision;
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
