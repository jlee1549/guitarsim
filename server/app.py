"""
app.py — trame application entry point

Run with:
    python app.py
Then open http://localhost:8080 in a browser.

Requires: trame trame-vuetify trame-matplotlib numpy scipy
"""

from trame.app import get_server
from trame.ui.vuetify3 import SinglePageLayout
from trame.widgets import vuetify3 as v, html
from trame.decorators import TrameApp, change

import numpy as np
from simulation import PickupParams, sweep, FREQS
from audio import render_strum
from pickup_db import PICKUPS, LAYOUTS, POSITION_DEFAULTS
import base64


@TrameApp()
class GuitarSimApp:
    def __init__(self, server=None):
        self.server = server or get_server()
        self.state  = self.server.state
        self.ctrl   = self.server.controller

        # ── default state ────────────────────────────────────────────────
        self.state.layout     = "HH"
        self.state.wiring     = "50s"
        self.state.tbleed     = "none"
        self.state.ccable_pf  = 500
        self.state.toggle_idx = 1   # "both" for HH
        self.state.audio_b64  = ""  # base64 WAV for client playback
        self.state.freq_labels = [f"{int(f)}" for f in FREQS]

        # Pickup state: list of dicts, one per pickup in current layout
        self._init_pickups("HH")
        self._build_ui()

    def _init_pickups(self, layout_name: str):
        defs = LAYOUTS[layout_name]
        pickups = []
        for d in defs:
            db = PICKUPS[d["type"]]
            pos = d["pos"]
            defaults = POSITION_DEFAULTS.get(pos, {"dist_mm": 80, "scale_mm": 628})
            pickups.append({
                "pos":        pos,
                "type":       d["type"],
                "preset_idx": 0,
                "rdc":        db[0]["rdc"],
                "L":          db[0]["L"],
                "Cp":         db[0]["Cp"],
                "Rvol":       500e3,
                "Rtone":      500e3,
                "Ctone":      22e-9,
                "vol_knob":   10.0,
                "tone_knob":  10.0,
                "dist_mm":    defaults["dist_mm"],
                "scale_mm":   defaults["scale_mm"],
            })
        self.state.pickups = pickups
        self.state.toggle_options = self._toggle_options(len(defs))
        self.state.toggle_idx = next(
            (i for i, t in enumerate(self.state.toggle_options) if len(t["active"]) == len(defs)), 0
        )

    @staticmethod
    def _toggle_options(n: int) -> list:
        presets = {
            1: [{"label": "bridge", "active": [0]}],
            2: [{"label": "neck",   "active": [0]},
                {"label": "both",   "active": [0, 1]},
                {"label": "bridge", "active": [1]}],
            3: [{"label": "neck",      "active": [0]},
                {"label": "neck+mid",  "active": [0, 1]},
                {"label": "mid",       "active": [1]},
                {"label": "mid+brdg",  "active": [1, 2]},
                {"label": "bridge",    "active": [2]}],
        }
        return presets.get(n, presets[2])

    def _make_pickup_params(self) -> list[PickupParams]:
        return [
            PickupParams(
                rdc=p["rdc"], L=p["L"], Cp=p["Cp"],
                Rvol=p["Rvol"], Rtone=p["Rtone"], Ctone=p["Ctone"],
                vol_knob=p["vol_knob"], tone_knob=p["tone_knob"],
                dist_mm=p["dist_mm"], scale_mm=p["scale_mm"],
            )
            for p in self.state.pickups
        ]

    def _active_indices(self) -> list[int]:
        opts = self.state.toggle_options
        idx  = self.state.toggle_idx
        return opts[idx]["active"] if idx < len(opts) else [0]

    def _compute(self) -> tuple[np.ndarray, np.ndarray]:
        """Return (current_db, reference_db) arrays."""
        pus    = self._make_pickup_params()
        active = self._active_indices()
        cable  = self.state.ccable_pf * 1e-12
        tbleed = self.state.tbleed
        wiring = self.state.wiring

        cur = sweep(pus, active, cable, tbleed, wiring)
        ref_pus = [PickupParams(**{**vars(p), "vol_knob": 10, "tone_knob": 10})
                   for p in pus]
        ref = sweep(ref_pus, active, cable, tbleed, wiring)

        anchor = np.max(ref) or 1.0
        cur_db = 20 * np.log10(np.clip(cur / anchor, 1e-12, None))
        ref_db = 20 * np.log10(np.clip(ref / anchor, 1e-12, None))
        return cur_db, ref_db

    @change("layout")
    def on_layout_change(self, layout, **_):
        self._init_pickups(layout)
        self.ctrl.update_chart()

    @change("wiring", "tbleed", "ccable_pf", "pickups", "toggle_idx")
    def on_param_change(self, **_):
        self.ctrl.update_chart()

    def update_chart(self):
        cur_db, ref_db = self._compute()
        self.state.chart_cur = cur_db.tolist()
        self.state.chart_ref = ref_db.tolist()

    def strum(self):
        pus    = self._make_pickup_params()
        active = self._active_indices()
        cable  = self.state.ccable_pf * 1e-12
        resp   = sweep(pus, active, cable, self.state.tbleed, self.state.wiring)
        wav    = render_strum(resp)
        self.state.audio_b64 = base64.b64encode(wav).decode()

    def _build_ui(self):
        self.ctrl.update_chart = self.update_chart
        with SinglePageLayout(self.server) as layout:
            layout.title.set_text("Guitar Electronics Simulator")
            with layout.content:
                html.Div("trame UI — work in progress", style="padding:2rem;color:#888;")


def main():
    app = GuitarSimApp()
    app.server.start()


if __name__ == "__main__":
    main()
