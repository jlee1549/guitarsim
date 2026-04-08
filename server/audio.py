# SPDX-License-Identifier: BSD-3-Clause
"""
audio.py — guitar string synthesis via Karplus-Strong digital waveguide

Excitation: triangular string displacement (physical initial condition).
  Produces 1/n^2 harmonic rolloff and pluck-point comb filter analytically.

KS loop:
  - Simple per-period gain (base_decay) for correct T60 — no FIR averaging.
    The two-point FIR y=0.5*(x+prev) runs at SAMPLE rate in original KS,
    not PERIOD rate. Running it at period rate with frac>0 causes catastrophic
    cancellation: gain per period = |cos(pi*frac)| << 1 for high strings.
    E4 frac=0.79 → |cos(pi*0.79)| = 0.59 → -4.6dB per period → dead in 50ms.
  - First-order all-pass for fractional delay (flat magnitude, correct pitch).
  - Optional stiffness all-pass for inharmonicity.
  - Initial FFT spectral taper for differential harmonic decay.
"""

import io, wave
import numpy as np
from scipy.signal import butter, sosfilt
from simulation import FREQS

SAMPLE_RATE = 44100
NOTE_DUR_S  = 3.0
DEFAULT_PLUCK_POS = 0.12

STRING_STIFFNESS = [0.0, 0.0, 0.0003, 0.0015, 0.003, 0.005]

STRING_LOSS = [0.30, 0.28, 0.25, 0.18, 0.15, 0.12]
STRING_BRIGHTNESS = STRING_LOSS   # alias

STRING_T60 = [7.0, 6.0, 4.5, 4.0, 5.0, 6.0]

OPEN_STRINGS = [82.41, 110.00, 146.83, 196.00, 246.94, 329.63]
STRING_NAMES = ["E2", "A2", "D3", "G3", "B3", "E4"]


def triangular_excitation(period: int, pluck_pos: float) -> np.ndarray:
    N     = period
    p_idx = max(1, min(N - 2, round(pluck_pos * N)))
    # Velocity excitation: magnetic pickup measures string velocity, not displacement.
    # Velocity of plucked string at release = derivative of triangular displacement:
    # constant positive on nut side, constant negative on bridge side.
    # This gives 1/n harmonic rolloff (vs 1/n^2 for displacement), matching
    # the bright attack of a real electric guitar string.
    x = np.zeros(N)
    x[:p_idx] =  1.0 / p_idx
    x[p_idx:] = -1.0 / (N - p_idx)
    x -= x.mean()
    pk = np.max(np.abs(x))
    if pk > 0: x /= pk
    return x.astype(np.float64)


def _t60_to_decay(f0: float, t60: float, sr: int) -> float:
    return float(10.0 ** (-3.0 / (t60 * f0)))


def ks_string(
    f0: float,
    t60: float,
    stiffness: float,
    pluck_pos: float,
    n_samples: int,
    sr: int = SAMPLE_RATE,
    brightness: float = 0.5,    # API compat only, unused
    loss_factor: float = 0.25,
) -> np.ndarray:
    """
    KS synthesis with pure gain loop (no FIR averaging at period rate).

    Loop per period: y = decay * x
    Fractional delay: first-order all-pass (always flat magnitude).
    Spectral pre-emphasis: initial delay line shaped so high harmonics
      start slightly lower, producing realistic differential decay.
    """
    period_exact = sr / f0
    period  = max(4, int(np.floor(period_exact)))
    frac    = period_exact - period

    base_decay = 10.0 ** (-3.0 / (t60 * f0))
    ap_frac    = (1.0 - frac) / (1.0 + frac)

    dl = triangular_excitation(period, pluck_pos)

    # Spectral pre-emphasis: mild initial rolloff on high harmonics
    if loss_factor > 0 and period > 8:
        spec = np.fft.rfft(dl, n=period)
        fr   = np.fft.rfftfreq(period) * sr
        n_h  = np.clip(np.round(fr / f0), 1, None)
        taper = 1.0 / (1.0 + loss_factor * 0.3 * (n_h - 1))
        dl = np.fft.irfft(spec * taper, n=period).astype(np.float64)

    ap_st = 0.0; stiff_st = 0.0; widx = 0

    def step(g):
        nonlocal ap_st, stiff_st, widx
        y = g * dl[widx]
        # All-pass fractional delay
        y_ap  = ap_frac * (y - ap_st) + ap_st
        ap_st = y; y = y_ap
        if stiffness > 0:
            s = stiffness * (y - stiff_st) + stiff_st
            stiff_st = y; y = s
        dl[widx] = y
        widx = (widx + 1) % period

    for _ in range(period * 3): step(1.0)   # settle all-pass state

    out = np.zeros(n_samples, dtype=np.float64)
    for i in range(n_samples):
        out[i] = dl[widx]
        step(base_decay)

    return np.clip(out, -2.0, 2.0).astype(np.float32)


def body_eq(signal: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    nyq  = sr / 2.0
    sos1 = butter(2, [150/nyq, 210/nyq], btype='band', output='sos')
    sig  = signal + sosfilt(sos1, signal) * 0.18
    sos2 = butter(2, [1800/nyq, 3500/nyq], btype='band', output='sos')
    sig  = sig + sosfilt(sos2, sig) * 0.07
    sos3 = butter(1, 8000/nyq, btype='low', output='sos')
    sig  = sig * 0.9 + sosfilt(sos3, sig) * 0.1
    return sig.astype(np.float32)


def build_ir(freq_response: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    N         = 4096
    fft_freqs = np.fft.rfftfreq(N, d=1.0/sr)
    log_min   = np.log10(FREQS[0]); log_max = np.log10(FREQS[-1])
    log_f     = np.log10(np.clip(fft_freqs, FREQS[0], FREQS[-1]))
    t         = np.clip((log_f - log_min) / (log_max - log_min), 0, 1)
    idx       = t * (len(FREQS) - 1)
    fi        = np.clip(np.floor(idx).astype(int), 0, len(FREQS)-2)
    fr_       = idx - fi
    H         = freq_response[fi]*(1-fr_) + freq_response[fi+1]*fr_
    H[fft_freqs < 30] = 0.0; H[fft_freqs > 20000] = 0.0
    ir = np.fft.irfft(H, n=N).real
    pk = int(np.argmax(np.abs(ir)))
    ir = np.roll(ir, N//2 - pk) * np.hanning(N)
    return ir.astype(np.float32)


def fft_convolve(signal: np.ndarray, ir: np.ndarray) -> np.ndarray:
    from scipy.signal import fftconvolve
    return fftconvolve(signal, ir).astype(np.float32)


def render_pluck(
    freq_response: np.ndarray,
    string_idx: int = 1,
    pluck_pos: float = DEFAULT_PLUCK_POS,
    reference_gain: float = 1.0,
    sr: int = SAMPLE_RATE,
) -> bytes:
    f0    = OPEN_STRINGS[string_idx]
    t60   = STRING_T60[string_idx]
    stiff = STRING_STIFFNESS[string_idx]
    loss  = STRING_LOSS[string_idx]

    norm_resp = freq_response / (np.max(freq_response) + 1e-12)
    ir        = build_ir(norm_resp, sr)
    n_samples = int(np.ceil(sr * NOTE_DUR_S))

    sig = ks_string(f0, t60, stiff, pluck_pos, n_samples, sr, loss_factor=loss)

    sig -= sig.mean()
    sos_hp = butter(2, 20.0/(sr/2.0), btype='high', output='sos')
    sig    = sosfilt(sos_hp, sig).astype(np.float32)
    sig    = body_eq(sig, sr)
    sig   -= sig.mean()

    conv = fft_convolve(sig, ir)
    conv = np.nan_to_num(conv[:n_samples], nan=0.0) * reference_gain
    conv = np.tanh(conv * 1.5) / float(np.tanh(np.float32(1.5)))
    pcm  = (conv * 0.85 * 32767).clip(-32768, 32767).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1); wf.setsampwidth(2)
        wf.setframerate(sr); wf.writeframes(pcm.tobytes())
    return buf.getvalue()
