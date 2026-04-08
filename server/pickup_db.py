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
         "rdc": 7500,  "L": 4.5,  "Cp": 100e-12},
        {"name": "PAF bridge (vintage A2)",
         "rdc": 8200,  "L": 5.0,  "Cp": 100e-12},

        # Seth Lover Model (SD SH-55): measured by Darth Phineas
        # Neck: 7.535kΩ, 3.733H  Bridge: 8.327kΩ, 4.612H
        {"name": "Seth Lover neck (A2, 8.14 kHz peak)",
         "rdc": 7535,  "L": 3.733, "Cp": 110e-12},
        {"name": "Seth Lover bridge (A2, 5.9 kHz peak)",
         "rdc": 8327,  "L": 4.612, "Cp": 130e-12},

        # Alnico II Pro (SD APH-1): neck 7.6kΩ / 7.1kHz, bridge 7.85kΩ / 6.7kHz
        # L derived: neck ~4.2H, bridge ~4.5H at Cp≈120pF
        {"name": "Alnico II Pro neck (7.1 kHz peak)",
         "rdc": 7600,  "L": 4.2,  "Cp": 120e-12},
        {"name": "Alnico II Pro bridge (6.7 kHz peak)",
         "rdc": 7850,  "L": 4.5,  "Cp": 120e-12},

        # Gibson '57 Classic / Burstbucker style
        {"name": "'57 Classic / Burstbucker neck",
         "rdc": 7800,  "L": 4.8,  "Cp": 110e-12},
        {"name": "'57 Classic / Burstbucker bridge",
         "rdc": 8500,  "L": 5.2,  "Cp": 110e-12},

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
        # SD JB (SH-4): measured 16.2kΩ, 8.54H (guitarhacking) — very dark
        # Resonant peak ~2.76kHz. Ceramic magnet version.
        {"name": "JB bridge (ceramic, 2.76 kHz peak)",
         "rdc": 16200, "L": 8.54, "Cp": 150e-12},

        # SD Custom Custom: 14kΩ, 9.35H (Bedlam Guitars measured)
        {"name": "Custom Custom bridge (A2)",
         "rdc": 14000, "L": 9.35, "Cp": 150e-12},

        # SD Distortion (SH-6): ~13.4kΩ, ceramic, very hot
        {"name": "Distortion bridge (ceramic)",
         "rdc": 13400, "L": 7.5,  "Cp": 160e-12},

        # DiMarzio Super Distortion: ~13.6kΩ, classic high output
        {"name": "Super Distortion bridge",
         "rdc": 13600, "L": 7.8,  "Cp": 155e-12},

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
        # ── Stratocaster ──────────────────────────────────────────────────
        # Vintage spec: neck ~5.8kΩ / ~2.2H, bridge ~6.4kΩ / ~2.5H
        {"name": "Strat neck (vintage A5, ~6.5kHz)",
         "rdc": 5800,  "L": 2.2,  "Cp": 60e-12},
        {"name": "Strat middle (RWRP)",
         "rdc": 5900,  "L": 2.3,  "Cp": 60e-12},
        {"name": "Strat bridge (vintage A5)",
         "rdc": 6400,  "L": 2.5,  "Cp": 65e-12},

        # SD SSL-1 vintage: ~5.8kΩ, A5
        {"name": "SSL-1 Vintage Strat (A5)",
         "rdc": 5800,  "L": 2.2,  "Cp": 62e-12},

        # Overwound / hot single (e.g. SD SSL-5 Custom): ~12.9kΩ
        {"name": "Hot Strat bridge (Custom, A5)",
         "rdc": 12900, "L": 4.8,  "Cp": 85e-12},

        # Texas Special / Blues style: moderate output, warm
        {"name": "Texas Special neck (A5, warm)",
         "rdc": 7200,  "L": 2.8,  "Cp": 70e-12},

        # DiMarzio Area 58 noiseless: ~5.02kHz resonant peak
        {"name": "Noiseless (Area-style, 5kHz peak)",
         "rdc": 8500,  "L": 3.2,  "Cp": 80e-12},

        # ── Telecaster ───────────────────────────────────────────────────
        # Tele neck: higher inductance due to cover/steel baseplate effect
        {"name": "Tele neck (with steel baseplate, ~4.5H)",
         "rdc": 7200,  "L": 4.5,  "Cp": 75e-12},
        {"name": "Tele bridge (brass baseplate)",
         "rdc": 7800,  "L": 3.0,  "Cp": 72e-12},
        {"name": "Tele bridge (hot, A5)",
         "rdc": 9500,  "L": 3.8,  "Cp": 80e-12},

        # ── Lipstick / specialty ─────────────────────────────────────────
        # SD SLS-1 Lipstick: 4.3kΩ, 9.4kHz resonant peak → L≈2.5H at 55pF
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
