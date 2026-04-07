"""
audio.py — improved guitar string synthesis + electronics IR convolution

Synthesis model:
  - Extended Karplus-Strong with string stiffness (all-pass dispersion filter)
  - Separate pick attack transient (shaped noise burst at onset)
  - Per-string decay tuned to approximate real guitar sustain
  - Body resonance approximation via lightweight comb
  - 6-string downstrum (E2 A2 D3 G3 B3 E4) shaped by electronics IR

Reference: Jaffe & Smith (1983), Karjalainen et al. (1993) extended KS model
"""

import io
import wave
import numpy as np
from simulation import FREQS

STRING_FREQS = [82.41, 110.00, 146.83, 196.00, 246.94, 329.63]
STRING_DECAY = [0.9993, 0.9992, 0.9991, 0.9989, 0.9987, 0.9985]
STRING_GAINS = [0.90,   0.84,   0.78,   0.72,   0.66,   0.60]

# String stiffness coefficient: higher = more inharmonicity (brighter, piano-like)
# Guitar wound strings (low) have less stiffness than plain (high)
STRING_STIFFNESS = [0.0, 0.0, 0.001, 0.002, 0.004, 0.006]

STRUM_GAP_S = 0.055
NOTE_DUR_S  = 2.4
SAMPLE_RATE = 44100


def all_pass_filter(x: np.ndarray, coeff: float) -> np.ndarray:
    """First-order all-pass: H(z) = (coeff + z^-1) / (1 + coeff*z^-1)
    Used for fractional delay and dispersion in extended KS."""
    y = np.zeros_like(x)
    xm1, ym1 = 0.0, 0.0
    for i in range(len(x)):
        y[i] = coeff * (x[i] - ym1) + xm1
        xm1 = x[i]
        ym1 = y[i]
    return y


def ks_string_extended(
    f0: float,
    decay: float,
    stiffness: float,
    n_samples: int,
    sr: int = SAMPLE_RATE,
) -> np.ndarray:
    """
    Extended Karplus-Strong with:
    - Fractional delay via all-pass interpolation for accurate pitch
    - Stiffness dispersion filter in the loop
    - Shaped attack transient (pick noise burst)
    - Dynamic low-pass in the loop (approximates energy loss per cycle)
    """
    # Exact period with fractional part
    period_exact = sr / f0
    period = int(np.floor(period_exact))
    frac = period_exact - period  # fractional delay

    # All-pass coefficient for fractional delay
    ap_coeff = (1 - frac) / (1 + frac)

    # Initial excitation: shaped noise burst simulating pick attack
    # Duration ~3ms, bandpass shaped to emphasise pluck character
    attack_samples = int(0.003 * sr)
    excitation = np.zeros(period, dtype=np.float64)
    if attack_samples <= period:
        burst = np.random.uniform(-1, 1, attack_samples)
        # Shape: fast attack, exponential decay
        env = np.exp(-np.linspace(0, 5, attack_samples))
        burst *= env
        # Mild high-pass to make it click-like (remove DC)
        burst = np.diff(burst, prepend=burst[0])
        excitation[:attack_samples] = burst

    # Add a low-level sustained noise tail (rest of period)
    # This models the string's initial complex motion before settling
    excitation[attack_samples:] = np.random.uniform(-0.08, 0.08, period - attack_samples)

    dl = excitation.copy()

    out = np.zeros(n_samples, dtype=np.float64)
    ap_state = 0.0  # all-pass filter state

    for i in range(n_samples):
        idx = i % period
        nx  = (i + 1) % period
        out[i] = dl[idx]

        # Low-pass (averaging) + decay in loop — simulates per-cycle energy loss
        lp = decay * (dl[idx] + dl[nx]) * 0.5

        # All-pass for fractional delay (corrects pitch)
        ap_out = ap_coeff * (lp - ap_state) + dl[idx]
        ap_state = ap_out

        # Stiffness dispersion: second all-pass in series
        if stiffness > 0:
            ap_out = stiffness * ap_out + (1 - stiffness) * lp

        dl[idx] = ap_out

    return out.astype(np.float32)

def body_resonance(signal: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """
    Lightweight body resonance approximation.
    Models the guitar body's main air resonance (~100 Hz) and
    top plate resonance (~200–300 Hz) as a simple IIR comb.
    This is very approximate — a proper body model uses measured IRs.
    """
    try:
        from scipy.signal import lfilter, butter
        # Mild low-mid boost around 180–220 Hz (body air resonance)
        b, a = butter(2, [160 / (sr / 2), 260 / (sr / 2)], btype='band')
        boost = lfilter(b, a, signal) * 0.15
        return signal + boost
    except ImportError:
        return signal  # graceful fallback if scipy unavailable


def build_ir(freq_response: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """
    Convert linear freq response (at simulation.FREQS) to time-domain IR via IFFT.
    Returns windowed, zero-phase IR.
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
    H[fft_freqs < 30]    = 0
    H[fft_freqs > 20000] = 0

    ir = np.fft.irfft(H, n=N).real
    pk = int(np.argmax(np.abs(ir)))
    ir = np.roll(ir, N // 2 - pk)
    ir *= np.hanning(N)
    return ir.astype(np.float32)


def fft_convolve(signal: np.ndarray, ir: np.ndarray) -> np.ndarray:
    """Overlap-add FFT convolution."""
    try:
        from scipy.signal import fftconvolve
        return fftconvolve(signal, ir).astype(np.float32)
    except ImportError:
        n = len(signal) + len(ir) - 1
        return np.fft.irfft(
            np.fft.rfft(signal, n=n) * np.fft.rfft(ir, n=n), n=n
        ).real.astype(np.float32)


def render_strum(freq_response: np.ndarray, sr: int = SAMPLE_RATE) -> bytes:
    """
    Synthesise a 6-string downstrum shaped by freq_response.
    Returns 16-bit mono PCM WAV bytes.
    """
    norm_resp = freq_response / (np.max(freq_response) + 1e-12)
    ir = build_ir(norm_resp, sr)

    total_dur     = STRUM_GAP_S * 5 + NOTE_DUR_S
    total_samples = int(np.ceil(sr * total_dur))
    mix           = np.zeros(total_samples, dtype=np.float32)

    for s, (f0, decay, stiff, gain) in enumerate(
        zip(STRING_FREQS, STRING_DECAY, STRING_STIFFNESS, STRING_GAINS)
    ):
        n_samples = int(np.ceil(sr * NOTE_DUR_S))
        start     = round(s * STRUM_GAP_S * sr)

        ks   = ks_string_extended(f0, decay, stiff, n_samples, sr)
        ks   = body_resonance(ks, sr)
        conv = fft_convolve(ks, ir)

        end = min(start + len(conv), total_samples)
        mix[start:end] += conv[:end - start] * gain

    # Normalise with soft knee to avoid hard clipping
    peak = np.max(np.abs(mix))
    if peak > 0:
        mix /= peak
    mix = np.tanh(mix * 1.2) / np.tanh(1.2)  # gentle saturation

    pcm = (mix * 0.88 * 32767).clip(-32768, 32767).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()
