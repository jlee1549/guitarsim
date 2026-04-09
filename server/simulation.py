# SPDX-License-Identifier: BSD-3-Clause
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
    # Polarity: +1 = normal, -1 = reversed (RWRP or out-of-phase wiring).
    polarity: int = 1
    # Eddy current loss model (GuitarFreak Rd/Ld parameters).
    # Models the damping effect of metal covers, baseplates, and pole pieces.
    # Rd_ohm: parallel resistance (higher = less damping). 0 = disabled.
    # Ld_H:   series inductance forming the RL shunt with Rd.
    # Effect: shunts high frequencies, softening the resonant peak.
    # Typical values — uncovered HB: Rd=200-300kΩ, Ld=9-20H
    #                  covered HB:   Rd=150-250kΩ, Ld=9-20H (slightly more damping)
    #                  SC (alnico):  Rd=400-600kΩ, Ld=10-15H (less metal, less eddy)
    Rd_ohm: float = 0.0   # 0 = no eddy current model
    Ld_H:   float = 0.0

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
    """RLC pickup source impedance with optional eddy current shunt."""
    w  = 2 * np.pi * freqs
    Zs = pu.rdc + 1j * w * pu.L
    if pu.Cp > 0:
        Yp = 1.0/Zs + 1j*w*pu.Cp
        Zs = 1.0 / Yp
    # Eddy current loss: parallel RL shunt (Rd in series with Ld, paralleling Zs)
    # Models damping from metal covers/baseplates. At high freq, jwLd dominates
    # and shunts the pickup, softening the resonant peak.
    if pu.Rd_ohm > 0 and pu.Ld_H > 0:
        Z_eddy = pu.Rd_ohm + 1j * w * pu.Ld_H
        Zs = (Zs * Z_eddy) / (Zs + Z_eddy)
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


def position_comb(freqs: np.ndarray, dist_mm: float, scale_mm: float = 628.0, f0: float = 0.0) -> np.ndarray:
    """
    Pickup position comb filter: sin(pi * f * 2 * d / v)

    Returns COMPLEX values (with sign/phase) so that two pickups in parallel
    combine with the correct phase relationship — this produces the characteristic
    Strat quack in positions 2 and 4 from out-of-phase cancellation between
    the neck and middle (or middle and bridge) pickups.

    Wave velocity v = 2 * scale * f0 (per string). Falls back to STRING_WAVE_VELOCITY.
    """
    d = dist_mm / 1000.0
    v = 2.0 * (scale_mm / 1000.0) * f0 if f0 > 0 else STRING_WAVE_VELOCITY
    arg = np.pi * freqs * 2 * d / v
    return np.sin(arg).astype(complex)   # complex, preserves sign/phase


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
        # 50s wiring: tone cap shunts at vol pot wiper (Rv2 node).
        # Two-stage model:
        #   Stage 1: pickup Zs drives into (Rv2 || Y_tone || Y_cable || Y_amp)
        #            → gives voltage at wiper relative to amp input
        #   Stage 2: wiper is attenuated by Rv1 series with the parallel combo
        # This preserves the pickup resonance at all vol settings.
        Y_ext    = Y_tone + Y_cable + Y_bleed + Y_amp   # everything hanging off wiper
        Y_ext   += (1.0/Rv2 if Rv2 > 0 else 1e12)       # Rv2 to ground
        Z_ext    = 1.0 / Y_ext
        # Voltage at wiper node (Thevenin source into Z_ext):
        v_wiper  = np.abs(Z_ext) / np.abs(Zs + Z_ext)
        # Attenuation from wiper to output (Rv1 series divider):
        Rv2_eff  = (Rv2 * Z_ext) / (Rv2 + Z_ext) if Rv2 > 0 else Z_ext
        att      = np.abs(Rv2_eff) / np.abs(Rv1 + Rv2_eff) if Rv1 > 0 else np.ones(len(freqs))
        gain     = v_wiper * att
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
    f0: float = 0.0,
    freqs: np.ndarray = None,   # custom frequency grid; defaults to FREQS
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
    freqs = FREQS if freqs is None else freqs

    if len(active) == 1:
        pu   = pickups[active[0]]
        gain, *_ = channel_gain(freqs, pu, Ccable, wiring, R_amp)
        if include_position:
            gain *= np.abs(position_comb(freqs, pu.dist_mm, pu.scale_mm, f0))
        return gain

    # Two code paths depending on whether the position comb is needed.
    w = 2 * np.pi * freqs

    if not include_position:
        # Chart display path: no comb, no polarity. Each pickup contributes
        # its full channel gain (with cable + amp load already applied).
        # This gives clean resonant-peak curves showing the electronics character.
        # Pickups combine as parallel voltage sources: sum the gains directly.
        gain_sum = np.zeros(len(freqs))
        for idx in active:
            pu = pickups[idx]
            gain, *_ = channel_gain(freqs, pu, Ccable, wiring, R_amp)
            gain_sum += gain
        return np.nan_to_num(gain_sum / len(active), nan=0.0)

    # Audio path: full phasor sum with position comb and polarity.
    # Each pickup's voltage contribution is: polarity * gain * comb (complex).
    # This correctly models quack from RWRP phase cancellation.
    V_sum    = np.zeros(len(freqs), dtype=complex)
    Y_shunt  = np.zeros(len(freqs), dtype=complex)

    for idx in active:
        pu   = pickups[idx]
        gain, Zs, Rv1, Rv2, Y_tone = channel_gain(freqs, pu, 0.0, wiring, 1e99)
        comb = position_comb(freqs, pu.dist_mm, pu.scale_mm, f0)
        V_sum  += pu.polarity * gain.astype(complex) * comb
        Y_shunt += (1.0/Rv2 if Rv2 > 0 else 1e-12) + Y_tone
        Y_shunt += bleed_admittance(freqs, pu.tbleed)

    Y_cable  = 1j * w * Ccable if Ccable > 0 else np.zeros(len(freqs), dtype=complex)
    Y_amp    = np.full(len(freqs), 1.0 / R_amp, dtype=complex)
    Y_shunt += Y_cable + Y_amp

    gain = np.abs(V_sum)
    return np.nan_to_num(gain, nan=0.0)
