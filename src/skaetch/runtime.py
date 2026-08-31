"""In-memory image processing for the live SKAetch outreach exhibit."""

from __future__ import annotations

import base64
import io
import time
from dataclasses import dataclass
from typing import Final

import numpy as np
from matplotlib import colormaps
from PIL import Image

from skaetch.imaging import centered_fft2
from skaetch.operators import (
    OUTREACH_SPEC,
    SCIENCE_SPEC,
    OperatorMode,
    load_frozen_operator,
    operator_spec,
    source_pixels_for_spec,
)
from skaetch.preprocessing import (
    embed_preprocessed_source,
    robust_preprocess,
    science_preprocess,
)
from skaetch.reconstruction import positive_support_reconstruction

IMAGE_MODES: Final[tuple[OperatorMode, ...]] = ("outreach", "science")
DEFAULT_TEST_PATTERN_SIZE_ARCMIN: Final[float] = 12.0
MAX_DECODED_IMAGE_BYTES: Final[int] = 8_000_000
DISPLAY_SIZE_PIXELS: Final[int] = 640


def centre_crop(array: np.ndarray, size: int) -> np.ndarray:
    """Return a centred even-sized square crop from a square array."""
    array = np.asarray(array)
    if array.ndim != 2 or array.shape[0] != array.shape[1]:
        raise ValueError("array must be square and two-dimensional")
    size = min(int(size), array.shape[0] - (array.shape[0] % 2))
    if size < 2:
        raise ValueError("size must be at least 2 pixels")
    if size % 2:
        size -= 1
    centre = array.shape[0] // 2
    half = size // 2
    return array[centre - half : centre + half, centre - half : centre + half]


def display_crop_size(source_pixels: int, npix: int) -> int:
    """Return the exhibit display crop surrounding the artificial source."""
    return int(min(npix, max(96, round(1.30 * int(source_pixels)))))


def _normalise_positive(array: np.ndarray) -> np.ndarray:
    low, high = np.percentile(array, (0.5, 99.5))
    return np.clip((array - low) / (high - low + 1e-30), 0.0, 1.0)


def _normalise_symmetric(array: np.ndarray) -> np.ndarray:
    limit = np.percentile(np.abs(array), 99.5) + 1e-30
    return np.clip((array / limit + 1.0) / 2.0, 0.0, 1.0)


def false_colour_image(values: np.ndarray, *, cmap_name: str = "magma") -> Image.Image:
    """Map a normalized two-dimensional array to an RGB false-colour image."""
    values = np.asarray(values, dtype=float)
    if values.ndim != 2 or np.any(~np.isfinite(values)):
        raise ValueError("values must be a finite two-dimensional array")
    rgb = np.uint8(np.round(255.0 * colormaps[cmap_name](np.clip(values, 0.0, 1.0))[..., :3]))
    return Image.fromarray(rgb)


def display_positive(array: np.ndarray, *, size: int = DISPLAY_SIZE_PIXELS) -> Image.Image:
    return false_colour_image(_normalise_positive(array)).resize((size, size), Image.Resampling.LANCZOS)


def display_symmetric(array: np.ndarray, *, size: int = DISPLAY_SIZE_PIXELS) -> Image.Image:
    return false_colour_image(_normalise_symmetric(array)).resize((size, size), Image.Resampling.LANCZOS)


def pil_to_png_data_url(image: Image.Image) -> str:
    """Encode an in-memory Pillow image as a PNG data URL."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", compress_level=1)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def decode_image_data_url(data_url: str) -> Image.Image:
    """Decode one browser image data URL without writing it to disk."""
    if not isinstance(data_url, str) or not data_url.startswith("data:image/") or "," not in data_url:
        raise ValueError("expected an image data URL")
    header, payload = data_url.split(",", 1)
    if ";base64" not in header:
        raise ValueError("image data URL must use base64 encoding")
    raw = base64.b64decode(payload, validate=True)
    if len(raw) > MAX_DECODED_IMAGE_BYTES:
        raise ValueError("image payload is too large")
    with Image.open(io.BytesIO(raw)) as image:
        image.load()
        return image.convert("RGB")


@dataclass(frozen=True)
class ProcessedPortrait:
    artificial_sky: str
    radio_portrait: str
    timing_ms: dict[str, float]
    stage: str
    duration: str
    image_mode: OperatorMode

    def as_dict(self) -> dict:
        return {
            "artificial_sky": self.artificial_sky,
            "radio_portrait": self.radio_portrait,
            "timing_ms": self.timing_ms,
            "stage": self.stage,
            "duration": self.duration,
            "image_mode": self.image_mode,
        }


class RadioPortraitEngine:
    """Apply the committed frozen operators to visitor or demonstration images."""

    def __init__(self, *, preload: bool = True):
        self._source_cache: dict[tuple[str, str, str, float], tuple[np.ndarray, int, np.ndarray]] = {}
        if preload:
            self.preload()

    def preload(self) -> None:
        from skaetch.geometry import STAGES
        from skaetch.operators import DURATIONS

        for image_mode in IMAGE_MODES:
            for stage in STAGES:
                for duration in DURATIONS:
                    load_frozen_operator(stage, duration, image_mode)

    def process_array(
        self,
        image,
        stage: str,
        duration: str,
        *,
        preprocess_mode: str = "robust",
        image_mode: OperatorMode = "outreach",
        source_size_deg: float = 0.10,
        cache_key: str | None = None,
    ) -> ProcessedPortrait:
        t0 = time.perf_counter()
        spec = operator_spec(image_mode)
        source_size_deg = float(source_size_deg)
        if not np.isfinite(source_size_deg) or source_size_deg <= 0.0:
            raise ValueError("source_size_deg must be finite and positive")

        source_cache_key = None
        if cache_key is not None:
            source_cache_key = (
                str(cache_key),
                preprocess_mode,
                image_mode,
                round(source_size_deg, 8),
            )
        cached = self._source_cache.get(source_cache_key) if source_cache_key is not None else None

        if cached is None:
            if preprocess_mode == "robust":
                processed = robust_preprocess(image)
            elif preprocess_mode == "science":
                processed = science_preprocess(image)
            else:
                raise ValueError(f"unknown preprocess_mode {preprocess_mode!r}")
            t_preprocess = time.perf_counter()

            source_pixels = source_pixels_for_spec(spec, source_size_deg)
            if source_pixels > spec.npix:
                raise ValueError("source angular size does not fit inside the selected imaging field")
            sky = embed_preprocessed_source(
                processed,
                (spec.npix, spec.npix),
                (source_pixels, source_pixels),
                total_flux=1.0,
            ).astype(np.float32)
            # The live exhibit deliberately retains the mature float32 sky
            # representation before the FFT.  The reusable preprocessing API
            # itself remains higher precision.
            source_fourier = centered_fft2(sky)
            t_fft = time.perf_counter()
            if source_cache_key is not None:
                self._source_cache[source_cache_key] = (sky, source_pixels, source_fourier)
        else:
            sky, source_pixels, source_fourier = cached
            t_preprocess = t0
            t_fft = t0

        operator = load_frozen_operator(stage, duration, image_mode)
        if image_mode == "outreach":
            result = operator.dirty_image(source_fourier)
            t_imaging = time.perf_counter()
            t_reconstruction = t_imaging
            result_crop = centre_crop(result, display_crop_size(source_pixels, OUTREACH_SPEC.npix))
            sky_crop = centre_crop(sky, display_crop_size(source_pixels, OUTREACH_SPEC.npix))
            display_result = display_symmetric(result_crop)
        else:
            observed = operator.grid(source_fourier, cell_normalized=True)
            t_imaging = time.perf_counter()
            result = positive_support_reconstruction(observed, operator.touched, source_pixels)
            t_reconstruction = time.perf_counter()
            result_crop = centre_crop(result, display_crop_size(source_pixels, SCIENCE_SPEC.npix))
            sky_crop = centre_crop(sky, display_crop_size(source_pixels, SCIENCE_SPEC.npix))
            display_result = display_positive(result_crop)

        return ProcessedPortrait(
            artificial_sky=pil_to_png_data_url(display_positive(sky_crop)),
            radio_portrait=pil_to_png_data_url(display_result),
            timing_ms={
                "preprocess": round(1000.0 * (t_preprocess - t0), 1),
                "fft_embed": round(1000.0 * (t_fft - t_preprocess), 1),
                "imaging": round(1000.0 * (t_imaging - t_fft), 1),
                "restoration": round(1000.0 * (t_reconstruction - t_imaging), 1),
                "total": round(1000.0 * (t_reconstruction - t0), 1),
            },
            stage=stage,
            duration=duration,
            image_mode=image_mode,
        )

    def process_pil(self, image: Image.Image, stage: str, duration: str, **kwargs) -> ProcessedPortrait:
        array = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
        return self.process_array(array, stage, duration, **kwargs)

    def warmup(self) -> dict[str, float]:
        """Exercise both live processing paths to remove first-request startup cost."""
        y, x = np.mgrid[0:384, 0:384]
        demo = np.zeros((384, 384, 3), dtype=np.float32)
        demo[..., 0] = x / 383.0
        demo[..., 1] = y / 383.0
        demo[..., 2] = 0.5 + 0.25 * np.sin(x / 19.0) * np.cos(y / 23.0)
        demo = np.clip(demo, 0.0, 1.0)

        start = time.perf_counter()
        self.process_array(demo, "AA2", "6h", preprocess_mode="robust", image_mode="outreach")
        outreach_ms = 1000.0 * (time.perf_counter() - start)
        start = time.perf_counter()
        self.process_array(demo, "AA2", "6h", preprocess_mode="robust", image_mode="science")
        science_ms = 1000.0 * (time.perf_counter() - start)
        return {
            "warmup_ms": round(outreach_ms + science_ms, 1),
            "outreach_ms": round(outreach_ms, 1),
            "science_ms": round(science_ms, 1),
        }
