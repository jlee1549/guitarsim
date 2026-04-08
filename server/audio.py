"""
audio.py — guitar string synthesis via Karplus-Strong digital waveguide

Excitation model: triangular string displacement (physical initial condition)
  x[n] = n/p_idx            for 0 <= n < p_idx
  x[n] = (N-n)/(N-p_idx)   for p_idx <= n < N

This is exactly what a guitar string looks like when held by a pick.
It produces the correct 1/n^2 harmonic rolloff and the pluck-point
comb filter analytically — no noise, no filtering required.

KS feedback loop:
  - Averaging LPF (x[n] + x[n-1]) / 2  -> harmonic darkening over time
  - Per-sample decay from T60            -> correct sustain envelope
  - Fractional delay all-pass            -> accurate pitch
  - Stiffness all-pass                   -> inharmonicity on plain strings

Single string output, shaped by electronics frequency response IR.
"""

import io
import wave
import numpy as np
from scipy.signal import butter, sosfilt
from simulation import FREQS

SAMPLE_RATE = 44100
NOTE_DUR_S  = 3.0   # seconds of sustain rendered

# Pluck position as fraction of string from bridge end
# 0.12 = typical pick position in normal playing
DEFAULT_PLUCK_POS = 0.12

# Stiffness per string number (0=low E, 5=high E)
# Wound strings have near-zero stiffness; plain strings have more
STRING_STIFFNESS = [0.0, 0.0, 0.0003, 0.0015, 0.003, 0.005]

# T60 per string (seconds)
STRING_T60 = [7.0, 6.0, 4.5, 3.2, 2.4, 1.8]

# Open string frequencies: E2 A2 D3 G3 B3 E4
OPEN_STRINGS = [82.41, 110.00, 146.83, 196.00, 246.94, 329.63]
STRING_NAMES = ["E2", "A2", "D3", "G3", "B3", "E4"]

def triangular_excitation(period: int, pluck_pos: float) -> np.ndarray:
    """
    Physical triangular string displacement.
    DC-removed: a symmetric triangle has zero mean only when p=0.5;
    at other pluck positions the mean is nonzero and must be subtracted
    or the KS loop accumulates a bias that sounds like static/rumble.
    """
    N     = period
    p_idx = max(1, min(N - 2, round(pluck_pos * N)))
    x     = np.zeros(N)
    x[:p_idx] = np.arange(p_idx) / p_idx
    x[p_idx:] = np.arange(N - p_idx, 0, -1) / (N - p_idx)
    x -= x.mean()          # remove DC bias
    pk = np.max(np.abs(x))
    if pk > 0:
        x /= pk
    return x.astype(np.float64)


def _t60_to_decay(f0: float, t60: float, sr: int) -> float:
    """Per-sample decay: 0.001^(1/(t60*f0)) — 60dB drop at fundamental in t60s."""
    return float(10.0 ** (-3.0 / (t60 * f0)))


def ks_string(
    f0: float,
    t60: float,
    stiffness: float,
    pluck_pos: float,
    n_samples: int,
    sr: int = SAMPLE_RATE,
) -> np.ndarray:
    """
    Karplus-Strong with physical triangular excitation.

    The triangular initial condition gives:
    - Correct 1/n^2 harmonic rolloff (guitar-like timbre from sample 1)
    - Pluck-point comb filter built into the excitation analytically
    - Natural darkening as the averaging LPF attenuates harmonics each pass
    """
    period_exact = sr / f0
    period       = int(np.floor(period_exact))
    frac         = period_exact - period

    # Fractional delay all-pass: H(z) = (a + z^-1) / (1 + a*z^-1)
    ap_frac = (1.0 - frac) / (1.0 + frac)
    decay   = _t60_to_decay(f0, t60, sr)

    # Physical triangular pluck — no noise, no filtering needed
    dl = triangular_excitation(period, pluck_pos)

    ap_f_st = 0.0
    ap_s_st = 0.0

    def _ks_step(idx: int) -> None:
        nonlocal ap_f_st, ap_s_st
        # Average with the PREVIOUS slot (already filtered this pass) — canonical KS
        prev_idx = (idx - 1) % period
        lp = (dl[idx] + dl[prev_idx]) * 0.5 * decay
        ap_f_out = ap_frac * (lp - ap_f_st) + ap_f_st
        ap_f_st  = lp;  lp = ap_f_out
        if stiffness > 0:
            ap_s_out = stiffness * (lp - ap_s_st) + ap_s_st
            ap_s_st  = lp;  lp = ap_s_out
        dl[idx] = np.clip(lp, -2.0, 2.0)

    # Warm-up: several full periods so the filter fully settles
    # and all delay-line slots hold consistent filtered values
    for i in range(period * 10):
        _ks_step(i % period)

    out = np.zeros(n_samples, dtype=np.float64)
    for i in range(n_samples):
        idx    = i % period
        out[i] = dl[idx]
        _ks_step(idx)

    return out.astype(np.float32)

def body_eq(signal: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Approximate guitar body resonance EQ."""
    nyq  = sr / 2.0
    sos1 = butter(2, [150/nyq, 210/nyq], btype='band', output='sos')
    sig  = signal + sosfilt(sos1, signal) * 0.18
    sos2 = butter(2, [1800/nyq, 3500/nyq], btype='band', output='sos')
    sig  = sig + sosfilt(sos2, sig) * 0.07
    sos3 = butter(1, 8000/nyq, btype='low', output='sos')
    sig  = sig * 0.9 + sosfilt(sos3, sig) * 0.1
    return sig.astype(np.float32)


def build_ir(freq_response: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Convert linear freq response (at FREQS) -> windowed zero-phase IR."""
    N         = 4096
    fft_freqs = np.fft.rfftfreq(N, d=1.0 / sr)
    log_min   = np.log10(FREQS[0])
    log_max   = np.log10(FREQS[-1])
    log_f     = np.log10(np.clip(fft_freqs, FREQS[0], FREQS[-1]))
    t         = np.clip((log_f - log_min) / (log_max - log_min), 0, 1)
    indices   = t * (len(FREQS) - 1)
    fi        = np.floor(indices).astype(int)
    frac_     = indices - fi
    fi        = np.clip(fi, 0, len(FREQS) - 2)
    H         = freq_response[fi] * (1 - frac_) + freq_response[fi + 1] * frac_
    H[fft_freqs < 30]    = 0.0
    H[fft_freqs > 20000] = 0.0
    ir = np.fft.irfft(H, n=N).real
    pk = int(np.argmax(np.abs(ir)))
    ir = np.roll(ir, N // 2 - pk)
    ir *= np.hanning(N)
    return ir.astype(np.float32)


def fft_convolve(signal: np.ndarray, ir: np.ndarray) -> np.ndarray:
    from scipy.signal import fftconvolve
    return fftconvolve(signal, ir).astype(np.float32)


def render_pluck(
    freq_response: np.ndarray,
    string_idx: int = 1,          # 0=E2 1=A2 2=D3 3=G3 4=B3 5=E4
    pluck_pos: float = DEFAULT_PLUCK_POS,
    reference_gain: float = 1.0,  # relative to wide-open, preserves vol knob
    sr: int = SAMPLE_RATE,
) -> bytes:
    """
    Synthesise a single plucked string shaped by freq_response.
    Returns 16-bit mono WAV bytes.
    """
    f0    = OPEN_STRINGS[string_idx]
    t60   = STRING_T60[string_idx]
    stiff = STRING_STIFFNESS[string_idx]

    norm_resp = freq_response / (np.max(freq_response) + 1e-12)
    ir        = build_ir(norm_resp, sr)

    n_samples = int(np.ceil(sr * NOTE_DUR_S))
    sig       = ks_string(f0, t60, stiff, pluck_pos, n_samples, sr)

    # Remove DC and apply gentle high-pass (20 Hz) to kill rumble from KS bias
    sig -= sig.mean()
    sos_hp = butter(2, 20.0 / (sr / 2.0), btype='high', output='sos')
    sig    = sosfilt(sos_hp, sig).astype(np.float32)

    sig = body_eq(sig, sr)

    # Final DC removal after body EQ
    sig -= sig.mean()

    conv = fft_convolve(sig, ir)

    conv = np.nan_to_num(conv[:n_samples], nan=0.0)

    # Apply reference gain — preserves volume knob audibility
    conv *= reference_gain

    # Soft limit — no hard normalization
    conv = np.tanh(conv * 1.5) / float(np.tanh(np.float32(1.5)))
    pcm  = (conv * 0.85 * 32767).clip(-32768, 32767).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()
