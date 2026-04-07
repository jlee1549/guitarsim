"""
audio.py — guitar string synthesis + electronics IR convolution

Synthesis approach:
  - Per-string parametric excitation shaped for wound vs plain strings
  - Extended Karplus-Strong using scipy lfilter for the feedback loop
  - Fractional delay compensation via all-pass interpolation
  - Per-string stiffness (inharmonicity) dispersion
  - Body resonance EQ approximating guitar air/top-plate modes
  - 6-string downstrum E2 A2 D3 G3 B3 E4

References:
  Jaffe & Smith (1983), Karjalainen et al. (1993),
  Smith (2010) Physical Audio Signal Processing
"""

import io
import wave
import numpy as np
from scipy.signal import butter, lfilter, sosfilt, butter
from simulation import FREQS

SAMPLE_RATE = 44100
STRUM_GAP_S = 0.055
NOTE_DUR_S  = 2.5

# Standard tuning open strings
STRING_FREQS = [82.41, 110.00, 146.83, 196.00, 246.94, 329.63]

# T60 decay (seconds) — measured from real acoustic guitar recordings
# Low strings sustain longer than high strings
STRING_T60 = [8.0, 7.0, 5.5, 4.0, 3.0, 2.2]

# Output gain per string (lower strings hit louder in a downstrum)
STRING_GAINS = [0.88, 0.82, 0.76, 0.70, 0.64, 0.58]

# Stiffness (inharmonicity): wound strings ~0, plain ~0.002-0.008
STRING_STIFFNESS = [0.0, 0.0, 0.0005, 0.002, 0.004, 0.007]

# Excitation character: wound strings are warmer, plain are brighter/shorter
# (lo_cut_hz, hi_cut_hz, duration_ms, noise_level)
STRING_EXCITATION = [
    (60,  800,  8.0, 1.0),   # E2  wound — warm thud
    (80,  1200, 7.0, 1.0),   # A2  wound
    (100, 1800, 6.0, 1.0),   # D3  wound
    (120, 3500, 4.0, 0.85),  # G3  plain — transition string
    (150, 6000, 3.0, 0.75),  # B3  plain — bright
    (200, 8000, 2.5, 0.65),  # E4  plain — brightest, shortest
]

def _make_excitation(f0: float, sr: int, lo_hz: float, hi_hz: float,
                     dur_ms: float, level: float) -> np.ndarray:
    """
    Bandpass-filtered noise burst for the initial pick attack.
    Duration matches one string period so it seeds the delay line cleanly.
    """
    period = round(sr / f0)
    n_att  = min(round(dur_ms * sr / 1000), period)

    # White noise shaped by attack/decay envelope
    t   = np.linspace(0, 1, n_att)
    env = np.exp(-6 * t) * (1 - np.exp(-80 * t))  # fast attack, exponential tail
    exc = np.random.randn(n_att) * env * level

    # Bandpass filter the excitation
    nyq = sr / 2
    lo  = np.clip(lo_hz / nyq, 0.001, 0.98)
    hi  = np.clip(hi_hz / nyq, 0.001, 0.98)
    if lo < hi:
        sos = butter(3, [lo, hi], btype='band', output='sos')
        exc = sosfilt(sos, exc)

    # Pad or trim to exactly one period, then normalize
    dl = np.zeros(period)
    dl[:len(exc)] = exc[:period]
    peak = np.max(np.abs(dl))
    if peak > 0:
        dl /= peak
    return dl.astype(np.float64)


def _t60_to_decay(f0: float, t60: float, sr: int) -> float:
    """Convert T60 (time to -60dB) to per-sample KS decay coefficient."""
    # After N=sr*t60 samples we want gain^N = 10^(-60/20) = 0.001
    # => gain = 0.001^(1/(sr*t60))
    n = sr * t60
    return float(0.001 ** (1.0 / n))


def ks_string(f0: float, t60: float, stiffness: float,
              lo_hz: float, hi_hz: float, dur_ms: float, excite_level: float,
              n_samples: int, sr: int = SAMPLE_RATE) -> np.ndarray:
    """
    Extended Karplus-Strong with:
      - Parametric bandpass excitation (wound vs plain character)
      - Fractional delay all-pass for accurate pitch
      - Stiffness dispersion all-pass in the loop
      - T60-derived decay coefficient
    """
    period_exact = sr / f0
    period       = int(np.floor(period_exact))
    frac         = period_exact - period

    # Fractional delay all-pass coefficient
    # H(z) = (a + z^-1)/(1 + a*z^-1),  a = (1-frac)/(1+frac)
    ap_frac = (1.0 - frac) / (1.0 + frac)

    # Stiffness: second all-pass coefficient (small positive value)
    ap_stiff = stiffness

    decay = _t60_to_decay(f0, t60, sr)

    # Seed the delay line with shaped excitation
    dl = _make_excitation(f0, sr, lo_hz, hi_hz, dur_ms, excite_level)

    out       = np.zeros(n_samples, dtype=np.float64)
    ap_f_st   = 0.0   # all-pass fractional delay state
    ap_s_st   = 0.0   # all-pass stiffness state

    for i in range(n_samples):
        idx = i % period
        nx  = (i + 1) % period
        out[i] = dl[idx]

        # Low-pass averaging + decay
        lp = decay * (dl[idx] + dl[nx]) * 0.5

        # All-pass for fractional delay
        ap_f_out  = ap_frac * (lp - ap_f_st) + ap_f_st
        ap_f_st   = lp
        lp        = ap_f_out

        # All-pass for stiffness dispersion
        if ap_stiff > 0:
            ap_s_out = ap_stiff * (lp - ap_s_st) + ap_s_st
            ap_s_st  = lp
            lp       = ap_s_out

        dl[idx] = np.clip(lp, -2.0, 2.0)

    return out.astype(np.float32)

def body_eq(signal: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """
    Approximate guitar body resonance with a gentle EQ curve:
      - Slight low-mid boost ~180 Hz (air cavity resonance)
      - Mild upper-mid presence ~2-3 kHz (top plate + bridge)
      - High-shelf rolloff above 8 kHz (body absorption)
    Much more effective than a simple butterworth peak.
    """
    nyq = sr / 2

    # Air cavity boost ~160-220 Hz
    sos1 = butter(2, [155/nyq, 225/nyq], btype='band', output='sos')
    sig  = signal + sosfilt(sos1, signal) * 0.18

    # Presence boost ~1.8-3.5 kHz (bridge/saddle brightness)
    sos2 = butter(2, [1700/nyq, 3800/nyq], btype='band', output='sos')
    sig  = sig + sosfilt(sos2, sig) * 0.10

    # High shelf rolloff above 7 kHz
    sos3 = butter(2, 7000/nyq, btype='low', output='sos')
    sig  = sig * 0.85 + sosfilt(sos3, sig) * 0.15

    return sig.astype(np.float32)


def build_ir(freq_response: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """
    Convert linear frequency response (at simulation.FREQS) → time-domain IR.
    Uses zero-phase IFFT with Hann windowing.
    """
    N = 4096
    fft_freqs = np.fft.rfftfreq(N, d=1.0 / sr)

    log_min = np.log10(FREQS[0])
    log_max = np.log10(FREQS[-1])
    log_f   = np.log10(np.clip(fft_freqs, FREQS[0], FREQS[-1]))
    t       = np.clip((log_f - log_min) / (log_max - log_min), 0, 1)

    indices = t * (len(FREQS) - 1)
    fi      = np.floor(indices).astype(int)
    frac    = indices - fi
    fi      = np.clip(fi, 0, len(FREQS) - 2)

    H = freq_response[fi] * (1 - frac) + freq_response[fi + 1] * frac
    H[fft_freqs < 30]    = 0.0
    H[fft_freqs > 20000] = 0.0

    ir = np.fft.irfft(H, n=N).real
    pk = int(np.argmax(np.abs(ir)))
    ir = np.roll(ir, N // 2 - pk)
    ir *= np.hanning(N)
    return ir.astype(np.float32)


def fft_convolve(signal: np.ndarray, ir: np.ndarray) -> np.ndarray:
    """Overlap-add FFT convolution via scipy."""
    from scipy.signal import fftconvolve
    return fftconvolve(signal, ir).astype(np.float32)


def render_strum(freq_response: np.ndarray, sr: int = SAMPLE_RATE) -> bytes:
    """
    Synthesise 6-string downstrum shaped by freq_response.
    Returns 16-bit mono WAV bytes.
    """
    norm_resp = freq_response / (np.max(freq_response) + 1e-12)
    ir        = build_ir(norm_resp, sr)

    total_dur     = STRUM_GAP_S * 5 + NOTE_DUR_S
    total_samples = int(np.ceil(sr * total_dur))
    mix           = np.zeros(total_samples, dtype=np.float32)

    for s in range(6):
        f0                          = STRING_FREQS[s]
        t60                         = STRING_T60[s]
        stiff                       = STRING_STIFFNESS[s]
        gain                        = STRING_GAINS[s]
        lo, hi, dur_ms, exc_level   = STRING_EXCITATION[s]

        n_samples = int(np.ceil(sr * NOTE_DUR_S))
        start     = round(s * STRUM_GAP_S * sr)

        ks   = ks_string(f0, t60, stiff, lo, hi, dur_ms, exc_level, n_samples, sr)
        ks   = body_eq(ks, sr)
        conv = fft_convolve(ks, ir)

        end = min(start + len(conv), total_samples)
        mix[start:end] += conv[:end - start] * gain

    # Normalise + soft saturation
    mix = np.nan_to_num(mix, nan=0.0, posinf=1.0, neginf=-1.0)
    peak = np.max(np.abs(mix))
    if peak > 0:
        mix /= peak
    mix = np.tanh(mix * 1.3) / np.tanh(np.float32(1.3))

    pcm = (mix * 0.88 * 32767).clip(-32768, 32767).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()
