"""
audio.py — Karplus-Strong string synthesis + electronics IR convolution

Produces WAV bytes for a 6-string strum (E2 A2 D3 G3 B3 E4) shaped
by the pickup/electronics frequency response.
"""

import io
import wave
import struct
import numpy as np
from simulation import FREQS


STRING_FREQS  = [82.41, 110.00, 146.83, 196.00, 246.94, 329.63]  # E2–E4
STRING_DECAY  = [0.9992, 0.9991, 0.9990, 0.9988, 0.9986, 0.9984]
STRING_GAINS  = [0.90,   0.84,   0.78,   0.72,   0.66,   0.60]
STRUM_GAP_S   = 0.06   # seconds between strings
NOTE_DUR_S    = 2.2
SAMPLE_RATE   = 44100


def build_ir(freq_response: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """
    Convert a linear frequency response (at FREQS) into a time-domain
    impulse response via IFFT. Returns a windowed, zero-phase IR.
    """
    N = 4096
    # Interpolate log-spaced response onto linear FFT bin frequencies
    fft_freqs = np.fft.rfftfreq(N, d=1.0 / sr)
    log_freqs = np.log10(np.clip(fft_freqs, FREQS[0], FREQS[-1]))
    log_min, log_max = np.log10(FREQS[0]), np.log10(FREQS[-1])
    t = np.clip((log_freqs - log_min) / (log_max - log_min), 0, 1)
    indices = t * (len(FREQS) - 1)
    fi = np.floor(indices).astype(int)
    frac = indices - fi
    fi = np.clip(fi, 0, len(FREQS) - 2)
    H = freq_response[fi] * (1 - frac) + freq_response[fi + 1] * frac
    H[fft_freqs < 30] = 0
    H[fft_freqs > 20000] = 0

    # IFFT → real IR
    ir = np.fft.irfft(H, n=N)

    # Shift to make zero-phase (peak at centre), then Hann window
    pk = np.argmax(np.abs(ir))
    ir = np.roll(ir, N // 2 - pk)
    ir *= np.hanning(N)
    return ir.astype(np.float32)


def ks_string(f0: float, decay: float, n_samples: int, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Karplus-Strong plucked string synthesis."""
    period = round(sr / f0)
    dl = np.random.uniform(-1, 1, period).astype(np.float64)
    # High-pass excitation to remove DC
    dl = np.diff(dl, prepend=dl[0]) * 0.9
    out = np.zeros(n_samples, dtype=np.float64)
    for i in range(n_samples):
        idx, nx = i % period, (i + 1) % period
        out[i] = dl[idx]
        dl[idx] = decay * (dl[idx] + dl[nx]) * 0.5
    return out.astype(np.float32)


def render_strum(freq_response: np.ndarray, sr: int = SAMPLE_RATE) -> bytes:
    """
    Synthesise a 6-string downstrum shaped by freq_response.
    Returns 16-bit PCM WAV bytes.
    """
    norm_resp = freq_response / (np.max(freq_response) + 1e-12)
    ir = build_ir(norm_resp, sr)

    total_dur = STRUM_GAP_S * 5 + NOTE_DUR_S
    total_samples = int(np.ceil(sr * total_dur))
    mix = np.zeros(total_samples, dtype=np.float32)

    for s, (f0, decay, gain) in enumerate(zip(STRING_FREQS, STRING_DECAY, STRING_GAINS)):
        n_samples = int(np.ceil(sr * NOTE_DUR_S))
        start = round(s * STRUM_GAP_S * sr)
        ks = ks_string(f0, decay, n_samples, sr)
        # Convolve with IR using scipy if available, else numpy FFT
        try:
            from scipy.signal import fftconvolve
            conv = fftconvolve(ks, ir)
        except ImportError:
            conv = np.fft.irfft(np.fft.rfft(ks, n=len(ks) + len(ir) - 1) *
                                np.fft.rfft(ir, n=len(ks) + len(ir) - 1))
        end = min(start + len(conv), total_samples)
        mix[start:end] += conv[:end - start] * gain

    # Normalise
    peak = np.max(np.abs(mix))
    if peak > 0:
        mix /= peak
    mix = (mix * 0.85 * 32767).clip(-32768, 32767).astype(np.int16)

    # Pack as WAV
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(mix.tobytes())
    return buf.getvalue()
