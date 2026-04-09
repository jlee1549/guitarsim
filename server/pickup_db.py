# SPDX-License-Identifier: BSD-3-Clause
"""
pickup_db.py — pickup electrical parameter database

Parameters per pickup:
  rdc  : DC resistance (Ohms) — sets output level and Thevenin source impedance
  L    : inductance (Henries) — primary tone-shaping parameter; higher = darker
  Cp   : self-capacitance (Farads) — with L sets resonant peak frequency
         resonant peak ≈ 1 / (2π√(L·Cp)) before loading by pots/cable

Measured/published values from:
  - Seymour Duncan archived tone chart (DCR + resonant peak)
  - Bedlam Guitars inductance measurements (100+ pickups)
  - Individual measurements: Seth Lover (Darth Phineas), JB (guitarhacking.net)
  - Seymour Duncan forums data compilation

Inductance derived where not directly measured:
  L = 1 / ((2π·f_res)² · Cp)  with Cp estimated from pickup type.

HB self-cap range: 80–180pF (higher for potted/covered pickups)
SC self-cap range: 50–100pF
P90 self-cap range: 80–120pF
"""

PICKUPS = {
    "humbucker": [
        # ── Vintage / PAF style ──────────────────────────────────────────
        # Original PAF: ~7.5kΩ, ~4.5H neck / ~5.5H bridge (Seymour Duncan forums)
        {"name": "PAF neck (vintage A2)",
         "rdc": 7500,  "L": 4.5,  "Cp": 100e-12,
         "Rd": 280000, "Ld": 12.0},   # uncovered, typical vintage
        {"name": "PAF bridge (vintage A2)",
         "rdc": 8200,  "L": 5.0,  "Cp": 100e-12,
         "Rd": 280000, "Ld": 12.0},

        # Seth Lover Model (SD SH-55): measured by Darth Phineas
        {"name": "Seth Lover neck (A2, 8.14 kHz peak)",
         "rdc": 7535,  "L": 3.733, "Cp": 110e-12,
         "Rd": 300000, "Ld": 9.0},
        {"name": "Seth Lover bridge (A2, 5.9 kHz peak)",
         "rdc": 8327,  "L": 4.612, "Cp": 130e-12,
         "Rd": 300000, "Ld": 9.0},

        # Alnico II Pro (SD APH-1)
        {"name": "Alnico II Pro neck (7.1 kHz peak)",
         "rdc": 7600,  "L": 4.2,  "Cp": 120e-12,
         "Rd": 290000, "Ld": 9.0},
        {"name": "Alnico II Pro bridge (6.7 kHz peak)",
         "rdc": 7850,  "L": 4.5,  "Cp": 120e-12,
         "Rd": 290000, "Ld": 9.0},

        # Gibson '57 Classic — GuitarFreak measured Rd/Ld
        # Uncovered: Rd=290kΩ, Ld=9H  Covered: Rd=220kΩ, Ld=9H
        {"name": "'57 Classic uncovered (GF measured)",
         "rdc": 8572,  "L": 5.256, "Cp": 117e-12,
         "Rd": 290000, "Ld": 9.0},
        {"name": "'57 Classic covered (GF measured)",
         "rdc": 8752,  "L": 5.404, "Cp": 110e-12,
         "Rd": 220000, "Ld": 9.0},   # cover adds ~30% more damping

        # ── Medium output / versatile ─────────────────────────────────────
        # SD Jazz (SH-2N): ~7.7kΩ neck, clean/warm
        {"name": "Jazz neck (A5, warm)",
         "rdc": 7700,  "L": 4.3,  "Cp": 115e-12},

        # SD '59 (SH-1): ~8.3kΩ bridge, classic rock
        {"name": "'59 bridge (A5)",
         "rdc": 8300,  "L": 4.9,  "Cp": 115e-12},

        # DiMarzio PAF 36th Anniversary: ~8.1kΩ, moderate output
        {"name": "PAF 36th Anniversary bridge",
         "rdc": 8100,  "L": 5.1,  "Cp": 120e-12},

        # Wide Range HB (Seth Lover / Fender, CuNiFe): lower inductance by design
        # Lower inductance → brighter, more single-coil-like response
        {"name": "Wide Range HB (CuNiFe)",
         "rdc": 6500,  "L": 3.2,  "Cp": 80e-12},

        # ── Hot / high output ─────────────────────────────────────────────
        # SD JB (SH-4): measured 16.2kΩ, 8.54H (guitarhacking)
        {"name": "JB bridge (ceramic, 2.76 kHz peak)",
         "rdc": 16200, "L": 8.54, "Cp": 150e-12,
         "Rd": 160000, "Ld": 15.0},   # heavily potted, significant damping

        # SD Custom Custom: 14kΩ, 9.35H
        {"name": "Custom Custom bridge (A2)",
         "rdc": 14000, "L": 9.35, "Cp": 150e-12,
         "Rd": 180000, "Ld": 12.0},

        # SD Distortion (SH-6): ~13.4kΩ, ceramic
        {"name": "Distortion bridge (ceramic)",
         "rdc": 13400, "L": 7.5,  "Cp": 160e-12,
         "Rd": 170000, "Ld": 15.0},

        # DiMarzio Super Distortion: GF measured Rd=160kΩ, Ld=20H
        {"name": "Super Distortion bridge (GF measured)",
         "rdc": 16373, "L": 10.0, "Cp": 75e-12,
         "Rd": 160000, "Ld": 20.0},

        # DiMarzio Tone Zone: ~16.6kΩ, very dark and warm
        {"name": "Tone Zone bridge (A5)",
         "rdc": 16600, "L": 9.0,  "Cp": 160e-12},

        # ── Low wind / bright ─────────────────────────────────────────────
        # Filtertron-style: low inductance, tight, bright (Gretsch Blacktop ~1.8H)
        {"name": "Filtertron style (bright, 1.8H)",
         "rdc": 4800,  "L": 1.8,  "Cp": 60e-12},

        # Low-wind custom (e.g. Bare Knuckle Stormy Monday): clean, open
        {"name": "Low-wind boutique (A3, open)",
         "rdc": 7200,  "L": 4.0,  "Cp": 95e-12},
    ],

    "single": [
        # ── Stratocaster — measured values (GuitarFreak / Bedlam) ─────────
        # Texas Special: measured R=6340Ω, L=2.55H, Cp=160pF (GuitarFreak)
        {"name": "Texas Special (measured, A5)",
         "rdc": 6340,  "L": 2.55, "Cp": 160e-12},
        # Fender CS69: measured R=5450Ω, L=2.30H, Cp=140pF
        {"name": "CS '69 (measured, A5)",
         "rdc": 5450,  "L": 2.30, "Cp": 140e-12},
        # Fender 57/62: measured R=7082Ω, L=2.97H, Cp=96pF
        {"name": "Fender '57/'62 (measured, A5)",
         "rdc": 7082,  "L": 2.97, "Cp": 96e-12},
        # SD SSL-1: measured R=6620Ω, L=3.16H, Cp=100pF
        {"name": "SSL-1 Vintage (measured, A5)",
         "rdc": 6620,  "L": 3.16, "Cp": 100e-12},
        # Fender VN (Vintage Noiseless): measured R=10400Ω, L=2.86H, Cp=38pF
        # Very low Cp — gives a bright, extended high-frequency response
        {"name": "Vintage Noiseless (measured, A5)",
         "rdc": 10400, "L": 2.86, "Cp": 38e-12},
        # Suhr V60 LP: measured R=6471Ω, L=3.00H, Cp=229pF (high Cp — darker)
        {"name": "Suhr V60 LP (measured, A5)",
         "rdc": 6471,  "L": 3.00, "Cp": 229e-12},
        # Lollar Blackface: measured R=7664Ω, L=3.57H, Cp=81pF
        {"name": "Lollar Blackface (measured, A5)",
         "rdc": 7664,  "L": 3.57, "Cp": 81e-12},
        # GFS Blues: measured R=6241Ω, L=2.44H, Cp=83pF
        {"name": "GFS Blues (measured, A5)",
         "rdc": 6241,  "L": 2.44, "Cp": 83e-12},
        # Tonerider Surfari: measured R=6557Ω, L=2.92H, Cp=102pF
        {"name": "Tonerider Surfari (measured, A5)",
         "rdc": 6557,  "L": 2.92, "Cp": 102e-12},
        # Generic hot single (e.g. SSL-5 style): ~12.9kΩ
        {"name": "Hot Strat bridge (overwound, A5)",
         "rdc": 12900, "L": 4.8,  "Cp": 85e-12},

        # ── Telecaster — measured ──────────────────────────────────────────
        # Fender MIJ Tele: measured R=6750Ω, L=2.00H, Cp=240pF
        # High Cp from metal baseplate proximity — darker than Strat SC
        {"name": "MIJ Tele bridge (measured, A5)",
         "rdc": 6750,  "L": 2.00, "Cp": 240e-12},
        # Fender MIM Ceram: measured R=7437Ω, L=4.12H, Cp=196pF
        {"name": "MIM Tele neck (measured, ceramic)",
         "rdc": 7437,  "L": 4.12, "Cp": 196e-12},
        # Generic Tele neck with steel baseplate (adds ~2H effective inductance)
        {"name": "Tele neck (steel baseplate, generic)",
         "rdc": 7200,  "L": 4.5,  "Cp": 75e-12},

        # ── Lipstick ──────────────────────────────────────────────────────
        # SD SLS-1 Lipstick: 4.3kΩ, resonant ~9.4kHz → L≈2.5H at 55pF
        {"name": "Lipstick tube (A5, 9.4kHz peak)",
         "rdc": 4300,  "L": 2.5,  "Cp": 55e-12},
    ],

    "p90": [
        # P90 soapbar: typically ~8H inductance (darker than PAF)
        # SD SP90-1 Vintage: measured resonant peak ~4.5kHz → L≈5H at 250pF? 
        # More realistically Cp~100pF → L≈4.8H
        {"name": "P-90 neck (vintage A5, soapbar)",
         "rdc": 7200,  "L": 7.0,  "Cp": 100e-12},
        {"name": "P-90 bridge (vintage A5, soapbar)",
         "rdc": 8000,  "L": 8.0,  "Cp": 100e-12},

        # Dog-ear P90 (slightly different winding)
        {"name": "P-90 neck (dog-ear)",
         "rdc": 7500,  "L": 7.5,  "Cp": 105e-12},

        # Hot P90 (overwound)
        {"name": "P-90 hot bridge",
         "rdc": 10000, "L": 9.5,  "Cp": 115e-12},

        # Mini-humbucker style (narrower coil, lower L)
        {"name": "Mini-humbucker (Firebird style)",
         "rdc": 6800,  "L": 4.0,  "Cp": 80e-12},
    ],
}

# Default pickup positions (mm from bridge, scale length mm)
POSITION_DEFAULTS = {
    "neck":   {"dist_mm": 170, "scale_mm": 628},
    "middle": {"dist_mm": 90,  "scale_mm": 648},
    "bridge": {"dist_mm": 38,  "scale_mm": 628},
}

LAYOUTS = {
    # topology fields:
    #   shared_vol: True = one master volume knob for all pickups
    #   tone_map:   list, one entry per pickup — "tone1", "tone2", or None (no tone pot)
    #               None means pickup goes straight to volume with no tone cap shunt
    "HH":  {"pickups": [{"pos":"neck",   "type":"humbucker", "polarity": 1},
                         {"pos":"bridge", "type":"humbucker", "polarity": 1}],
             "shared_vol": False,
             "tone_map":   ["tone1", "tone2"]},

    "HSS": {"pickups": [{"pos":"neck",   "type":"humbucker", "polarity": 1},
                         {"pos":"middle", "type":"single",    "polarity":-1},  # RWRP
                         {"pos":"bridge", "type":"single",    "polarity": 1}],
             "shared_vol": True,
             "tone_map":   ["tone1", "tone2", None]},

    "HHS": {"pickups": [{"pos":"neck",   "type":"humbucker", "polarity": 1},
                         {"pos":"middle", "type":"humbucker", "polarity": 1},
                         {"pos":"bridge", "type":"single",    "polarity":-1}],  # RWRP
             "shared_vol": True,
             "tone_map":   ["tone1", "tone2", None]},

    "SSS": {"pickups": [{"pos":"neck",   "type":"single", "polarity": 1},
                         {"pos":"middle", "type":"single", "polarity":-1},  # RWRP
                         {"pos":"bridge", "type":"single", "polarity": 1}],
             "shared_vol": True,
             "tone_map":   ["tone1", "tone2", None]},

    "H":   {"pickups": [{"pos":"bridge", "type":"humbucker", "polarity": 1}],
             "shared_vol": False,
             "tone_map":   ["tone1"]},

    "SS":  {"pickups": [{"pos":"neck",   "type":"single", "polarity": 1},
                         {"pos":"bridge", "type":"single", "polarity": 1}],
             "shared_vol": True,
             "tone_map":   ["tone1", "tone1"]},
}
