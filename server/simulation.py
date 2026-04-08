"""
simulation.py — guitar electronics circuit simulation

Wiring topologies:
  HH (Les Paul): Each pickup has independent volume + tone pot.
    Both outputs sum in parallel at jack. 50s or modern wiring per pickup.

  SSS (Strat): Master volume, tone-1 on neck, tone-2 on middle,
    bridge has no dedicated tone pot (wired direct to volume).
    In-between positions connect adjacent pickups in parallel.

  HSS: Humbucker neck has its own volume+tone; two singles share master vol
    with the Strat tone arrangement for the single coil section.

  General: For simplicity we model each pickup as having its own vol+tone.
  The user can set Rtone=inf (or very large) and tone_knob=10 to simulate
  no tone pot, approximating bridge-with-no-tone-pot on SSS.

Circuit math: complex impedance, numpy vectorised over FREQS.
Returns linear gain array.
"""

import numpy as np
from dataclasses import dataclass
from typing import Literal

FREQS = np.logspace(np.log10(50), np.log10(20000), 200)
STRING_WAVE_VELOCITY = 200.0  # m/s


@dataclass
class PickupParams:
    rdc: float
    L: float
    Cp: float
    Rvol: float = 500e3
    Rtone: float = 500e3
    Ctone: float = 22e-9
    vol_knob: float = 10.0
    tone_knob: float = 10.0
    dist_mm: float = 80.0
    scale_mm: float = 628.0
    vol_taper: str  = "audio"
    tone_taper: str = "audio"
    tbleed: str     = "none"
    has_tone: bool  = True   # False = no tone pot (bridge on SSS Strat)
    # Direct wiper fraction (0-1). When >= 0, bypasses vol_knob + apply_taper.
    # Slider pct (0-100) / 100 goes here. Taper selector then only affects
    # the knob-to-alpha mapping shown for reference — not the simulation result.
    vol_alpha: float  = -1.0
    tone_alpha: float = -1.0

def apply_taper(knob: float, taper: str) -> float:
    alpha = knob / 10.0
    if taper == "linear":
        return alpha
    elif taper == "audio":
        return float(np.clip((10.0 ** (2.0 * alpha) - 1.0) / 99.0, 0.0, 1.0))
    elif taper == "custom_15":
        return 0.15*(alpha/0.5) if alpha <= 0.5 else 0.15 + 0.85*((alpha-0.5)/0.5)
    elif taper == "custom_30":
        return 0.30*(alpha/0.5) if alpha <= 0.5 else 0.30 + 0.70*((alpha-0.5)/0.5)
    return alpha


def pickup_source_z(freqs: np.ndarray, pu: PickupParams) -> np.ndarray:
    """RLC pickup source impedance (parallel Cp across series Rdc+jωL)."""
    w  = 2 * np.pi * freqs
    Zs = pu.rdc + 1j * w * pu.L
    if pu.Cp > 0:
        Yp = 1.0/Zs + 1j*w*pu.Cp
        return 1.0 / Yp
    return Zs


def tone_admittance(freqs: np.ndarray, pu: PickupParams) -> np.ndarray:
    """Tone branch admittance. has_tone=False → near-zero admittance (open)."""
    if not pu.has_tone:
        return np.zeros(len(freqs), dtype=complex)
    w  = 2 * np.pi * freqs
    tone_a = pu.tone_alpha if pu.tone_alpha >= 0 else apply_taper(pu.tone_knob, pu.tone_taper)
    Rs = pu.Rtone * tone_a + 10.0
    Xt = -1 / (w * pu.Ctone) if pu.Ctone > 0 else np.full_like(w, -1e15)
    return 1.0 / (Rs + 1j * Xt)


def bleed_admittance(freqs: np.ndarray, mode: str) -> np.ndarray:
    w = 2 * np.pi * freqs
    if mode == "cap":
        return 1j * w * 100e-12
    elif mode == "network":
        Rb, Cb = 150e3, 100e-12
        return 1.0 / (Rb + 1 / (1j * w * Cb))
    return np.zeros(len(freqs), dtype=complex)


def position_comb(freqs: np.ndarray, dist_mm: float) -> np.ndarray:
    d   = dist_mm / 1000.0
    arg = np.pi * freqs * 2 * d / STRING_WAVE_VELOCITY
    return np.abs(np.sin(arg))


def channel_gain(
    freqs: np.ndarray,
    pu: PickupParams,
    Ccable: float,
    wiring: Literal["50s", "modern"],
    R_amp: float = 1e6,
) -> tuple:
    """Single pickup channel gain + Thévenin components.
    R_amp: amp input impedance (Ohms). Added as parallel shunt at the output node.
    Default 1MΩ is typical for a tube amp input.
    """
    w      = 2 * np.pi * freqs
    Zs     = pickup_source_z(freqs, pu)
    alpha  = pu.vol_alpha if pu.vol_alpha >= 0 else apply_taper(pu.vol_knob, pu.vol_taper)
    Rv1    = pu.Rvol * (1 - alpha)
    Rv2    = pu.Rvol * alpha

    Y_tone  = tone_admittance(freqs, pu)
    Y_bleed = bleed_admittance(freqs, pu.tbleed)
    Y_cable = 1j * w * Ccable if Ccable > 0 else np.zeros_like(freqs, dtype=complex)
    Y_amp   = np.full(len(freqs), 1.0 / R_amp, dtype=complex)

    if wiring == "50s":
        # Rv2=0 means wiper at ground → infinite shunt (dead short at output)
        Y_shunt  = (1/Rv2 if Rv2 > 0 else 1e12) + Y_tone + Y_cable + Y_bleed + Y_amp
        Z_load   = 1.0 / Y_shunt
        Z_denom  = Zs + Rv1 + Z_load
        gain     = np.abs(Z_load) / np.abs(Z_denom)
    else:
        # Modern: tone shunts at input lug
        Y_input  = (1/pu.Rvol) + Y_tone + Y_bleed
        Z_input  = 1.0 / Y_input
        v1       = np.abs(Z_input) / np.abs(Zs + Z_input)
        Z_th     = 1.0 / (1.0/Zs + 1.0/Z_input)
        # Rv2=0 → dead short at output wiper
        Y_load2  = (1/Rv2 if Rv2 > 0 else 1e12) + Y_cable + Y_amp
        Z_load2  = 1.0 / Y_load2
        gain     = v1 * np.abs(Z_load2) / np.abs(Z_th + Rv1 + Z_load2)

    gain = np.nan_to_num(gain, nan=0.0)
    return gain, Zs, Rv1, Rv2, Y_tone

def sweep(
    pickups: list,
    active: list,
    Ccable: float,
    wiring: str,
    include_position: bool = True,
    R_amp: float = 1e6,
) -> np.ndarray:
    """
    Combined frequency response for active pickups (parallel Thévenin combination).

    Wiring notes:
      HH (Les Paul): Each pickup has independent vol+tone. Correct as-is.
      SSS (Strat):   Master volume — model by giving all pickups the same
                     vol_knob value. Tone pots: neck gets tone-1, middle gets
                     tone-2, bridge has has_tone=False (no dedicated tone pot).
                     The in-between positions (neck+middle, middle+bridge) are
                     handled by passing both pickup indices in `active`.
      HSS:           Neck HB has its own vol+tone; singles share master vol
                     with Strat-style tone assignment.

    In-between positions create a partial hum-cancellation and an impedance
    drop that produces the characteristic "scooped" tone — this falls out
    naturally from the Thévenin parallel combination.
    """
    freqs = FREQS

    if len(active) == 1:
        pu   = pickups[active[0]]
        gain, *_ = channel_gain(freqs, pu, Ccable, wiring, R_amp)
        if include_position:
            gain *= position_comb(freqs, pu.dist_mm)
        return gain

    # Parallel Thévenin combination
    w       = 2 * np.pi * freqs
    Y_src   = np.zeros(len(freqs), dtype=complex)
    Y_shunt = np.zeros(len(freqs), dtype=complex)

    for idx in active:
        pu   = pickups[idx]
        _, Zs, Rv1, Rv2, Y_tone = channel_gain(freqs, pu, 0.0, wiring, 1e99)
        comb = position_comb(freqs, pu.dist_mm) if include_position else 1.0
        Z_ser = (Zs + Rv1) / np.where(comb > 0, comb, 1e-9)
        Y_src   += 1.0 / Z_ser
        Y_shunt += (1.0/Rv2 if Rv2 > 0 else 1e12) + Y_tone
        Y_shunt += bleed_admittance(freqs, pu.tbleed)

    Y_cable  = 1j * w * Ccable if Ccable > 0 else np.zeros(len(freqs), dtype=complex)
    Y_amp    = np.full(len(freqs), 1.0 / R_amp, dtype=complex)
    Y_shunt += Y_cable + Y_amp

    Z_load = 1.0 / Y_shunt
    Z_th   = 1.0 / Y_src
    gain   = np.abs(Z_load) / np.abs(Z_th + Z_load)
    return np.nan_to_num(gain, nan=0.0)
