"""Audio utilities for Twilio Media Streams integration.

Handles μ-law ↔ PCM conversion and simple voice activity detection.
Twilio sends/receives μ-law encoded audio at 8kHz mono.

Uses pure numpy — no audioop (removed in Python 3.13+).
"""

import base64
import io

import numpy as np
import soundfile as sf

# μ-law lookup tables for fast encoding/decoding
_MULAW_BIAS = 33
_MULAW_MAX = 32635

# Decoding table: μ-law byte → 16-bit PCM sample
_MULAW_DECODE_TABLE = np.zeros(256, dtype=np.int16)
for _i in range(256):
    _val = ~_i
    _sign = _val & 0x80
    _exponent = (_val >> 4) & 0x07
    _mantissa = _val & 0x0F
    _sample = ((_mantissa << 3) + _MULAW_BIAS) << _exponent
    _sample -= _MULAW_BIAS
    if _sign:
        _sample = -_sample
    _MULAW_DECODE_TABLE[_i] = np.int16(_sample)


def _encode_mulaw_sample(sample: int) -> int:
    """Encode a single 16-bit PCM sample to μ-law byte."""
    sign = 0
    if sample < 0:
        sign = 0x80
        sample = -sample
    if sample > _MULAW_MAX:
        sample = _MULAW_MAX
    sample += _MULAW_BIAS

    exponent = 7
    mask = 0x4000
    for exp in range(7, 0, -1):
        if sample & mask:
            exponent = exp
            break
    else:
        exponent = 0

    mantissa = (sample >> (exponent + 3)) & 0x0F
    mulaw_byte = ~(sign | (exponent << 4) | mantissa) & 0xFF
    return mulaw_byte


# Build encoding table for speed
_MULAW_ENCODE_TABLE = np.zeros(65536, dtype=np.uint8)
for _i in range(65536):
    _s = _i if _i < 32768 else _i - 65536  # unsigned to signed
    _MULAW_ENCODE_TABLE[_i] = _encode_mulaw_sample(_s)


def mulaw_to_pcm_bytes(mulaw_data: bytes) -> bytes:
    """Decode μ-law bytes to 16-bit PCM bytes."""
    indices = np.frombuffer(mulaw_data, dtype=np.uint8)
    samples = _MULAW_DECODE_TABLE[indices]
    return samples.tobytes()


def pcm_to_mulaw_bytes(pcm_data: bytes) -> bytes:
    """Encode 16-bit PCM bytes to μ-law bytes."""
    samples = np.frombuffer(pcm_data, dtype=np.int16)
    # Use view as uint16 for table lookup
    indices = samples.view(np.uint16)
    mulaw = _MULAW_ENCODE_TABLE[indices]
    return mulaw.tobytes()


def pcm_bytes_to_wav(pcm_data: bytes, sample_rate: int = 8000) -> bytes:
    """Convert raw 16-bit PCM bytes to WAV format for Whisper API."""
    samples = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0
    buf = io.BytesIO()
    sf.write(buf, samples, sample_rate, format="WAV")
    return buf.getvalue()


def _resample(data: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    """Simple resampling using linear interpolation."""
    if source_rate == target_rate:
        return data
    ratio = target_rate / source_rate
    new_length = int(len(data) * ratio)
    indices = np.linspace(0, len(data) - 1, new_length)
    return np.interp(indices, np.arange(len(data)), data.astype(np.float64)).astype(
        data.dtype
    )


def wav_to_mulaw_base64(wav_bytes: bytes, target_rate: int = 8000) -> str:
    """Convert WAV audio to μ-law base64 string for Twilio Media Streams."""
    data, source_rate = sf.read(io.BytesIO(wav_bytes), dtype="int16")

    # Convert to mono if stereo
    if len(data.shape) > 1:
        data = data.mean(axis=1).astype(np.int16)

    # Resample if needed
    if source_rate != target_rate:
        data = _resample(data, source_rate, target_rate)

    mulaw = pcm_to_mulaw_bytes(data.tobytes())
    return base64.b64encode(mulaw).decode("ascii")


def detect_silence(
    pcm_buffer: bytes,
    threshold: int = 500,
    sample_rate: int = 8000,
    silence_duration: float = 1.5,
) -> bool:
    """Check if the tail of the PCM buffer is silence.

    Returns True if the last `silence_duration` seconds are below threshold.
    """
    num_samples = int(sample_rate * silence_duration)
    num_bytes = num_samples * 2  # 16-bit = 2 bytes per sample

    if len(pcm_buffer) < num_bytes:
        return False

    tail = pcm_buffer[-num_bytes:]
    samples = np.frombuffer(tail, dtype=np.int16)
    rms = np.sqrt(np.mean(samples.astype(np.float64) ** 2))

    return rms < threshold
