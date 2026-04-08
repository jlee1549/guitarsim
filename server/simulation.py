"""
simulation.py — guitar electronics circuit simulation

All circuit math is done in complex arithmetic using numpy.
Topology: pickup RLC source → volume pot (50s or modern wiring) → tone RC shunt → cable cap load.
Returns frequency response as numpy array of linear gain values.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Literal

FREQS = np.logspace(np.log10(50), np.log10(20000), 200)

# Representative string wave velocity (geometric mean across strings at concert pitch)
# Puts bridge pickup null ~2.6 kHz, neck null ~590 Hz
STRING_WAVE_VELOCITY = 200.0  # m/s


@dataclass
class PickupParams:
    rdc: float          # DC resistance, Ohms
    L: float            # inductance, Henries
    Cp: float           # self-capacitance, Farads
    Rvol: float = 500e3
    Rtone: float = 500e3
    Ctone: float = 22e-9
    vol_knob: float = 10.0   # 0–10
    tone_knob: float = 10.0  # 0–10
    dist_mm: float = 80.0
    scale_mm: float = 628.0
    vol_taper: str = "audio"   # "linear", "audio", "custom_15", "custom_30"
    tone_taper: str = "audio"  # same options


def apply_taper(knob: float, taper: str) -> float:
    """
    Convert a knob position (0–10) to a resistance fraction (0–1) based on taper type.

    Linear (B):    alpha = knob/10  — equal resistance per degree
    Audio (A):     ~10% resistance at midpoint. Models standard log pot.
                   Uses the common guitar approximation: R = (10^(2*alpha) - 1) / 99
                   where alpha = knob/10. Gives 10% at knob=5, smooth swell.
    Custom 15%:    Midpoint = 15%. Piecewise linear (RS-style, less extreme than audio).
    Custom 30%:    Midpoint = 30%. Vintage taper / Mojotone style. Most linear feel.
    """
    alpha = knob / 10.0
    if taper == "linear":
        return alpha
    elif taper == "audio":
        # Standard audio taper approximation — 10% resistance at midpoint
        # Rearranged: fraction = (10^(2*alpha) - 1) / 99
        # Clamped to [0,1] to handle floating point edge cases
        return float(np.clip((10.0 ** (2.0 * alpha) - 1.0) / 99.0, 0.0, 1.0))
    elif taper == "custom_15":
        # Piecewise linear with 15% at midpoint (RS SuperPot style)
        if alpha <= 0.5:
            return 0.15 * (alpha / 0.5)
        else:
            return 0.15 + 0.85 * ((alpha - 0.5) / 0.5)
    elif taper == "custom_30":
        # Piecewise linear with 30% at midpoint (vintage/Mojotone style)
        if alpha <= 0.5:
            return 0.30 * (alpha / 0.5)
        else:
            return 0.30 + 0.70 * ((alpha - 0.5) / 0.5)
    else:
        return alpha  # fallback to linear


def pickup_source_z(freqs: np.ndarray, pu: PickupParams) -> np.ndarray:
    """Complex source impedance of pickup: (Rdc + jwL) || (1/jwCp)"""
    w = 2 * np.pi * freqs
    Z_RL = pu.rdc + 1j * w * pu.L
    Z_Cp = 1 / (1j * w * pu.Cp) if pu.Cp > 0 else np.full_like(w, 1e15, dtype=complex)
    return (Z_RL * Z_Cp) / (Z_RL + Z_Cp)


def tone_admittance(freqs: np.ndarray, pu: PickupParams) -> np.ndarray:
    """Tone branch admittance. knob=10: large Rs → near open. knob=0: Rs≈0 → max cut."""
    w = 2 * np.pi * freqs
    Rs = pu.Rtone * apply_taper(pu.tone_knob, pu.tone_taper) + 10.0  # 10Ω floor
    Xt = -1 / (w * pu.Ctone) if pu.Ctone > 0 else np.full_like(w, -1e15)
    Z_tone = Rs + 1j * Xt
    return 1.0 / Z_tone


def bleed_admittance(freqs: np.ndarray, mode: str) -> np.ndarray:
    """Treble bleed network admittance."""
    w = 2 * np.pi * freqs
    if mode == "cap":
        return 1j * w * 100e-12
    elif mode == "network":
        Rb, Cb = 150e3, 100e-12
        return 1.0 / (Rb + 1 / (1j * w * Cb))
    return np.zeros_like(freqs, dtype=complex)


def position_comb(freqs: np.ndarray, dist_mm: float) -> np.ndarray:
    """Pickup position comb filter: |sin(pi * f * 2*d / v)|"""
    d = dist_mm / 1000.0
    arg = np.pi * freqs * 2 * d / STRING_WAVE_VELOCITY
    return np.abs(np.sin(arg))

def channel_gain(
    freqs: np.ndarray,
    pu: PickupParams,
    Ccable: float,
    tbleed: str,
    wiring: Literal["50s", "modern"],
) -> tuple[np.ndarray, np.ndarray, float, float, np.ndarray]:
    """
    Compute voltage gain at output for a single pickup channel.
    Returns (gain, Zs, Rv1, Rv2, Y_tone) for use in multi-pickup combining.
    """
    w = 2 * np.pi * freqs
    Zs = pickup_source_z(freqs, pu)
    # Volume pot: taper maps knob position to resistance fraction
    alpha = apply_taper(pu.vol_knob, pu.vol_taper)
    Rv1 = pu.Rvol * (1 - alpha)   # upper segment (series with pickup)
    Rv2 = pu.Rvol * alpha          # lower segment (shunts to ground)

    Y_tone = tone_admittance(freqs, pu)
    Y_bleed = bleed_admittance(freqs, tbleed)
    Y_cable = 1j * w * Ccable if Ccable > 0 else np.zeros_like(freqs, dtype=complex)

    if wiring == "50s":
        # Tone, cable, lower pot shunt at wiper
        Y_shunt = (1 / Rv2 if Rv2 > 0 else 0) + Y_tone + Y_cable + Y_bleed
        Z_load = 1.0 / Y_shunt
        Z_denom = Zs + Rv1 + Z_load
        gain = np.abs(Z_load) / np.abs(Z_denom)
    else:
        # Modern: tone shunts at input lug (before volume taper)
        Y_input = (1 / pu.Rvol) + Y_tone + Y_bleed
        Z_input = 1.0 / Y_input
        v1 = np.abs(Z_input) / np.abs(Zs + Z_input)
        # Thevenin source at lug3
        Z_th = 1.0 / (1.0 / Zs + 1.0 / Z_input)
        Y_load2 = (1 / Rv2 if Rv2 > 0 else 0) + Y_cable
        Z_load2 = 1.0 / Y_load2
        Z_denom2 = Z_th + Rv1 + Z_load2
        gain = v1 * np.abs(Z_load2) / np.abs(Z_denom2)

    gain = np.nan_to_num(gain, nan=0.0)
    return gain, Zs, Rv1, Rv2, Y_tone


def sweep(
    pickups: list[PickupParams],
    active: list[int],
    Ccable: float,
    tbleed: str,
    wiring: str,
    include_position: bool = True,
) -> np.ndarray:
    """
    Compute combined frequency response for the active pickup set.
    Returns linear gain array at FREQS.
    """
    freqs = FREQS

    if len(active) == 1:
        pu = pickups[active[0]]
        gain, *_ = channel_gain(freqs, pu, Ccable, tbleed, wiring)
        if include_position:
            gain *= position_comb(freqs, pu.dist_mm)
        return gain

    # Multi-pickup: Thevenin combining
    w = 2 * np.pi * freqs
    Y_src = np.zeros(len(freqs), dtype=complex)
    Y_shunt = np.zeros(len(freqs), dtype=complex)

    for idx in active:
        pu = pickups[idx]
        gain, Zs, Rv1, Rv2, Y_tone = channel_gain(freqs, pu, 0, "none", wiring)
        comb = position_comb(freqs, pu.dist_mm) if include_position else 1.0
        Z_ser = (Zs + Rv1) / np.where(comb > 0, comb, 1e-9)
        Y_src += 1.0 / Z_ser
        Y_shunt += (1 / Rv2 if Rv2 > 0 else 0) + Y_tone

    Y_cable = 1j * w * Ccable if Ccable > 0 else np.zeros(len(freqs), dtype=complex)
    Y_bleed = bleed_admittance(freqs, tbleed)
    Y_shunt += Y_cable + Y_bleed

    Z_load = 1.0 / Y_shunt
    Z_th = 1.0 / Y_src
    result = np.abs(Z_load) / np.abs(Z_th + Z_load)
    return np.nan_to_num(result, nan=0.0)
