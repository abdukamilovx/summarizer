"""
Audio preprocessing: noise reduction and speech enhancement.
Cleans audio before sending to Whisper for better transcription
when background music or noise is present.
"""
import numpy as np
from typing import Optional
from utils.logger import log


def bandpass_filter(
    audio: np.ndarray,
    sample_rate: int,
    low_freq: float = 200.0,
    high_freq: float = 4000.0,
    order: int = 5,
) -> np.ndarray:
    """Apply a Butterworth bandpass filter to isolate speech frequencies.

    Speech fundamental: ~85-300 Hz, formants up to ~4kHz.
    This cuts rumbling bass and high-frequency music/noise.
    """
    from scipy.signal import butter, sosfilt

    nyquist = sample_rate / 2.0
    low = max(low_freq / nyquist, 0.001)
    high = min(high_freq / nyquist, 0.999)

    sos = butter(order, [low, high], btype="band", output="sos")
    return sosfilt(sos, audio).astype(np.float32)


def reduce_noise(
    audio: np.ndarray,
    sample_rate: int,
    stationary: bool = False,
    prop_decrease: float = 0.85,
) -> np.ndarray:
    """Reduce background noise using spectral gating (noisereduce library).

    Args:
        stationary: True for constant noise (fan, AC), False for non-stationary (music).
        prop_decrease: How much to reduce noise (0.0-1.0). Higher = more aggressive.
    """
    import noisereduce as nr

    return nr.reduce_noise(
        y=audio,
        sr=sample_rate,
        stationary=stationary,
        prop_decrease=prop_decrease,
        n_fft=2048,
        hop_length=512,
    ).astype(np.float32)


def enhance_speech(
    audio: np.ndarray,
    sample_rate: int,
    enable_bandpass: bool = True,
    enable_noise_reduction: bool = True,
    aggressive: bool = False,
) -> np.ndarray:
    """Full speech enhancement pipeline.

    1. Bandpass filter to isolate speech frequencies
    2. Noise reduction via spectral gating
    3. Normalization

    Args:
        aggressive: If True, uses stronger noise reduction (for loud music).
    """
    if len(audio) == 0:
        return audio

    result = audio.copy()

    # Step 1: Bandpass filter — cut non-speech frequencies
    if enable_bandpass:
        try:
            result = bandpass_filter(result, sample_rate)
        except Exception as e:
            log.warning(f"Bandpass filter failed: {e}")

    # Step 2: Noise reduction
    if enable_noise_reduction:
        try:
            prop = 0.95 if aggressive else 0.85
            result = reduce_noise(
                result,
                sample_rate,
                stationary=False,
                prop_decrease=prop,
            )
        except Exception as e:
            log.warning(f"Noise reduction failed: {e}")

    # Step 3: Normalize
    peak = np.max(np.abs(result))
    if peak > 0.01:
        result = result / peak * 0.95

    return result.astype(np.float32)
