"""
pickup_db.py — pickup electrical parameter database
All values: rdc in Ohms, L in Henries, Cp in Farads
"""

PICKUPS = {
    "humbucker": [
        {"name": "PAF-style (low wind)",   "rdc": 7500,  "L": 3.8, "Cp": 120e-12},
        {"name": "PAF-style (high wind)",  "rdc": 8500,  "L": 4.2, "Cp": 140e-12},
        {"name": "Seth Lover style",       "rdc": 7800,  "L": 4.0, "Cp": 130e-12},
        {"name": "hot humbucker",          "rdc": 13000, "L": 5.5, "Cp": 160e-12},
        {"name": "vintage PAF bridge",     "rdc": 8200,  "L": 4.1, "Cp": 135e-12},
    ],
    "single": [
        {"name": "Strat neck (vintage)",   "rdc": 5800,  "L": 2.2, "Cp": 60e-12},
        {"name": "Strat bridge (vintage)", "rdc": 6400,  "L": 2.5, "Cp": 65e-12},
        {"name": "Tele neck",              "rdc": 7200,  "L": 2.8, "Cp": 70e-12},
        {"name": "Tele bridge",            "rdc": 7800,  "L": 3.0, "Cp": 75e-12},
        {"name": "overwound single",       "rdc": 9000,  "L": 3.4, "Cp": 85e-12},
    ],
    "p90": [
        {"name": "P-90 neck (vintage)",    "rdc": 7200,  "L": 4.5, "Cp": 90e-12},
        {"name": "P-90 bridge (vintage)",  "rdc": 8000,  "L": 5.0, "Cp": 95e-12},
        {"name": "P-90 soapbar",           "rdc": 7600,  "L": 4.7, "Cp": 92e-12},
        {"name": "hot P-90",               "rdc": 10000, "L": 5.8, "Cp": 110e-12},
    ],
}

# Default pickup positions (mm from bridge, scale length mm)
POSITION_DEFAULTS = {
    "neck":   {"dist_mm": 170, "scale_mm": 628},
    "middle": {"dist_mm": 90,  "scale_mm": 648},
    "bridge": {"dist_mm": 38,  "scale_mm": 628},
}

LAYOUTS = {
    "HH":  [{"pos": "neck",   "type": "humbucker"},
            {"pos": "bridge", "type": "humbucker"}],
    "HSS": [{"pos": "neck",   "type": "humbucker"},
            {"pos": "middle", "type": "single"},
            {"pos": "bridge", "type": "single"}],
    "HHS": [{"pos": "neck",   "type": "humbucker"},
            {"pos": "middle", "type": "humbucker"},
            {"pos": "bridge", "type": "single"}],
    "SSS": [{"pos": "neck",   "type": "single"},
            {"pos": "middle", "type": "single"},
            {"pos": "bridge", "type": "single"}],
    "H":   [{"pos": "bridge", "type": "humbucker"}],
    "SS":  [{"pos": "neck",   "type": "single"},
            {"pos": "bridge", "type": "single"}],
}
