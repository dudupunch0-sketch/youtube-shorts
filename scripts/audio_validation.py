#!/usr/bin/env python3
"""Validate PCM WAV files before they enter the video pipeline."""

from __future__ import annotations

import array
import math
import wave
from pathlib import Path
from typing import Any


class AudioValidationError(ValueError):
    """Raised when an audio file is silent, malformed, or unusable."""


def _samples_from_wav(path: Path) -> tuple[wave._wave_params, list[int]]:
    try:
        handle = wave.open(str(path), "rb")
    except (wave.Error, OSError) as error:
        raise AudioValidationError(f"could not open WAV: {path}: {error}") from error
    with handle as wav:
        params = wav.getparams()
        raw = wav.readframes(params.nframes)
    if params.sampwidth == 1:
        values = [sample - 128 for sample in raw]
    elif params.sampwidth in (2, 4):
        typecode = "h" if params.sampwidth == 2 else "i"
        values_array = array.array(typecode)
        values_array.frombytes(raw)
        if values_array.itemsize != params.sampwidth:
            raise AudioValidationError(f"unsupported sample width: {params.sampwidth}")
        values = list(values_array)
    else:
        raise AudioValidationError(f"unsupported PCM sample width: {params.sampwidth}")
    return params, values


def inspect_wav(path: Path) -> dict[str, Any]:
    params, values = _samples_from_wav(path)
    if params.framerate <= 0 or params.nchannels <= 0 or params.nframes <= 0 or not values:
        raise AudioValidationError(f"empty WAV stream: {path}")
    max_value = float((1 << (8 * params.sampwidth - 1)) - 1)
    peak = max(abs(value) for value in values)
    rms = math.sqrt(sum(float(value) * float(value) for value in values) / len(values))
    peak_normalized = peak / max_value
    rms_normalized = rms / max_value
    constant = min(values) == max(values)
    duration_sec = params.nframes / params.framerate
    return {
        "path": str(path),
        "sample_rate": params.framerate,
        "channels": params.nchannels,
        "sample_width_bytes": params.sampwidth,
        "frames": params.nframes,
        "duration_sec": round(duration_sec, 3),
        "peak_normalized": round(peak_normalized, 6),
        "rms_normalized": round(rms_normalized, 6),
        "constant_signal": constant,
        "finite": True,
        "non_silent": peak_normalized >= 0.001 and rms_normalized >= 0.0001 and not constant,
    }


def validate_wav(path: Path, minimum_duration_sec: float = 0.05) -> dict[str, Any]:
    metrics = inspect_wav(path)
    if metrics["duration_sec"] < minimum_duration_sec:
        raise AudioValidationError(f"audio is too short: {path} ({metrics['duration_sec']}s)")
    if not metrics["finite"]:
        raise AudioValidationError(f"audio contains non-finite samples: {path}")
    if not metrics["non_silent"]:
        raise AudioValidationError(
            f"audio is silent or constant: {path} "
            f"(peak={metrics['peak_normalized']}, rms={metrics['rms_normalized']})"
        )
    return metrics
