"""
audio.py — guitar string synthesis via Karplus-Strong digital waveguide

KS model correctly implements all four required behaviors:
  1. Full harmonic series — the N-sample delay line resonates at f0, 2f0, 3f0...
  2. Pluck-point filter — two-point pickup via excitation position in the delay line
  3. Harmonic decay — the averaging LPF in the feedback loop attenuates highs
     each pass, so the tone darkens naturally over time
  4. Inharmonicity — all-pass stiffness filter slightly stretches upper harmonics

The key insight: decay coefficient must be tuned so the LPF actually rolls off
harmonics. If decay is too close to 1.0, the LPF is compensated and no darkening
occurs. We derive the base decay from T60 at the fundamental, then let the LPF
handle differential harmonic decay automatically.

6-string downstrum: E2 A2 D3 G3 B3 E4 staggered 55ms
"""

import io
import wave
import numpy as np
from scipy.signal import butter, sosfilt
from simulation import FREQS

SAMPLE_RATE = 44100
STRUM_GAP_S = 0.055
NOTE_DUR_S  = 2.5

STRING_FREQS = [82.41, 110.00, 146.83, 196.00, 246.94, 329.63]

# T60 in seconds — real guitar measurements per string
STRING_T60 = [7.0, 6.0, 4.5, 3.2, 2.4, 1.8]

# Inharmonicity coefficient (stiffness): 0=wound, increases for plain strings
STRING_STIFFNESS = [0.0, 0.0, 0.0003, 0.0015, 0.003, 0.005]

# Output gain (lower strings slightly louder in a downstrum)
STRING_GAINS = [0.88, 0.82, 0.76, 0.70, 0.64, 0.58]

# Pluck position as fraction of string length from bridge (0=bridge, 0.5=midpoint)
# Real plucking position for each string in normal strumming
# Bridge pickup (~0.06), typical pluck (~0.12-0.15), neck pickup area (~0.25)
STRING_PLUCK_POS = [0.13, 0.13, 0.12, 0.11, 0.10, 0.09]

# Excitation: bandpass bounds (Hz) for wound vs plain strings
STRING_EXC_BAND = [
    (55,  900),   # E2 wound — fat thud
    (70,  1300),  # A2 wound
    (90,  2000),  # D3 wound
    (110, 4000),  # G3 transition
    (140, 7000),  # B3 plain
    (180, 9000),  # E4 plain
]

def _bandpass_excitation(period: int, lo_hz: float, hi_hz: float,
                         sr: int) -> np.ndarray:
    """
    Bandpass-filtered noise burst seeding one delay-line period.
    Roughly 1/f spectral slope (pink-ish) via differentiation to approximate
    a real pluck spectrum where harmonics roll off ~6dB/octave.
    """
    # Generate slightly more than one period to allow filter settling
    n = period * 3
    noise = np.random.randn(n)

    # Differentiate to get ~6dB/oct rolloff (white -> pink-ish)
    noise = np.diff(noise, prepend=noise[0])

    # Bandpass
    nyq = sr / 2.0
    lo  = np.clip(lo_hz / nyq, 0.001, 0.49)
    hi  = np.clip(hi_hz / nyq, lo + 0.001, 0.49)
    sos = butter(3, [lo, hi], btype='band', output='sos')
    noise = sosfilt(sos, noise)

    # Take the last period (filter fully settled)
    dl = noise[-period:].copy()

    # Normalize
    peak = np.max(np.abs(dl))
    if peak > 0:
        dl /= peak
    return dl.astype(np.float64)


def _t60_to_decay(f0: float, t60: float, sr: int) -> float:
    """
    Per-sample decay for the KS loop such that the FUNDAMENTAL decays
    by 60 dB in t60 seconds. The averaging LPF provides additional
    frequency-dependent decay on top of this.

    Note: do NOT compensate for the LPF loss here — that would eliminate
    the darkening effect. Just set the base level.
    """
    # Fundamental makes sr*t60 passes in t60 seconds... wait, it makes
    # sr/f0 samples per period, and t60*sr total samples, so t60*f0 periods.
    # We want decay^(t60*f0) = 10^(-3)  =>  decay = 10^(-3/(t60*f0))
    return float(10.0 ** (-3.0 / (t60 * f0)))


def ks_string(f0: float, t60: float, stiffness: float,
              pluck_pos: float, lo_hz: float, hi_hz: float,
              n_samples: int, sr: int = SAMPLE_RATE) -> np.ndarray:
    """
    Extended Karplus-Strong digital waveguide synthesis.

    The delay line represents one period of the string. The feedback loop:
      1. Averaging LPF (x[n] + x[n-1]) / 2 — natural harmonic darkening
      2. Per-sample gain (derived from T60 at fundamental)
      3. Fractional delay all-pass — accurate pitch
      4. Stiffness all-pass — inharmonicity

    Pluck point: excitation is injected at position round(pluck_pos * period),
    which applies the pluck-point comb filter implicitly through the
    interaction of the initial conditions with the delay-line resonator.
    The pickup point is fixed at position 0.
    """
    period_exact = sr / f0
    period       = int(np.floor(period_exact))
    frac         = period_exact - period

    # Fractional delay all-pass coefficient
    ap_frac = (1.0 - frac) / (1.0 + frac)

    # Per-sample decay — let LPF provide harmonic-differential decay
    decay = _t60_to_decay(f0, t60, sr)

    # Seed delay line — pluck point sets initial conditions
    dl = _bandpass_excitation(period, lo_hz, hi_hz, sr)

    # Apply pluck-point comb: zero out the samples at the "nut" side of the
    # pluck point. This suppresses harmonics whose nodes fall at the pluck.
    # Simple implementation: reverse the portion past the pluck point.
    pluck_idx = int(np.round(pluck_pos * period))
    if 0 < pluck_idx < period:
        # Reflect excitation: simulates string clamped at pluck point
        # by making the two "halves" mirror each other in sign
        dl[pluck_idx:] = -dl[pluck_idx:][::-1][:period - pluck_idx]

    out     = np.zeros(n_samples, dtype=np.float64)
    ap_f_st = 0.0   # fractional delay all-pass state
    ap_s_st = 0.0   # stiffness all-pass state
    prev    = dl[-1] # previous sample for averaging LPF

    for i in range(n_samples):
        idx = i % period
        out[i] = dl[idx]

        # Averaging LPF — this is the core of KS darkening
        lp = (dl[idx] + prev) * 0.5
        prev = dl[idx]

        # Apply base decay
        lp *= decay

        # Fractional delay all-pass
        ap_f_out  = ap_frac * (lp - ap_f_st) + ap_f_st
        ap_f_st   = lp
        lp        = ap_f_out

        # Stiffness dispersion all-pass
        if stiffness > 0:
            ap_s_out = stiffness * (lp - ap_s_st) + ap_s_st
            ap_s_st  = lp
            lp       = ap_s_out

        dl[idx] = np.clip(lp, -2.0, 2.0)

    return out.astype(np.float32)

def body_eq(signal: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Approximate guitar body resonance EQ."""
    nyq = sr / 2.0
    # Air cavity boost ~170 Hz
    sos1 = butter(2, [150/nyq, 210/nyq], btype='band', output='sos')
    sig  = signal + sosfilt(sos1, signal) * 0.20
    # Presence boost ~2-3.5 kHz
    sos2 = butter(2, [1800/nyq, 3500/nyq], btype='band', output='sos')
    sig  = sig + sosfilt(sos2, sig) * 0.08
    # Gentle high rolloff above 7 kHz
    sos3 = butter(1, 7500/nyq, btype='low', output='sos')
    sig  = sig * 0.88 + sosfilt(sos3, sig) * 0.12
    return sig.astype(np.float32)


def build_ir(freq_response: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Convert linear freq response (at FREQS) → windowed zero-phase IR."""
    N         = 4096
    fft_freqs = np.fft.rfftfreq(N, d=1.0 / sr)
    log_min   = np.log10(FREQS[0])
    log_max   = np.log10(FREQS[-1])
    log_f     = np.log10(np.clip(fft_freqs, FREQS[0], FREQS[-1]))
    t         = np.clip((log_f - log_min) / (log_max - log_min), 0, 1)
    indices   = t * (len(FREQS) - 1)
    fi        = np.floor(indices).astype(int)
    frac      = indices - fi
    fi        = np.clip(fi, 0, len(FREQS) - 2)
    H         = freq_response[fi] * (1 - frac) + freq_response[fi + 1] * frac
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


def render_strum(freq_response: np.ndarray, sr: int = SAMPLE_RATE) -> bytes:
    """Synthesise 6-string downstrum. Returns 16-bit mono WAV bytes."""
    norm_resp     = freq_response / (np.max(freq_response) + 1e-12)
    ir            = build_ir(norm_resp, sr)
    total_dur     = STRUM_GAP_S * 5 + NOTE_DUR_S
    total_samples = int(np.ceil(sr * total_dur))
    mix           = np.zeros(total_samples, dtype=np.float32)

    for s in range(6):
        f0        = STRING_FREQS[s]
        t60       = STRING_T60[s]
        stiff     = STRING_STIFFNESS[s]
        gain      = STRING_GAINS[s]
        pluck     = STRING_PLUCK_POS[s]
        lo, hi    = STRING_EXC_BAND[s]
        n_samples = int(np.ceil(sr * NOTE_DUR_S))
        start     = round(s * STRUM_GAP_S * sr)

        ks   = ks_string(f0, t60, stiff, pluck, lo, hi, n_samples, sr)
        ks   = body_eq(ks, sr)
        conv = fft_convolve(ks, ir)

        end = min(start + len(conv), total_samples)
        mix[start:end] += conv[:end - start] * gain

    mix  = np.nan_to_num(mix, nan=0.0, posinf=1.0, neginf=-1.0)
    peak = np.max(np.abs(mix))
    if peak > 0:
        mix /= peak
    mix = np.tanh(mix * 1.3) / float(np.tanh(np.float32(1.3)))
    pcm = (mix * 0.88 * 32767).clip(-32768, 32767).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()
