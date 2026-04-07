"""
app.py — trame Guitar Electronics Simulator

Run:
    cd server
    source .venv/bin/activate
    pip install -r requirements.txt
    python app.py

Then open http://localhost:8080
"""

from trame.app import get_server
from trame.ui.vuetify3 import SinglePageLayout
from trame.widgets import vuetify3 as v, html, client, plotly
from trame.decorators import TrameApp, change

import numpy as np
import base64

from simulation import PickupParams, sweep, FREQS
from audio import render_strum
from pickup_db import PICKUPS, LAYOUTS, POSITION_DEFAULTS

COLORS = ["#378ADD", "#D85A30", "#1D9E75", "#7F77DD"]
POT_ITEMS = [
    {"title": "250 kΩ", "value": 250000},
    {"title": "500 kΩ", "value": 500000},
    {"title": "1 MΩ",   "value": 1000000},
]


def _toggle_options(n: int) -> list:
    presets = {
        1: [{"label": "bridge",   "active": [0]}],
        2: [{"label": "neck",     "active": [0]},
            {"label": "both",     "active": [0, 1]},
            {"label": "bridge",   "active": [1]}],
        3: [{"label": "neck",     "active": [0]},
            {"label": "neck+mid", "active": [0, 1]},
            {"label": "mid",      "active": [1]},
            {"label": "mid+brdg", "active": [1, 2]},
            {"label": "bridge",   "active": [2]}],
    }
    return presets.get(n, presets[2])


def _default_pickup(pos: str, ptype: str) -> dict:
    db     = PICKUPS[ptype]
    defpos = POSITION_DEFAULTS.get(pos, {"dist_mm": 80, "scale_mm": 628})
    return {
        "pos": pos, "type": ptype, "preset_idx": 0,
        "rdc": db[0]["rdc"], "L": db[0]["L"], "Cp": db[0]["Cp"],
        "Rvol": 500000, "Rtone": 500000, "Ctone_nf": 22,
        "vol_knob": 10.0, "tone_knob": 10.0,
        "dist_mm": defpos["dist_mm"], "scale_mm": defpos["scale_mm"],
    }


def _default_pickups(layout_name: str) -> list:
    return [_default_pickup(d["pos"], d["type"]) for d in LAYOUTS[layout_name]]

def _make_plotly_figure(cur_db: list, ref_db: list, freqs: list) -> dict:
    """Return a plotly figure dict for the frequency response chart."""
    return {
        "data": [
            {
                "x": freqs, "y": cur_db,
                "type": "scatter", "mode": "lines",
                "name": "current", "line": {"color": "#378ADD", "width": 2},
            },
            {
                "x": freqs, "y": ref_db,
                "type": "scatter", "mode": "lines",
                "name": "reference (knobs at 10)",
                "line": {"color": "#888", "width": 1.5, "dash": "dash"},
            },
        ],
        "layout": {
            "margin": {"l": 50, "r": 20, "t": 20, "b": 40},
            "height": 300,
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": "rgba(0,0,0,0)",
            "xaxis": {
                "type": "log", "range": [np.log10(80), np.log10(18000)],
                "title": "frequency (Hz)",
                "tickvals": [100, 200, 500, 1000, 2000, 5000, 10000],
                "ticktext": ["100", "200", "500", "1k", "2k", "5k", "10k"],
                "gridcolor": "rgba(128,128,128,0.15)",
            },
            "yaxis": {
                "title": "level (dB, 0 = wide open)",
                "gridcolor": "rgba(128,128,128,0.15)",
            },
            "legend": {"x": 0.01, "y": 0.01, "bgcolor": "rgba(0,0,0,0)"},
        },
    }


@TrameApp()
class GuitarSim:
    def __init__(self, server=None):
        self.server = server or get_server()
        self.state  = self.server.state
        self.ctrl   = self.server.controller

        # ── initial state ─────────────────────────────────────────────────
        self.state.layout      = "HH"
        self.state.wiring      = "50s"
        self.state.tbleed      = "none"
        self.state.ccable_pf   = 500
        self.state.toggle_idx  = 1          # "both" in HH layout
        self.state.pickups     = _default_pickups("HH")
        self.state.tog_options = _toggle_options(2)
        self.state.audio_b64   = ""
        self.state.busy        = False
        self.state.status_msg  = "ready"

        # Preset name lists per pickup type for dropdowns
        self.state.hb_presets  = [p["name"] for p in PICKUPS["humbucker"]]
        self.state.sc_presets  = [p["name"] for p in PICKUPS["single"]]
        self.state.p90_presets = [p["name"] for p in PICKUPS["p90"]]

        freqs_list = [round(f, 1) for f in FREQS.tolist()]
        zeros = [0.0] * len(FREQS)
        self.state.figure = _make_plotly_figure(zeros, zeros, freqs_list)
        self.state.chart_stats = {"peak": 0, "200": 0.0, "500": 0.0, "1k": 0.0, "4k": 0.0}

        self._freqs_list = freqs_list
        self._compute_and_push()
        self._build_ui()

    # ── helpers ───────────────────────────────────────────────────────────
    def _active(self) -> list[int]:
        opts = self.state.tog_options
        idx  = self.state.toggle_idx
        return opts[idx]["active"] if 0 <= idx < len(opts) else [0]

    def _make_params(self, overrides: dict | None = None) -> list[PickupParams]:
        pus = []
        for p in self.state.pickups:
            src = {**p, **(overrides or {})}
            pus.append(PickupParams(
                rdc=src["rdc"],
                L=src["L"],
                Cp=src["Cp"],
                Rvol=src["Rvol"],
                Rtone=src["Rtone"],
                Ctone=src["Ctone_nf"] * 1e-9,   # nF → F
                vol_knob=src["vol_knob"],
                tone_knob=src["tone_knob"],
                dist_mm=src["dist_mm"],
                scale_mm=src["scale_mm"],
            ))
        return pus

    def _compute_and_push(self):
        cable  = self.state.ccable_pf * 1e-12
        tbleed = self.state.tbleed
        wiring = self.state.wiring
        active = self._active()

        cur = sweep(self._make_params(), active, cable, tbleed, wiring)

        ref_params = []
        for p in self.state.pickups:
            ref_params.append(PickupParams(
                rdc=p["rdc"], L=p["L"], Cp=p["Cp"],
                Rvol=p["Rvol"], Rtone=p["Rtone"],
                Ctone=p["Ctone_nf"] * 1e-9,
                vol_knob=10.0, tone_knob=10.0,
                dist_mm=p["dist_mm"], scale_mm=p["scale_mm"],
            ))
        ref = sweep(ref_params, active, cable, tbleed, wiring)

        anchor = float(np.max(ref)) or 1.0
        cur_db = (20 * np.log10(np.clip(cur / anchor, 1e-12, None))).tolist()
        ref_db = (20 * np.log10(np.clip(ref / anchor, 1e-12, None))).tolist()

        # Update plotly figure
        self.state.figure = _make_plotly_figure(cur_db, ref_db, self._freqs_list)

        # Stats
        def _at(f):
            i = int(np.argmin(np.abs(FREQS - f)))
            return round(cur_db[i], 1)

        pk = int(np.argmax(cur_db))
        self.state.chart_stats = {
            "peak": round(float(FREQS[pk])),
            "200":  _at(200),
            "500":  _at(500),
            "1k":   _at(1000),
            "4k":   _at(4000),
        }

    # ── reactive handlers ─────────────────────────────────────────────────
    @change("layout")
    def on_layout(self, layout, **_):
        defs = LAYOUTS[layout]
        self.state.pickups     = _default_pickups(layout)
        self.state.tog_options = _toggle_options(len(defs))
        n = len(defs)
        self.state.toggle_idx  = next(
            (i for i, t in enumerate(self.state.tog_options)
             if len(t["active"]) == n), 0
        )
        self._compute_and_push()

    @change("wiring", "tbleed", "ccable_pf", "toggle_idx")
    def on_shared_param(self, **_):
        self._compute_and_push()

    # Individual pickup param changes — each bound explicitly in the UI
    def set_pickup_param(self, idx: int, key: str, val):
        pus = list(self.state.pickups)
        pus[idx] = {**pus[idx], key: val}
        self.state.pickups = pus
        self._compute_and_push()

    def set_pickup_preset(self, idx: int, preset_idx: int):
        pu  = self.state.pickups[idx]
        db  = PICKUPS[pu["type"]]
        if preset_idx < len(db):
            p   = db[preset_idx]
            pus = list(self.state.pickups)
            pus[idx] = {**pu, "preset_idx": preset_idx,
                        "rdc": p["rdc"], "L": p["L"], "Cp": p["Cp"]}
            self.state.pickups = pus
            self._compute_and_push()

    def strum(self):
        self.state.busy = True
        self.state.status_msg = "rendering audio..."
        try:
            cable  = self.state.ccable_pf * 1e-12
            active = self._active()
            resp   = sweep(self._make_params(), active, cable,
                           self.state.tbleed, self.state.wiring)
            wav    = render_strum(resp)
            self.state.audio_b64  = base64.b64encode(wav).decode()
            self.state.status_msg = "playing — E A D G B e"
        except Exception as e:
            self.state.status_msg = f"audio error: {e}"
        finally:
            self.state.busy = False

    # ── UI ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        with SinglePageLayout(self.server) as layout:
            layout.title.set_text("Guitar Electronics Simulator")

            # Audio playback: watch audio_b64 state, decode and play WAV
            client.Style("body { background: #f5f5f3; }")
            client.Script("""
(function() {
  let _audioCtx = null;
  function getCtx() {
    if (!_audioCtx) _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (_audioCtx.state === 'suspended') _audioCtx.resume();
    return _audioCtx;
  }
  window.__playWav = function(b64) {
    if (!b64) return;
    const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    getCtx().decodeAudioData(bytes.buffer, (buf) => {
      const src = getCtx().createBufferSource();
      const gain = getCtx().createGain();
      src.buffer = buf;
      gain.gain.value = 0.85;
      src.connect(gain); gain.connect(getCtx().destination);
      src.start();
    });
  };
})();
            """)

            with layout.toolbar:
                v.VSpacer()
                v.VSelect(
                    v_model=("layout",),
                    items=([
                        {"title": "HH — Les Paul",   "value": "HH"},
                        {"title": "HSS — Strat",     "value": "HSS"},
                        {"title": "HHS",             "value": "HHS"},
                        {"title": "SSS — 3× single", "value": "SSS"},
                        {"title": "H — solo HB",     "value": "H"},
                        {"title": "SS — Telecaster", "value": "SS"},
                    ],),
                    label="Layout", density="compact",
                    hide_details=True, style="max-width:200px;",
                )
                v.VSelect(
                    v_model=("wiring",),
                    items=([{"title": "50s wiring",    "value": "50s"},
                            {"title": "Modern wiring", "value": "modern"}],),
                    label="Wiring", density="compact",
                    hide_details=True, style="max-width:160px;margin-left:8px;",
                )

            with layout.content:
                with v.VContainer(fluid=True, classes="pa-3"):
                    self._section("Pickup selector")
                    with v.VRow(classes="mb-1"):
                        with v.VCol():
                            with v.VBtnToggle(
                                v_model=("toggle_idx",),
                                mandatory=True, density="compact",
                            ):
                                with v.VBtn(
                                    v_for="(opt, ti) in tog_options",
                                    key="ti", value=("ti",), size="small",
                                ):
                                    html.Span("{{ opt.label }}")

                    self._section("Pickups")
                    with v.VRow(classes="mb-2"):
                        with v.VCol(
                            v_for="(pu, pi) in pickups",
                            key="pi", cols=12, sm=6, md=4,
                        ):
                            self._pickup_card()

                    self._section("Shared")
                    with v.VRow(classes="mb-2"):
                        with v.VCol(cols=12, sm=6, md=4):
                            with v.VCard(variant="outlined", classes="pa-1"):
                                with v.VCardText():
                                    v.VSelect(
                                        v_model=("tbleed",),
                                        items=([
                                            {"title": "No treble bleed",             "value": "none"},
                                            {"title": "Cap only (100 pF)",           "value": "cap"},
                                            {"title": "Cap + resistor (100pF/150k)", "value": "network"},
                                        ],),
                                        label="Treble bleed",
                                        density="compact", hide_details=True, classes="mb-3",
                                    )
                                    html.Div("Cable capacitance", classes="text-caption text-medium-emphasis")
                                    with html.Div(style="display:flex;align-items:center;gap:8px;"):
                                        v.VSlider(
                                            v_model=("ccable_pf",),
                                            min=0, max=2000, step=50,
                                            hide_details=True, style="flex:1;",
                                        )
                                        html.Span(
                                            "{{ ccable_pf }} pF",
                                            classes="text-caption",
                                            style="min-width:60px;",
                                        )

                    # Strum + stats row
                    with v.VRow(classes="mb-2", align="center"):
                        with v.VCol(cols="auto"):
                            v.VBtn(
                                "Strum  E A D G B e",
                                prepend_icon="mdi-music-note-eighth",
                                color="primary", variant="outlined",
                                loading=("busy",),
                                click=(self.strum, "[]"),
                            )
                            # Trigger JS playback when audio_b64 changes
                            client.ServerStateChange(
                                trigger_on=("audio_b64",),
                                update="__playWav(audio_b64)",
                            )
                        with v.VCol():
                            html.Div(
                                "{{ status_msg }}",
                                classes="text-caption text-medium-emphasis",
                            )
                        with v.VCol(cols=12):
                            html.Div(
                                "Peak: {{ chart_stats.peak }} Hz  |  "
                                "200 Hz: {{ chart_stats['200'] }} dB  "
                                "500 Hz: {{ chart_stats['500'] }} dB  "
                                "1 kHz: {{ chart_stats['1k'] }} dB  "
                                "4 kHz: {{ chart_stats['4k'] }} dB",
                                classes="text-caption text-medium-emphasis font-weight-medium",
                            )

                    # Frequency response chart
                    with v.VCard(variant="outlined"):
                        with v.VCardText(classes="pa-1"):
                            plotly.Figure(
                                display_mode_bar=False,
                                v_model=("figure",),
                            )

    @staticmethod
    def _section(label: str):
        html.Div(
            label,
            classes="text-caption text-uppercase text-medium-emphasis mb-1 mt-3",
            style="letter-spacing:.06em;font-weight:500;",
        )

    def _pickup_card(self):
        """Template card rendered per pickup via v-for on parent VCol."""
        with v.VCard(variant="outlined"):
            with v.VCardText(classes="pa-3"):
                # Header
                html.Div(
                    "{{ pu.pos.charAt(0).toUpperCase() + pu.pos.slice(1) }}"
                    " — {{ pu.type === 'humbucker' ? 'Humbucker' : pu.type === 'p90' ? 'P-90' : 'Single coil' }}",
                    classes="text-subtitle-2 font-weight-medium mb-2",
                )
                # Preset selector — items depend on pickup type
                v.VSelect(
                    v_model=("pickups[pi].preset_idx",),
                    items=(
                        "pu.type === 'humbucker' ? hb_presets : "
                        "pu.type === 'p90' ? p90_presets : sc_presets",
                    ),
                    label="Model", density="compact",
                    hide_details=True, classes="mb-3",
                )
                v.VDivider(classes="mb-2")
                # Volume knob
                html.Div(
                    "Volume: {{ pu.vol_knob.toFixed(1) }}",
                    classes="text-caption text-medium-emphasis",
                )
                v.VSlider(
                    v_model=("pickups[pi].vol_knob",),
                    min=0, max=10, step=0.1,
                    hide_details=True, color="primary",
                )
                # Tone knob
                html.Div(
                    "Tone: {{ pu.tone_knob.toFixed(1) }}",
                    classes="text-caption text-medium-emphasis",
                )
                v.VSlider(
                    v_model=("pickups[pi].tone_knob",),
                    min=0, max=10, step=0.1,
                    hide_details=True, color="secondary",
                )

                # Pot selectors
                with v.VRow(dense=True, classes="mt-1"):
                    with v.VCol(cols=6):
                        v.VSelect(
                            v_model=("pickups[pi].Rvol",),
                            items=(POT_ITEMS,),
                            label="Vol pot", density="compact", hide_details=True,
                        )
                    with v.VCol(cols=6):
                        v.VSelect(
                            v_model=("pickups[pi].Rtone",),
                            items=(POT_ITEMS,),
                            label="Tone pot", density="compact", hide_details=True,
                        )
                # Tone cap
                html.Div(
                    "Tone cap: {{ pickups[pi].Ctone_nf }} nF",
                    classes="text-caption text-medium-emphasis mt-2",
                )
                v.VSlider(
                    v_model=("pickups[pi].Ctone_nf",),
                    min=1, max=100, step=1,
                    hide_details=True,
                )
                v.VDivider(classes="my-2")
                # Position
                html.Div("Position", classes="text-caption text-uppercase text-medium-emphasis")
                html.Div(
                    "Distance from bridge: {{ pickups[pi].dist_mm }} mm",
                    classes="text-caption text-medium-emphasis",
                )
                v.VSlider(
                    v_model=("pickups[pi].dist_mm",),
                    min=5, max=320, step=1,
                    hide_details=True, color="success",
                )
                html.Div(
                    "Scale length: {{ pickups[pi].scale_mm }} mm",
                    classes="text-caption text-medium-emphasis",
                )
                v.VSlider(
                    v_model=("pickups[pi].scale_mm",),
                    min=580, max=710, step=1,
                    hide_details=True,
                )


def main():
    app = GuitarSim()
    # Watch pickups array changes — trame doesn't auto-detect nested mutations
    # so we trigger recompute whenever any pickup state key changes
    @app.state.change("pickups")
    def _on_pickups(**_):
        app._compute_and_push()

    app.server.start()


if __name__ == "__main__":
    main()
