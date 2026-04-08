# SPDX-License-Identifier: BSD-3-Clause
"""
Taper inversion utilities.
Convert between knob position (0-10) and perceptually-linear slider values.

Volume slider: 0-100 maps linearly to pot wiper position (alpha = 0..1).
  alpha = vol_pct / 100
  vol_knob = inverse_audio_taper(alpha)

Tone slider: displayed as 0-100 but internally represents alpha = tone_pct/100.
  tone_knob = inverse_audio_taper(alpha)

This way equal slider movement = equal change in pot resistance fraction,
which is proportional to equal change in the circuit's loading behaviour.

The audio taper formula: alpha = (10^(2*x) - 1) / 99  where x = knob/10
Inverting:  x = log10(99*alpha + 1) / 2
            knob = 10 * log10(99*alpha + 1) / 2
"""
import numpy as np

def alpha_to_knob(alpha: float) -> float:
    """Convert pot wiper fraction (0-1) to knob position (0-10) for audio taper."""
    alpha = float(np.clip(alpha, 0.0, 1.0))
    if alpha <= 0.0: return 0.0
    if alpha >= 1.0: return 10.0
    return float(10.0 * np.log10(99.0 * alpha + 1.0) / 2.0)

def knob_to_alpha(knob: float) -> float:
    """Convert knob position (0-10) to pot wiper fraction (0-1) for audio taper."""
    x = float(np.clip(knob, 0.0, 10.0)) / 10.0
    return float(np.clip((10.0 ** (2.0 * x) - 1.0) / 99.0, 0.0, 1.0))

def vol_pct_to_knob(pct: float) -> float:
    """vol_pct (0-100) -> knob (0-10). Linear pct = linear wiper position."""
    return alpha_to_knob(pct / 100.0)

def knob_to_vol_pct(knob: float) -> float:
    """knob (0-10) -> vol_pct (0-100)."""
    return round(knob_to_alpha(knob) * 100.0, 1)
