# SPDX-License-Identifier: BSD-3-Clause
"""
app.py — Guitar Electronics Simulator (trame)

Graph: Chart.js rendered via client.Script — no trame-plotly dependency.
Audio: WAV bytes pushed as base64 state, decoded via Web Audio API in JS.
State: flat indexed keys for pickup params (trame watches top-level keys).
"""
from trame.app import get_server
from trame.ui.vuetify3 import SinglePageLayout
from trame.widgets import vuetify3 as v, html, client
from trame.widgets import plotly as plotly_widget
from trame.decorators import TrameApp, change

import numpy as np, base64

from taper_utils import vol_pct_to_knob, knob_to_vol_pct
from simulation import PickupParams, sweep, FREQS
from audio import render_pluck, OPEN_STRINGS, STRING_NAMES, DEFAULT_PLUCK_POS
from pickup_db import PICKUPS, LAYOUTS, POSITION_DEFAULTS
from wiring import make_wiring_svg
from plotly_fig import make_fr_figure

MAX_PU = 3
COLORS = ["#378ADD", "#D85A30", "#1D9E75"]
POT_ITEMS   = [{"title":"250 kΩ","value":250000},{"title":"500 kΩ","value":500000},{"title":"1 MΩ","value":1000000}]
TAPER_ITEMS = [{"title":"Audio / log (A)","value":"audio"},{"title":"Linear (B)","value":"linear"},
               {"title":"Custom 15% (RS SuperPot)","value":"custom_15"},{"title":"Custom 30% (vintage)","value":"custom_30"}]
TBLEED_ITEMS= [{"title":"None","value":"none"},{"title":"Cap only (100 pF)","value":"cap"},
               {"title":"Cap + 150kΩ","value":"network"}]
LAYOUT_ITEMS= [{"title":"HH — Les Paul","value":"HH"},{"title":"HSS — Strat","value":"HSS"},
               {"title":"HHS","value":"HHS"},{"title":"SSS — 3× single","value":"SSS"},
               {"title":"H — solo HB","value":"H"},{"title":"SS — Telecaster","value":"SS"}]
WIRING_ITEMS= [{"title":"50s wiring","value":"50s"},{"title":"Modern wiring","value":"modern"}]

def _toggle_options(n):
    p={1:[["bridge",[0]]],
       2:[["neck",[0]],["both",[0,1]],["bridge",[1]]],
       3:[["neck",[0]],["neck+mid",[0,1]],["mid",[1]],["mid+brdg",[1,2]],["bridge",[2]]]}
    return [{"label":a,"active":b} for a,b in p.get(n,p[2])]

def _default_pu(pos, ptype):
    db  = PICKUPS[ptype]; dp = POSITION_DEFAULTS.get(pos,{"dist_mm":80,"scale_mm":628})
    # Pick a position-appropriate default preset: prefer one whose name contains
    # the position keyword (neck/bridge/middle). Fall back to first preset.
    preset_idx = 0
    entry = db[0]
    for i, candidate in enumerate(db):
        if pos in candidate["name"].lower():
            entry = candidate
            preset_idx = i
            break
    return {"pos":pos,"type":ptype,
            "preset_idx": preset_idx,
            "rdc":entry["rdc"],"L":entry["L"],"Cp":entry["Cp"],
            "base_rdc":entry["rdc"],"base_L":entry["L"],"base_Cp":entry["Cp"],
            "Rd": entry.get("Rd", 0.0), "Ld": entry.get("Ld", 0.0),
            "Rvol":500000,"Rtone":500000,"Ctone_nf":22,
            "vol_knob":10.0,"tone_knob":10.0,
            "vol_pct":100.0,"tone_pct":100.0,
            "polarity":1, "coil_config":"series", "coil_side":"outer",
            "dist_mm":dp["dist_mm"],"height_mm":2.5,"tbleed":"none","has_tone":True}

@TrameApp()
class GuitarSim:
    def __init__(self, server=None):
        self.server = server or get_server()
        self.state  = self.server.state
        self.ctrl   = self.server.controller

        # Shared
        self.state.layout      = "HH"
        self.state.wiring      = "50s"
        self.state.ccable_pf   = 200       # typical 3m cable ~100-300pF
        self.state.r_amp_kohm  = 1000      # amp input impedance in kΩ (1MΩ = tube amp typical)
        self.state.scale_mm    = 628       # instrument scale length (shared)
        self.state.vol_taper   = "audio"
        self.state.tone_taper  = "audio"
        self.state.toggle_idx  = 1
        self.state.tog_options = _toggle_options(2)
        self.state.n_pickups   = 2
        self.state.pu_labels   = ["neck (HB)","bridge (HB)",""]
        self.state.pluck_string= 1
        self.state.pluck_pos   = 12
        self.state.string_items= [{"title":f"{STRING_NAMES[i]} — {OPEN_STRINGS[i]:.1f} Hz","value":i} for i in range(6)]
        self.state.busy        = False
        self.state.status_msg  = "ready"
        self.state.audio_b64   = ""
        self.state.audio_token = 0
        self.state.wiring_svg  = ""   # SVG string (legacy)
        self.state.wiring_src  = ""   # base64 data URI for <img>

        # Plotly figure widget reference (set during layout build)
        self._plotly_fig = None

        # Topology state — shared vs independent controls
        self.state.shared_vol   = False   # HH: independent vol per pickup
        self.state.tone_map     = ["tone1","tone2",""]  # per-pickup tone assignment
        self.state.master_vol   = 100.0   # 0-100% wiper position
        self.state.tone1_knob   = 100.0   # 0-100% wiper position
        self.state.tone2_knob   = 100.0   # 0-100% wiper position

        # Preset lists — value is index so trame state gets an int, not a string
        self.state.hb_presets  = [{"title": p["name"], "value": i} for i,p in enumerate(PICKUPS["humbucker"])]
        self.state.sc_presets  = [{"title": p["name"], "value": i} for i,p in enumerate(PICKUPS["single"])]
        self.state.p90_presets = [{"title": p["name"], "value": i} for i,p in enumerate(PICKUPS["p90"])]

        # Flat pickup state
        self._pu_data = [_default_pu("neck","humbucker"),
                         _default_pu("bridge","humbucker"),
                         _default_pu("bridge","humbucker")]
        for i in range(MAX_PU):
            setattr(self.state, f"pu{i}_preset",      0)
            setattr(self.state, f"pu{i}_presets",     [{"title":"loading...","value":0}])
            setattr(self.state, f"pu{i}_polarity",    1)
            setattr(self.state, f"pu{i}_coil_config", "series")
            setattr(self.state, f"pu{i}_coil_side",   "outer")
            setattr(self.state, f"pu{i}_is_hb",       True)
        self._push_pu_state()  # overwrites with real values

        # Chart state — plain lists, rendered by Chart.js in client.Script
        self._freqs = [round(f,1) for f in FREQS.tolist()]
        self.state.chart_freqs  = self._freqs
        self.state.chart_cur    = [0.0]*len(FREQS)
        self.state.chart_ref    = [0.0]*len(FREQS)
        self.state.chart_audio      = []
        self.state.chart_audio_ref  = []
        self.state.audio_ref_label  = ""
        self.state.chart_stats  = {"peak":0,"db200":0.0,"db500":0.0,"db1k":0.0,"db4k":0.0}
        self.state.chart_note   = ""

        self._compute_and_push()
        self._build_ui()
        # Push initial figure and wiring now that the plotly widget is instantiated
        self._push_plotly_fig(
            self.state.chart_cur, self.state.chart_ref, None, None
        )
        self._push_wiring_svg()

    # ── flat state helpers ────────────────────────────────────────────────
    def _push_pu_state(self):
        for i,p in enumerate(self._pu_data):
            ptype = p["type"]
            presets_list = {"humbucker": self.state.hb_presets,
                            "single":    self.state.sc_presets,
                            "p90":       self.state.p90_presets}.get(ptype, self.state.hb_presets)
            setattr(self.state,f"pu{i}_presets",     presets_list)
            setattr(self.state,f"pu{i}_preset",      p.get("preset_idx", 0))
            setattr(self.state,f"pu{i}_vol",         p["vol_pct"])
            setattr(self.state,f"pu{i}_tone",        p["tone_pct"])
            setattr(self.state,f"pu{i}_rvol",        p["Rvol"])
            setattr(self.state,f"pu{i}_rtone",       p["Rtone"])
            setattr(self.state,f"pu{i}_ctone_nf",    p["Ctone_nf"])
            setattr(self.state,f"pu{i}_dist_mm",     p["dist_mm"])
            setattr(self.state,f"pu{i}_height_mm",   p["height_mm"])
            setattr(self.state,f"pu{i}_tbleed",      p["tbleed"])
            setattr(self.state,f"pu{i}_polarity",    p["polarity"])
            setattr(self.state,f"pu{i}_coil_config", p["coil_config"])
            setattr(self.state,f"pu{i}_coil_side",   p["coil_side"])
            setattr(self.state,f"pu{i}_is_hb",       ptype == "humbucker")

    def _pull_pu_state(self):
        for i in range(MAX_PU):
            vol_pct  = float(getattr(self.state, f"pu{i}_vol",  100.0))
            tone_pct = float(getattr(self.state, f"pu{i}_tone", 100.0))
            polarity    = int(getattr(self.state, f"pu{i}_polarity",    1))
            coil_config = str(getattr(self.state, f"pu{i}_coil_config", "series"))
            coil_side   = str(getattr(self.state, f"pu{i}_coil_side",   "outer"))
            self._pu_data[i]["vol_pct"]      = vol_pct
            self._pu_data[i]["tone_pct"]     = tone_pct
            self._pu_data[i]["vol_knob"]     = vol_pct_to_knob(vol_pct)
            self._pu_data[i]["tone_knob"]    = vol_pct_to_knob(tone_pct)
            self._pu_data[i]["polarity"]     = polarity
            self._pu_data[i]["coil_config"]  = coil_config
            self._pu_data[i]["coil_side"]    = coil_side
            self._pu_data[i]["Rvol"]         = getattr(self.state,f"pu{i}_rvol",    500000)
            self._pu_data[i]["Rtone"]        = getattr(self.state,f"pu{i}_rtone",   500000)
            self._pu_data[i]["Ctone_nf"]     = getattr(self.state,f"pu{i}_ctone_nf",22)
            self._pu_data[i]["dist_mm"]      = getattr(self.state,f"pu{i}_dist_mm", 80)
            self._pu_data[i]["height_mm"]    = getattr(self.state,f"pu{i}_height_mm", 2.5)
            self._pu_data[i]["tbleed"]       = getattr(self.state,f"pu{i}_tbleed",  "none")
            # Apply coil config scaling from measured GuitarFreak data.
            # PAF Pro measured: series(rdc=9687,L=4.318,Cp=120) vs
            #   parallel(rdc=2435,L=1.459,Cp=276) vs split(rdc=5045,L=2.123,Cp=177)
            # rdc: parallel=rdc/4, split=rdc/2 (one coil)
            # L:   parallel=L/4 (N^2), split=L/2 (N^2 for half turns ≈ L/4 but
            #      measured shows L_split ≈ L/2 — coil coupling effect)
            # Cp:  does NOT halve — self-cap increases relative to L.
            #      parallel≈2.3x full, split≈1.5x full (measured)
            br = self._pu_data[i]["base_rdc"]
            bL = self._pu_data[i]["base_L"]
            bC = self._pu_data[i]["base_Cp"]
            if coil_config == "parallel":
                self._pu_data[i]["rdc"] = br / 4      # two coils in parallel
                self._pu_data[i]["L"]   = bL / 4      # L ~ N^2
                self._pu_data[i]["Cp"]  = bC * 2.3    # measured ≈ 2.3x series
            elif coil_config == "split":
                self._pu_data[i]["rdc"] = br / 2      # one coil, half turns
                self._pu_data[i]["L"]   = bL / 4      # L ~ N^2 for half turns
                self._pu_data[i]["Cp"]  = bC * 1.5    # measured ≈ 1.5x series
                # Inner coil is ~10mm further from bridge than outer.
                # Outer = bridge-side coil (slightly brighter comb character).
                # Inner = neck-side coil (slightly darker comb character).
                base_dist = POSITION_DEFAULTS.get(self._pu_data[i]["pos"], {"dist_mm": 80})["dist_mm"]
                offset = -10 if coil_side == "outer" else +10
                self._pu_data[i]["dist_mm"] = max(5, base_dist + offset)
            else:  # series (default)
                self._pu_data[i]["rdc"] = br
                self._pu_data[i]["L"]   = bL
                self._pu_data[i]["Cp"]  = bC

    def _active(self):
        opts = self.state.tog_options; idx = self.state.toggle_idx
        return opts[idx]["active"] if 0 <= idx < len(opts) else [0]

    def _make_params(self):
        self._pull_pu_state()
        scale       = self.state.scale_mm
        shared_vol  = self.state.shared_vol
        master_pct  = float(self.state.master_vol)             # 0-100 wiper pct
        master_vol  = vol_pct_to_knob(master_pct)             # for legacy knob field
        tmap        = self.state.tone_map
        tone1_pct   = float(self.state.tone1_knob)            # 0-100 wiper pct
        tone2_pct   = float(self.state.tone2_knob)
        tone1       = vol_pct_to_knob(tone1_pct)              # for legacy knob field
        tone2       = vol_pct_to_knob(tone2_pct)

        params = []
        for i, p in enumerate(self._pu_data):
            vol_knob = master_vol if shared_vol else p["vol_knob"]
            t = tmap[i] if i < len(tmap) else ""
            if not shared_vol:
                # Independent controls (HH Les Paul): each pickup uses its own
                # per-pickup tone knob directly. tone_map only applies for shared layouts.
                tone_knob = p["tone_knob"]
                has_tone  = True
            elif t == "tone1":
                tone_knob = tone1
                has_tone  = True
            elif t == "tone2":
                tone_knob = tone2
                has_tone  = True
            else:
                tone_knob = 10.0   # no tone pot (e.g. SSS bridge)
                has_tone  = False

            # vol_alpha/tone_alpha = direct wiper fraction from slider pct.
            # This bypasses apply_taper() in channel_gain, so taper selector
            # does not affect the simulation — slider position IS the alpha.
            v_alpha = (p["vol_pct"] / 100.0) if not shared_vol else (master_pct / 100.0)
            # Pickup height: output scales as (ref/h)^2 (inverse-square law).
            # Reference height 2.5mm. Multiply into vol_alpha so it scales
            # the pickup's contribution to the mix the same way height does on a real guitar.
            h = float(p.get("height_mm", 2.5))
            height_gain = (2.5 / max(h, 0.5)) ** 2
            v_alpha = min(1.0, v_alpha * height_gain)
            if not shared_vol:
                # HH: per-pickup tone slider stored in p["tone_pct"]
                t_alpha = p["tone_pct"] / 100.0
            elif t == "tone1": t_alpha = tone1_pct / 100.0
            elif t == "tone2": t_alpha = tone2_pct / 100.0
            else:              t_alpha = 1.0

            params.append(PickupParams(
                rdc=p["rdc"], L=p["L"], Cp=p["Cp"],
                Rvol=p["Rvol"], Rtone=p["Rtone"], Ctone=p["Ctone_nf"]*1e-9,
                vol_knob=vol_knob, tone_knob=tone_knob,
                dist_mm=p["dist_mm"], scale_mm=scale,
                vol_taper=self.state.vol_taper, tone_taper=self.state.tone_taper,
                tbleed=p["tbleed"], has_tone=has_tone,
                vol_alpha=v_alpha, tone_alpha=t_alpha if has_tone else -1.0,
                polarity=p["polarity"],
                Rd_ohm=p.get("Rd", 0.0), Ld_H=p.get("Ld", 0.0),
            ))
        return params

    def _make_ref_params(self):
        """Same topology as _make_params() but all pots wide open (reference curve)."""
        base = self._make_params()
        result = []
        for p in base:
            import dataclasses
            result.append(dataclasses.replace(p,
                vol_knob=10.0, tone_knob=10.0,
                vol_alpha=1.0, tone_alpha=1.0))
        return result

    def _make_tone_open_params(self):
        """Same as _make_params() but tone wide open — isolates tone pot effect in audio FR."""
        base = self._make_params()
        result = []
        for p in base:
            import dataclasses
            result.append(dataclasses.replace(p,
                tone_knob=10.0, tone_alpha=1.0))
        return result

    def _push_plotly_fig(self, cur_db, ref_db, audio_db=None, audio_ref_db=None):
        """Build and push a Plotly figure to the trame-plotly widget."""
        if self._plotly_fig is None:
            return
        fig = make_fr_figure(
            list(FREQS), cur_db, ref_db,
            list(audio_db) if audio_db else None,
            list(audio_ref_db) if audio_ref_db else None,
        )
        self._plotly_fig.update(fig)

    def _push_wiring_svg(self):
        """Generate SVG wiring diagram and push as base64 data URI to avoid trame HTML sanitisation."""
        n = self.state.n_pickups
        active = self._active()
        pu_data = self._pu_data[:n]
        svg_str = make_wiring_svg(
            pu_data,
            self.state.layout,
            self.state.wiring,
            active,
            self.state.shared_vol,
            self.state.tone_map,
        )
        import base64
        b64 = base64.b64encode(svg_str.encode()).decode()
        self.state.wiring_src = f"data:image/svg+xml;base64,{b64}"

    def _compute_and_push(self):
        self._pull_pu_state()
        cable  = self.state.ccable_pf * 1e-12
        r_amp  = self.state.r_amp_kohm * 1e3
        active = self._active()
        pus    = self._make_params()
        # Chart shows electronics-only response without position comb.
        # The string-position comb is note/string-dependent and belongs only
        # in the audio render, not on a frequency response reference chart.
        # RWRP combinations will show near-cancellation — this is correct;
        # the quack comes from the comb breaking that cancellation selectively.
        cur    = sweep(pus, active, cable, self.state.wiring, R_amp=r_amp, include_position=False)
        ref    = sweep(self._make_ref_params(), active, cable, self.state.wiring, R_amp=r_amp, include_position=False)

        anchor = float(np.max(ref)) or 1.0
        cur_db = (20*np.log10(np.clip(cur/anchor,1e-12,None))).tolist()
        ref_db = (20*np.log10(np.clip(ref/anchor,1e-12,None))).tolist()

        self.state.chart_cur   = cur_db
        self.state.chart_ref   = ref_db
        self.state.chart_audio = []   # clear audio FR when electronics change

        def at(f): return round(cur_db[int(np.argmin(np.abs(FREQS-f)))],1)
        self.state.chart_stats = {"peak":round(float(FREQS[int(np.argmax(cur_db))])),"db200":at(200),"db500":at(500),"db1k":at(1000),"db4k":at(4000)}

        # Update Plotly figure
        self._push_plotly_fig(cur_db, ref_db,
                              self.state.chart_audio or None,
                              self.state.chart_audio_ref or None)
        # Update wiring SVG
        self._push_wiring_svg()

        # Note when polarity would affect response (only audible via audio render)
        polarities = [pus[i].polarity for i in active]
        has_rwrp = len(active) > 1 and len(set(polarities)) > 1
        self.state.chart_note = "Polarity effect visible only in audio (requires position comb)" if has_rwrp else ""

    # ── reactive handlers ─────────────────────────────────────────────────
    @change("layout")
    def on_layout(self, layout, **_):
        defn  = LAYOUTS[layout]
        defs  = defn["pickups"]
        n     = len(defs)
        tmap  = defn["tone_map"]
        for i, d in enumerate(defs):
            self._pu_data[i] = _default_pu(d["pos"], d["type"])
            self._pu_data[i]["has_tone"] = (tmap[i] is not None)
            self._pu_data[i]["polarity"] = d.get("polarity", 1)
        # Reset all knob state to wide-open
        for i in range(MAX_PU):
            setattr(self.state, f"pu{i}_preset",      0)
            setattr(self.state, f"pu{i}_vol",         100.0)
            setattr(self.state, f"pu{i}_tone",        100.0)
            setattr(self.state, f"pu{i}_coil_config", "series")
            pol = defs[i].get("polarity", 1) if i < len(defs) else 1
            setattr(self.state, f"pu{i}_polarity", pol)
        self.state.master_vol  = 100.0
        self.state.tone1_knob  = 100.0
        self.state.tone2_knob  = 100.0
        # Update topology state
        self.state.shared_vol  = defn["shared_vol"]
        self.state.tone_map    = [t or "" for t in tmap] + [""] * (MAX_PU - n)
        self.state.n_pickups   = n
        self.state.pu_labels   = [
            f"{d['pos']} ({'HB' if d['type']=='humbucker' else 'P90' if d['type']=='p90' else 'SC'})"
            for d in defs
        ] + [""] * (MAX_PU - n)
        self.state.tog_options = _toggle_options(n)
        self.state.toggle_idx  = next(
            (i for i,t in enumerate(self.state.tog_options) if len(t["active"]) == n), 0)
        # Push pickup data (presets list, rvol, etc.) and recompute
        self._push_pu_state()
        self._compute_and_push()

    @change("wiring","ccable_pf","r_amp_kohm","toggle_idx","scale_mm","vol_taper","tone_taper",
            "master_vol","tone1_knob","tone2_knob")
    def on_shared(self, **_):
        self._compute_and_push()

    def _make_pu_watcher(self, i):
        keys = [f"pu{i}_vol",f"pu{i}_tone",f"pu{i}_rvol",f"pu{i}_rtone",
                f"pu{i}_ctone_nf",f"pu{i}_dist_mm",f"pu{i}_height_mm",f"pu{i}_tbleed",
                f"pu{i}_polarity",f"pu{i}_coil_config",f"pu{i}_coil_side"]
        @self.state.change(*keys)
        def _watch(**_): self._compute_and_push()

    def _make_preset_watcher(self, i):
        @self.state.change(f"pu{i}_preset")
        def _on_preset(**kw):
            try:
                preset_idx = int(getattr(self.state, f"pu{i}_preset", 0))
            except (TypeError, ValueError):
                return
            ptype = self._pu_data[i]["type"]
            db    = PICKUPS[ptype]
            if 0 <= preset_idx < len(db):
                p = db[preset_idx]
                self._pu_data[i]["preset_idx"] = preset_idx
                self._pu_data[i]["base_rdc"] = p["rdc"]
                self._pu_data[i]["base_L"]   = p["L"]
                self._pu_data[i]["base_Cp"]  = p["Cp"]
                self._pu_data[i]["rdc"]      = p["rdc"]
                self._pu_data[i]["L"]        = p["L"]
                self._pu_data[i]["Cp"]       = p["Cp"]
                self._pu_data[i]["Rd"]       = p.get("Rd", 0.0)
                self._pu_data[i]["Ld"]       = p.get("Ld", 0.0)
                # Reset coil config to series when preset changes
                self._pu_data[i]["coil_config"] = "series"
                setattr(self.state, f"pu{i}_coil_config", "series")
            self._compute_and_push()

    def set_audio_ref(self, *args, **kwargs):
        """Freeze current audio FR as the reference for comparison."""
        if self.state.chart_audio:
            self.state.chart_audio_ref = list(self.state.chart_audio)
            si = int(self.state.pluck_string)
            self.state.audio_ref_label = f"ref: {STRING_NAMES[si]}"
            self._push_plotly_fig(
                self.state.chart_cur, self.state.chart_ref,
                self.state.chart_audio or None,
                self.state.chart_audio_ref,
            )

    def pluck(self, *args, **kwargs):
        self.state.busy = True; self.state.status_msg = "rendering..."
        try:
            self._pull_pu_state()
            active = self._active()
            cable  = self.state.ccable_pf * 1e-12
            r_amp  = self.state.r_amp_kohm * 1e3
            pus    = self._make_params()
            si     = int(self.state.pluck_string)
            f0     = OPEN_STRINGS[si]
            resp   = sweep(pus, active, cable, self.state.wiring, R_amp=r_amp, f0=f0)
            ref    = sweep(self._make_ref_params(), active, cable, self.state.wiring, R_amp=r_amp, f0=f0)
            ref_gain = float(np.max(resp))/(float(np.max(ref)) or 1.0)
            # Magnetic inharmonicity from pickup height.
            # B_magnetic = K_MAG/h³ − K_MAG/h_ref³, zero below reference height.
            # Calibrated: h=1mm → B≈0.004 (audible chorus), h=2mm → B≈0.0003 (subtle).
            # Uses the closest active pickup to the string (lowest height_mm).
            K_MAG = 0.004 * (1.5 ** 3)   # gives B=0.004 at h=1.5mm, ≈0 at h≥2.5mm
            H_REF = 2.5
            inh_B = 0.0
            for idx in active:
                h = float(self._pu_data[idx].get("height_mm", H_REF))
                b = max(0.0, K_MAG / max(h, 0.5)**3 - K_MAG / H_REF**3)
                inh_B = max(inh_B, b)   # worst-case pickup dominates
            wav = render_pluck(resp, string_idx=si,
                               reference_gain=ref_gain,
                               inharmonicity_B=inh_B)
            self.state.audio_b64   = base64.b64encode(wav).decode()
            self.state.audio_token = (self.state.audio_token or 0) + 1
            self.state.status_msg  = f"plucked {STRING_NAMES[si]}"

            # Audio FR: dense-grid sweep with pickup position comb AND pluck position
            # weighting. Pluck at position p creates harmonic weights |sin(n*pi*p)|,
            # which in continuous freq is |sin(pi*f*p/f0)|. Combined with the pickup
            # comb, this gives the full string+position+electronics response shape.
            DENSE = np.logspace(np.log10(50), np.log10(20000), 4000)
            resp_dense = sweep(pus, active, cable, self.state.wiring,
                               R_amp=r_amp, f0=f0, include_position=True,
                               freqs=DENSE)
            # Pluck position weighting: |sin(pi*f*pluck_pos/f0)|
            pluck_p = self.state.pluck_pos / 100.0
            pluck_weight = np.abs(np.sin(np.pi * DENSE * pluck_p / f0))
            resp_dense = resp_dense * pluck_weight
            peak_dense = float(np.max(resp_dense)) or 1.0
            # Band-average onto FREQS with 1/3-octave windows
            audio_db = []
            for fc in FREQS:
                lo   = fc / (2 ** (1/6))
                hi   = fc * (2 ** (1/6))
                mask = (DENSE >= lo) & (DENSE <= hi)
                val  = np.mean(resp_dense[mask]) if mask.any() else 1e-9
                audio_db.append(round(float(20 * np.log10(max(val/peak_dense, 1e-9))), 2))
            self.state.chart_audio = audio_db
            # Refresh plotly figure with audio FR included
            self._push_plotly_fig(
                self.state.chart_cur, self.state.chart_ref,
                audio_db,
                self.state.chart_audio_ref or None,
            )

        except Exception as e:
            self.state.status_msg = f"error: {e}"
            import traceback; traceback.print_exc()
        finally:
            self.state.busy = False

    # ── UI ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        for i in range(MAX_PU):
            self._make_pu_watcher(i)
            self._make_preset_watcher(i)
        with SinglePageLayout(self.server) as layout:
            layout.title.set_text("Guitar Electronics Simulator")

            # ── JS: audio playback only (chart now handled by trame-plotly) ──
            client.Style("body{background:#f5f5f3;}")
            client.Script("""
(function(){

// ── Audio playback ─────────────────────────────────────────────────────────
var _ctx=null, _lastToken=-1;
function getCtx(){
  if(!_ctx) _ctx=new(window.AudioContext||window.webkitAudioContext)();
  if(_ctx.state==='suspended') _ctx.resume();
  return _ctx;
}
function playWav(b64){
  try{
    var binary=atob(b64), bytes=new Uint8Array(binary.length);
    for(var i=0;i<binary.length;i++) bytes[i]=binary.charCodeAt(i);
    if(bytes[0]!==82||bytes[1]!==73||bytes[2]!==70||bytes[3]!==70) return;
    var ctx=getCtx();
    ctx.decodeAudioData(bytes.buffer.slice(0),function(buf){
      var src=ctx.createBufferSource(), g=ctx.createGain();
      g.gain.value=0.8; src.buffer=buf;
      src.connect(g); g.connect(ctx.destination); src.start();
    },function(e){console.warn('decode error',e);});
  }catch(e){console.warn('playWav',e);}
}

// ── Panel divider drag ────────────────────────────────────────────────────
(function(){
  var dragging=false, startX=0, startW=0;
  function initDivider(){
    var divider = document.getElementById('panel-divider');
    var panel   = document.getElementById('wiring-panel');
    if(!divider || !panel){ setTimeout(initDivider, 300); return; }
    divider.addEventListener('mousedown', function(e){
      dragging=true;
      startX=e.clientX;
      startW=panel.getBoundingClientRect().width;
      divider.style.background='#b0b0a8';
      document.body.style.cursor='col-resize';
      document.body.style.userSelect='none';
      e.preventDefault();
    });
    window.addEventListener('mousemove', function(e){
      if(!dragging) return;
      var newW = Math.max(160, Math.min(700, startW + (e.clientX - startX)));
      panel.style.flexBasis = newW+'px';
    });
    window.addEventListener('mouseup', function(){
      if(!dragging) return;
      dragging=false;
      divider.style.background='';
      document.body.style.cursor='';
      document.body.style.userSelect='';
    });
    // Hover highlight
    divider.addEventListener('mouseenter', function(){ divider.style.background='#c8c8c0'; });
    divider.addEventListener('mouseleave', function(){ if(!dragging) divider.style.background=''; });
  }
  initDivider();
})();
(function(){
  var scale=1, tx=0, ty=0, dragging=false, lx=0, ly=0;
  var img=null;

  function applyTransform(){
    if(img) img.style.transform='translate('+tx+'px,'+ty+'px) scale('+scale+')';
  }

  function initPanZoom(){
    img = document.getElementById('wiring-container');
    if(!img) return;
    img.style.transformOrigin = 'top left';
    img.style.transition = 'none';
    img.style.userSelect = 'none';
    img.style.cursor = 'grab';

    // Mouse wheel zoom
    img.parentElement.addEventListener('wheel', function(e){
      e.preventDefault();
      var rect = img.getBoundingClientRect();
      var mx = e.clientX - rect.left - tx;
      var my = e.clientY - rect.top  - ty;
      var delta = e.deltaY < 0 ? 1.15 : 1/1.15;
      var newScale = Math.min(8, Math.max(0.2, scale*delta));
      tx -= mx*(newScale/scale - 1);
      ty -= my*(newScale/scale - 1);
      scale = newScale;
      applyTransform();
    }, {passive:false});

    // Drag to pan
    img.addEventListener('mousedown', function(e){
      dragging=true; lx=e.clientX; ly=e.clientY;
      img.style.cursor='grabbing'; e.preventDefault();
    });
    window.addEventListener('mousemove', function(e){
      if(!dragging) return;
      tx += e.clientX-lx; ty += e.clientY-ly;
      lx=e.clientX; ly=e.clientY;
      applyTransform();
    });
    window.addEventListener('mouseup', function(){
      dragging=false; if(img) img.style.cursor='grab';
    });

    // Button controls
    document.getElementById('wiring-zoom-in') .onclick = function(){ scale=Math.min(8,scale*1.25); applyTransform(); };
    document.getElementById('wiring-zoom-out').onclick = function(){ scale=Math.max(0.2,scale/1.25); applyTransform(); };
    document.getElementById('wiring-zoom-reset').onclick = function(){ scale=1; tx=0; ty=0; applyTransform(); };
  }

  // Wait for element to exist
  function tryInit(){
    if(document.getElementById('wiring-container')) initPanZoom();
    else setTimeout(tryInit, 300);
  }
  tryInit();
})();

// ── Audio polling ──────────────────────────────────────────────────────────
function poll(){
  try{
    var s=window.trame&&window.trame.state&&window.trame.state.state;
    if(s){
      var tok=s.audio_token||0;
      if(tok!==_lastToken&&tok>0&&s.audio_b64){ _lastToken=tok; playWav(s.audio_b64); }
    }
  }catch(e){}
  setTimeout(poll,500);
}

poll();

})();
""")

            with layout.toolbar:
                v.VSpacer()
                v.VSelect(v_model=("layout",),items=(LAYOUT_ITEMS,),label="Layout",density="compact",hide_details=True,style="max-width:200px;")
                v.VSelect(v_model=("wiring",),items=(WIRING_ITEMS,),label="Wiring",density="compact",hide_details=True,style="max-width:160px;margin-left:8px;")

            with layout.content:
                with v.VContainer(fluid=True, classes="pa-0", style="height:calc(100vh - 64px);display:flex;flex-direction:row;overflow:hidden;"):

                    # ── LEFT: wiring diagram (pan/zoom) ─────────────────
                    with html.Div(id="wiring-panel", style="flex-basis:320px;flex-shrink:0;flex-grow:0;overflow:hidden;background:#f8f8f6;position:relative;height:100%;"):
                        # Zoom controls overlay
                        with html.Div(style="position:absolute;top:6px;right:6px;z-index:10;display:flex;flex-direction:column;gap:3px;"):
                            with v.VBtn(icon=True, size="x-small", variant="tonal",
                                   click="document.getElementById('wiring-zoom-in').click()",
                                   title="Zoom in"):
                                v.VIcon("mdi-plus", size="14")
                            with v.VBtn(icon=True, size="x-small", variant="tonal",
                                   click="document.getElementById('wiring-zoom-out').click()",
                                   title="Zoom out"):
                                v.VIcon("mdi-minus", size="14")
                            with v.VBtn(icon=True, size="x-small", variant="tonal",
                                   click="document.getElementById('wiring-zoom-reset').click()",
                                   title="Reset"):
                                v.VIcon("mdi-fit-to-screen-outline", size="14")
                        # Hidden control targets (easier than calling svgPanZoom API from Vue click)
                        html.Div(id="wiring-zoom-in",  style="display:none")
                        html.Div(id="wiring-zoom-out", style="display:none")
                        html.Div(id="wiring-zoom-reset",style="display:none")
                        # The diagram — img tag avoids trame SVG sanitisation
                        html.Img(
                            id="wiring-container",
                            src=("wiring_src",),
                            style="width:100%;height:100%;object-fit:contain;cursor:grab;display:block;",
                        )

                    # ── DIVIDER ──────────────────────────────────────────
                    html.Div(id="panel-divider",
                             style="width:5px;flex-shrink:0;cursor:col-resize;background:#e0e0da;"
                                   "border-left:1px solid #d0d0c8;border-right:1px solid #d0d0c8;"
                                   "transition:background 0.15s;",
                             __events=["mousedown"])

                    # ── RIGHT: controls + scope ──────────────────────────
                    with html.Div(style="flex:1;overflow-y:auto;display:flex;flex-direction:column;"):

                        # Controls strip
                        with v.VContainer(fluid=True, classes="pa-2"):

                            # Selector toggle
                            with v.VRow(dense=True, align="center", classes="mb-1"):
                                with v.VCol(cols="auto"):
                                    html.Div("Position",classes="text-caption text-uppercase text-medium-emphasis")
                                with v.VCol():
                                    with v.VBtnToggle(v_model=("toggle_idx",),mandatory=True,density="compact"):
                                        with v.VBtn(v_for="(opt,ti) in tog_options",key="ti",value=("ti",),size="small"):
                                            html.Span("{{ opt.label }}")

                            # Pickup cards
                            with v.VRow(dense=True, classes="mb-1"):
                                for i in range(MAX_PU):
                                    with v.VCol(cols=12,sm=6,md=4,v_show=f"n_pickups > {i}"):
                                        self._pickup_card(i)

                            # Instrument + taper + master
                            with v.VRow(dense=True, classes="mb-1"):
                                with v.VCol(cols=12,sm=4):
                                    with v.VCard(variant="outlined"):
                                        with v.VCardText(classes="pa-2"):
                                            html.Div("Scale: {{ scale_mm }} mm",classes="text-caption text-medium-emphasis")
                                            v.VSlider(v_model=("scale_mm",),min=580,max=710,step=1,hide_details=True,classes="mb-1")
                                            html.Div("Cable: {{ ccable_pf }} pF",classes="text-caption text-medium-emphasis")
                                            v.VSlider(v_model=("ccable_pf",),min=0,max=2000,step=50,hide_details=True,classes="mb-1")
                                            html.Div("Amp: {{ r_amp_kohm }} kΩ",classes="text-caption text-medium-emphasis")
                                            v.VSlider(v_model=("r_amp_kohm",),min=100,max=2000,step=100,hide_details=True)
                                with v.VCol(cols=12,sm=4):
                                    with v.VCard(variant="outlined"):
                                        with v.VCardText(classes="pa-2"):
                                            v.VSelect(v_model=("vol_taper",),items=(TAPER_ITEMS,),label="Vol taper",density="compact",hide_details=True,classes="mb-2")
                                            v.VSelect(v_model=("tone_taper",),items=(TAPER_ITEMS,),label="Tone taper",density="compact",hide_details=True)
                                with v.VCol(cols=12,sm=4,v_show="shared_vol"):
                                    with v.VCard(variant="outlined"):
                                        with v.VCardText(classes="pa-2"):
                                            html.Div("Master vol: {{ master_vol.toFixed(0) }}%",classes="text-caption text-medium-emphasis")
                                            v.VSlider(v_model=("master_vol",),min=0,max=100,step=1,hide_details=True,color="primary",classes="mb-1")
                                            with html.Div(v_show="shared_vol"):
                                                html.Div("Tone 1: {{ tone1_knob.toFixed(0) }}%",classes="text-caption text-medium-emphasis")
                                                v.VSlider(v_model=("tone1_knob",),min=0,max=100,step=1,hide_details=True,color="secondary",classes="mb-1")
                                                with html.Div(v_show="tone_map.filter(t=>t==='tone2').length > 0"):
                                                    html.Div("Tone 2: {{ tone2_knob.toFixed(0) }}%",classes="text-caption text-medium-emphasis")
                                                    v.VSlider(v_model=("tone2_knob",),min=0,max=100,step=1,hide_details=True,color="secondary")

                            # Pluck row
                            with v.VRow(dense=True, align="center", classes="mb-1"):
                                with v.VCol(cols=12,sm="auto"):
                                    v.VSelect(v_model=("pluck_string",),items=("string_items",),label="String",density="compact",hide_details=True,style="min-width:150px;")
                                with v.VCol(cols=12,sm=3):
                                    html.Div("Pluck pos: {{ pluck_pos }}%",classes="text-caption text-medium-emphasis")
                                    v.VSlider(v_model=("pluck_pos",),min=3,max=45,step=1,hide_details=True)
                                with v.VCol(cols="auto"):
                                    v.VBtn("Pluck",prepend_icon="mdi-music-note",color="primary",variant="outlined",size="small",loading=("busy",),click=self.pluck)
                                    v.VBtn("Set ref",size="small",variant="text",color="warning",click=self.set_audio_ref,
                                           v_show="chart_audio.length>0",classes="ml-1")
                                with v.VCol():
                                    html.Div("{{ status_msg }}",classes="text-caption text-medium-emphasis")
                                    html.Div("Peak: {{ chart_stats.peak }} Hz  |  1 kHz: {{ chart_stats.db1k }} dB  4 kHz: {{ chart_stats.db4k }} dB",
                                             classes="text-caption text-medium-emphasis font-weight-medium")

                        # ── Plotly FR scope (fills remaining height) ─────
                        with html.Div(style="flex:1;min-height:280px;padding:0 8px 8px;"):
                            self._plotly_fig = plotly_widget.Figure(
                                display_mode_bar=True,
                                mode_bar_buttons_to_remove=[
                                    "select2d","lasso2d","autoScale2d",
                                    "hoverClosestCartesian","hoverCompareCartesian",
                                ],
                                style="height:100%;",
                            )


    def _pickup_card(self, i: int):
        p = f"pu{i}_"
        ptype = self._pu_data[i]["type"]   # initial type, for reference only
        with v.VCard(variant="outlined"):
            with v.VCardText(classes="pa-3"):
                html.Div(f"{{{{ pu_labels[{i}] }}}}",classes="text-subtitle-2 font-weight-medium mb-2",style=f"color:{COLORS[i]}")
                v.VSelect(v_model=(f"{p}preset",),items=(f"{p}presets",),
                          label="Model",density="compact",hide_details=True,classes="mb-3")
                v.VDivider(classes="mb-2")
                with html.Div(v_show="!shared_vol"):
                    html.Div(f"Volume: {{{{ {p}vol.toFixed(0) }}}}%",classes="text-caption text-medium-emphasis")
                    v.VSlider(v_model=(f"{p}vol",),min=0,max=100,step=1,hide_details=True,color="primary")
                with html.Div(v_show=f"tone_map[{i}] !== ''"):
                    html.Div(f"Tone: {{{{ {p}tone.toFixed(0) }}}}%",classes="text-caption text-medium-emphasis",v_show="!shared_vol")
                    v.VSlider(v_model=(f"{p}tone",),min=0,max=100,step=1,hide_details=True,color="secondary",v_show="!shared_vol")
                with v.VRow(dense=True,classes="mt-1"):
                    with v.VCol(cols=6):
                        v.VSelect(v_model=(f"{p}rvol",),items=(POT_ITEMS,),label="Vol pot",density="compact",hide_details=True)
                    with v.VCol(cols=6):
                        v.VSelect(v_model=(f"{p}rtone",),items=(POT_ITEMS,),label="Tone pot",density="compact",
                                  hide_details=True,v_show=f"tone_map[{i}] !== ''")
                html.Div(f"Tone cap: {{{{ {p}ctone_nf }}}} nF",classes="text-caption text-medium-emphasis mt-2",
                         v_show=f"tone_map[{i}] !== ''")
                v.VSlider(v_model=(f"{p}ctone_nf",),min=1,max=100,step=1,hide_details=True,
                          v_show=f"tone_map[{i}] !== ''")
                v.VDivider(classes="my-2")
                with v.VRow(dense=True,classes="mb-1"):
                    with v.VCol(cols=6):
                        v.VSelect(v_model=(f"{p}coil_config",),
                                  items=([{"title":"Series","value":"series"},
                                          {"title":"Parallel","value":"parallel"},
                                          {"title":"Split","value":"split"}],),
                                  label="Coil",density="compact",hide_details=True,
                                  v_show=(f"{p}is_hb",))
                    with v.VCol(cols=6):
                        with v.VBtnToggle(v_model=(f"{p}polarity",),
                                          mandatory=True,density="compact",
                                          rounded="lg",border=True,
                                          color="primary"):
                            v.VBtn(value=(1,),  size="small", text="N",
                                   title="Normal polarity")
                            v.VBtn(value=(-1,), size="small", text="R",
                                   title="Reversed / RWRP")
                # Inner/outer coil selector — only meaningful for split
                with html.Div(v_show=f"{p}coil_config==='split' && {p}is_hb",
                               classes="mt-1"):
                    html.Div("Coil tap",classes="text-caption text-medium-emphasis")
                    with v.VBtnToggle(v_model=(f"{p}coil_side",),
                                      mandatory=True,density="compact",
                                      rounded="lg",border=True,
                                      color="primary"):
                        v.VBtn(value=("outer",), size="small", text="Outer",
                               title="Bridge-side coil")
                        v.VBtn(value=("inner",), size="small", text="Inner",
                               title="Neck-side coil")
                v.VDivider(classes="my-2")
                html.Div("Position",classes="text-caption text-uppercase text-medium-emphasis")
                html.Div(f"Dist from bridge: {{{{ {p}dist_mm }}}} mm",classes="text-caption text-medium-emphasis")
                v.VSlider(v_model=(f"{p}dist_mm",),min=5,max=320,step=1,hide_details=True,color="success")
                html.Div(f"Height from strings: {{{{ {p}height_mm }}}} mm",classes="text-caption text-medium-emphasis mt-1")
                v.VSlider(v_model=(f"{p}height_mm",),min=1.0,max=8.0,step=0.5,hide_details=True,color="success")
                v.VDivider(classes="my-2")
                v.VSelect(v_model=(f"{p}tbleed",),items=(TBLEED_ITEMS,),label="Treble bleed",density="compact",hide_details=True)


def main():
    import pathlib
    app = GuitarSim()
    static_dir = str(pathlib.Path(__file__).parent / "static")
    app.server.serve["tools"] = static_dir
    app.server.start(host="0.0.0.0")

if __name__ == "__main__":
    main()
