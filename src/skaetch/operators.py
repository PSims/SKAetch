"""Frozen sparse Fourier operators used by the SKAetch exhibit."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import as_file, files
from typing import Final, Literal

import numpy as np

from skaetch.geometry import STAGES
from skaetch.imaging import centered_ifft2

OperatorMode = Literal["outreach", "science"]
Duration = Literal["snapshot", "6h"]

DURATIONS: Final[tuple[str, ...]] = ("snapshot", "6h")
FREQUENCY_HZ: Final[float] = 150e6
DECLINATION_DEG: Final[float] = -26.7
SOURCE_SIZE_DEG: Final[float] = 0.10
OUTREACH_NPIX: Final[int] = 2048
OUTREACH_FIELD_DEG: Final[float] = 1.5
SCIENCE_NPIX: Final[int] = 1024
SCIENCE_FIELD_DEG: Final[float] = 0.7

_DELTAS: Final[tuple[tuple[int, int], ...]] = (
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1), (0, 0), (0, 1),
    (1, -1), (1, 0), (1, 1),
)
_DELTA_INDEX: Final[dict[tuple[int, int], int]] = {delta: i for i, delta in enumerate(_DELTAS)}
_OFFSETS: Final[tuple[tuple[int, int], ...]] = ((0, 0), (0, 1), (1, 0), (1, 1))


@dataclass(frozen=True)
class OperatorSpec:
    """Grid and weighting definition for one frozen-operator family."""

    mode: OperatorMode
    weighting: Literal["equal-cell", "natural"]
    npix: int
    field_deg: float
    source_size_deg: float = SOURCE_SIZE_DEG


OUTREACH_SPEC: Final[OperatorSpec] = OperatorSpec(
    mode="outreach",
    weighting="equal-cell",
    npix=OUTREACH_NPIX,
    field_deg=OUTREACH_FIELD_DEG,
)
SCIENCE_SPEC: Final[OperatorSpec] = OperatorSpec(
    mode="science",
    weighting="natural",
    npix=SCIENCE_NPIX,
    field_deg=SCIENCE_FIELD_DEG,
)


def operator_spec(mode: OperatorMode) -> OperatorSpec:
    """Return the fixed imaging specification for an exhibit image mode."""
    if mode == "outreach":
        return OUTREACH_SPEC
    if mode == "science":
        return SCIENCE_SPEC
    raise ValueError("mode must be 'outreach' or 'science'")


def duration_hour_angles_h(duration: Duration) -> np.ndarray:
    """Return the frozen hour-angle sequence for an operator duration."""
    if duration == "snapshot":
        return np.array([0.0])
    if duration == "6h":
        return np.linspace(-3.0, 3.0, 37)
    raise ValueError("duration must be 'snapshot' or '6h'")


def source_pixels_for_spec(
    spec: OperatorSpec,
    source_size_deg: float = SOURCE_SIZE_DEG,
) -> int:
    """Return the square source size in pixels for an angular source extent."""
    source_size_deg = float(source_size_deg)
    if not np.isfinite(source_size_deg) or source_size_deg <= 0.0:
        raise ValueError("source_size_deg must be finite and positive")
    pixel_deg = float(spec.field_deg) / int(spec.npix)
    return max(16, int(round(source_size_deg / pixel_deg)))


def _stage_slug(stage: str) -> str:
    if stage not in STAGES:
        raise ValueError(f"unknown SKA-Low stage {stage!r}")
    return stage.replace(".", "p").replace("*", "star")


def _operator_filename(stage: str, duration: Duration, mode: OperatorMode) -> str:
    slug = _stage_slug(stage)
    if duration not in DURATIONS:
        raise ValueError(f"unknown duration {duration!r}")
    prefix = "science_operator" if mode == "science" else "operator"
    return f"{prefix}_{slug}_{duration}.npz"


def _operator_dir(mode: OperatorMode):
    operator_spec(mode)
    return files("skaetch").joinpath("data", "operators", mode)


@lru_cache(maxsize=2)
def load_operator_manifest(mode: OperatorMode) -> dict:
    """Load metadata for one family of committed frozen operators."""
    path = _operator_dir(mode).joinpath("manifest.json")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@dataclass
class SparseFourierOperator:
    """Compact local-stencil representation of a frozen sampling operator."""

    spec: OperatorSpec
    touched: np.ndarray
    coeff: np.ndarray
    input_indices: np.ndarray
    accepted_samples: int
    total_samples: int
    total_weight: float | None = None

    def __post_init__(self) -> None:
        self.touched = np.asarray(self.touched, dtype=np.int32)
        self.coeff = np.asarray(self.coeff, dtype=np.float32)
        self.input_indices = np.asarray(self.input_indices, dtype=np.int32)
        if self.touched.ndim != 1:
            raise ValueError("touched must be one-dimensional")
        expected = (len(_DELTAS), len(self.touched))
        if self.coeff.shape != expected or self.input_indices.shape != expected:
            raise ValueError(f"coeff and input_indices must both have shape {expected}")
        if len(self.touched) and np.any(np.diff(self.touched.astype(np.int64)) <= 0):
            raise ValueError("touched Fourier-cell indices must be strictly increasing")
        ncells = self.spec.npix * self.spec.npix
        if np.any(self.touched < 0) or np.any(self.touched >= ncells):
            raise ValueError("touched contains an out-of-range Fourier-cell index")
        if np.any(self.input_indices < 0) or np.any(self.input_indices >= ncells):
            raise ValueError("input_indices contains an out-of-range Fourier-cell index")
        if np.any(~np.isfinite(self.coeff)):
            raise ValueError("coeff must contain only finite values")
        if self.accepted_samples < 0 or self.total_samples < self.accepted_samples:
            raise ValueError("invalid accepted/total sample counts")
        centre = (self.spec.npix // 2) * self.spec.npix + self.spec.npix // 2
        if np.any(self.touched == centre):
            raise ValueError("the frozen operator must not contain the Fourier-origin cell")
        if self.spec.weighting == "natural":
            if self.total_weight is None or not np.isfinite(self.total_weight) or self.total_weight <= 0.0:
                raise ValueError("natural operator requires a positive finite total_weight")
        elif self.total_weight is not None:
            raise ValueError("equal-cell operator must not carry total_weight")

        self.touched.setflags(write=False)
        self.coeff.setflags(write=False)
        self.input_indices.setflags(write=False)

    @classmethod
    def from_npz(cls, path, spec: OperatorSpec) -> "SparseFourierOperator":
        """Load one operator archive eagerly and validate its structure."""
        with np.load(path, allow_pickle=False) as data:
            required = {"touched", "coeff", "input_indices", "accepted_samples", "total_samples"}
            if not required.issubset(data.files):
                missing = sorted(required.difference(data.files))
                raise ValueError(f"operator archive is missing arrays: {missing}")
            total_weight = float(data["total_weight"]) if "total_weight" in data.files else None
            return cls(
                spec=spec,
                touched=np.array(data["touched"], dtype=np.int32, copy=True),
                coeff=np.array(data["coeff"], dtype=np.float32, copy=True),
                input_indices=np.array(data["input_indices"], dtype=np.int32, copy=True),
                accepted_samples=int(data["accepted_samples"]),
                total_samples=int(data["total_samples"]),
                total_weight=total_weight,
            )

    @property
    def density(self) -> np.ndarray:
        """Return the natural sampling density at every touched output cell."""
        if self.spec.weighting != "natural":
            return np.ones(len(self.touched), dtype=np.float32)
        return self.coeff.sum(axis=0, dtype=np.float32)

    @property
    def psf_peak(self) -> float:
        """Return the inverse-FFT central response used for dirty-image normalisation."""
        if self.spec.weighting == "natural":
            assert self.total_weight is not None
            return self.total_weight / float(self.spec.npix * self.spec.npix)
        return len(self.touched) / float(self.spec.npix * self.spec.npix)

    def values(self, source_fourier_grid, *, cell_normalized: bool = False) -> np.ndarray:
        """Apply the compact local stencil and return values at touched cells."""
        source = np.asarray(source_fourier_grid)
        expected_shape = (self.spec.npix, self.spec.npix)
        if source.shape != expected_shape:
            raise ValueError(f"source_fourier_grid must have shape {expected_shape}")
        if np.any(~np.isfinite(source)):
            raise ValueError("source_fourier_grid must contain only finite values")
        if cell_normalized and self.spec.weighting != "natural":
            raise ValueError("cell_normalized is only defined for natural operators")

        coeff = self.coeff
        if cell_normalized:
            density = self.density
            coeff = coeff / (density[None, :] + np.float32(1e-30))

        flat = source.ravel()
        result = np.zeros(len(self.touched), dtype=np.complex64)
        for k in range(len(_DELTAS)):
            result += coeff[k] * flat[self.input_indices[k]].astype(np.complex64)
        return result

    def grid(self, source_fourier_grid, *, cell_normalized: bool = False) -> np.ndarray:
        """Return a full Fourier grid containing the operator's touched-cell values."""
        values = self.values(source_fourier_grid, cell_normalized=cell_normalized)
        grid = np.zeros(self.spec.npix * self.spec.npix, dtype=np.complex64)
        grid[self.touched] = values
        return grid.reshape(self.spec.npix, self.spec.npix)

    def dirty_image(self, source_fourier_grid) -> np.ndarray:
        """Return the PSF-peak-normalised dirty image for this operator weighting."""
        grid = self.grid(source_fourier_grid)
        return np.real(centered_ifft2(grid)) / (self.psf_peak + 1e-30)


@lru_cache(maxsize=20)
def load_frozen_operator(stage: str, duration: Duration, mode: OperatorMode) -> SparseFourierOperator:
    """Load and cache one committed exhibit operator."""
    spec = operator_spec(mode)
    filename = _operator_filename(stage, duration, mode)
    asset = _operator_dir(mode).joinpath(filename)
    with as_file(asset) as path:
        return SparseFourierOperator.from_npz(path, spec)


@dataclass(frozen=True)
class SparseOperatorArrays:
    """Arrays produced by deterministic sparse-operator construction."""

    touched: np.ndarray
    coeff: np.ndarray
    input_indices: np.ndarray
    accepted_samples: int
    total_samples: int
    total_weight: float | None


def build_sparse_operator_from_uv(
    u_lambda,
    v_lambda,
    spec: OperatorSpec,
) -> SparseOperatorArrays:
    """Collapse bilinear visibility sampling and gridding into a local sparse stencil.

    ``u_lambda`` and ``v_lambda`` contain the physical baseline samples only;
    Hermitian conjugates are added here.  Equal-cell operators divide each
    output cell by accumulated sampling density. Natural operators retain the
    accumulated coefficient weight. The exact Fourier-origin cell is cleared.
    """
    u, v = np.broadcast_arrays(np.asarray(u_lambda, dtype=float), np.asarray(v_lambda, dtype=float))
    if np.any(~np.isfinite(u)) or np.any(~np.isfinite(v)):
        raise ValueError("u_lambda and v_lambda must contain only finite values")
    if u.ndim == 1:
        u = u.reshape(1, -1)
        v = v.reshape(1, -1)
    elif u.ndim != 2:
        raise ValueError("u_lambda and v_lambda must be one- or two-dimensional")

    npix = int(spec.npix)
    du = 1.0 / np.deg2rad(float(spec.field_deg))
    coeff = np.zeros((len(_DELTAS), npix * npix), dtype=np.float32)
    density = np.zeros(npix * npix, dtype=np.float32) if spec.weighting == "equal-cell" else None
    accepted = 0
    total = 0

    # Iterate time groups in order and place each physical group immediately
    # before its Hermitian conjugates, matching the frozen exhibit construction.
    for u_group, v_group in zip(u, v, strict=True):
        for uu, vv in ((u_group, v_group), (-u_group, -v_group)):
            gx = uu / du + npix / 2
            gy = vv / du + npix / 2
            ix = np.floor(gx).astype(np.int64)
            iy = np.floor(gy).astype(np.int64)
            fx = gx - ix
            fy = gy - iy
            good = (ix >= 0) & (ix < npix - 1) & (iy >= 0) & (iy < npix - 1)
            total += len(ix)
            accepted += int(np.count_nonzero(good))
            ix = ix[good]
            iy = iy[good]
            fx = fx[good]
            fy = fy[good]

            weights = (
                (1.0 - fx) * (1.0 - fy),
                fx * (1.0 - fy),
                (1.0 - fx) * fy,
                fx * fy,
            )
            indices = (
                iy * npix + ix,
                iy * npix + ix + 1,
                (iy + 1) * npix + ix,
                (iy + 1) * npix + ix + 1,
            )
            if density is not None:
                for weight, index in zip(weights, indices, strict=True):
                    np.add.at(density, index, weight.astype(np.float32))

            for b, (output_y, output_x) in enumerate(_OFFSETS):
                for a, (input_y, input_x) in enumerate(_OFFSETS):
                    k = _DELTA_INDEX[(input_y - output_y, input_x - output_x)]
                    product = (weights[b] * weights[a]).astype(np.float32)
                    np.add.at(coeff[k], indices[b], product)
    centre = (npix // 2) * npix + npix // 2
    coeff[:, centre] = 0.0
    if density is not None:
        density[centre] = 0.0
        touched = np.flatnonzero(density > 0.0).astype(np.int32)
        compact = (coeff[:, touched] / density[touched]).astype(np.float32)
        total_weight = None
    else:
        touched = np.flatnonzero(np.any(coeff != 0.0, axis=0)).astype(np.int32)
        compact = coeff[:, touched].astype(np.float32, copy=False)
        total_weight = float(compact.sum(dtype=np.float64))

    y = (touched // npix).astype(np.int32)
    x = (touched % npix).astype(np.int32)
    input_indices = np.empty((len(_DELTAS), len(touched)), dtype=np.int32)
    for k, (dy, dx) in enumerate(_DELTAS):
        yy = y + dy
        xx = x + dx
        valid = (yy >= 0) & (yy < npix) & (xx >= 0) & (xx < npix)
        index = np.zeros(len(touched), dtype=np.int32)
        index[valid] = (yy[valid] * npix + xx[valid]).astype(np.int32)
        compact[k, ~valid] = 0.0
        input_indices[k] = index

    return SparseOperatorArrays(
        touched=touched,
        coeff=np.array(compact, dtype=np.float32, copy=True),
        input_indices=input_indices,
        accepted_samples=accepted,
        total_samples=total,
        total_weight=total_weight,
    )
