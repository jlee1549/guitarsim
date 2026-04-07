"""
app.py — trame Guitar Electronics Simulator

State design: flat indexed keys for all slider-controlled pickup params.
e.g. pu0_vol, pu1_vol, pu0_tone, pu1_tone, etc.
Trame watches top-level keys reliably; nested dict mutations are not reactive.

Run:
    cd server && source .venv/bin/activate && python app.py --server
    open http://localhost:8080
"""

from trame.app import get_server
from trame.ui.vuetify3 import SinglePageLayout
from trame.widgets import vuetify3 as v, html, client, plotly
from trame.decorators import TrameApp, change

import numpy as np
import base64

from simulation import PickupParams, sweep, FREQS
from audio import render_pluck, OPEN_STRINGS, STRING_NAMES, DEFAULT_PLUCK_POS
from pickup_db import PICKUPS, LAYOUTS, POSITION_DEFAULTS

MAX_PICKUPS = 3   # max supported in any layout
COLORS = ["#378ADD", "#D85A30", "#1D9E75"]

POT_ITEMS = [
    {"title": "250 kΩ", "value": 250000},
    {"title": "500 kΩ", "value": 500000},
    {"title": "1 MΩ",   "value": 1000000},
]

TBLEED_ITEMS = [
    {"title": "No treble bleed",             "value": "none"},
    {"title": "Cap only (100 pF)",           "value": "cap"},
    {"title": "Cap + resistor (100pF/150k)", "value": "network"},
]

LAYOUT_ITEMS = [
    {"title": "HH — Les Paul",   "value": "HH"},
    {"title": "HSS — Strat",     "value": "HSS"},
    {"title": "HHS",             "value": "HHS"},
    {"title": "SSS — 3× single", "value": "SSS"},
    {"title": "H — solo HB",     "value": "H"},
    {"title": "SS — Telecaster", "value": "SS"},
]

WIRING_ITEMS = [
    {"title": "50s wiring",    "value": "50s"},
    {"title": "Modern wiring", "value": "modern"},
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
        "pos": pos, "type": ptype,
        "rdc": db[0]["rdc"], "L": db[0]["L"], "Cp": db[0]["Cp"],
        "Rvol": 500000, "Rtone": 500000, "Ctone_nf": 22,
        "vol_knob": 10.0, "tone_knob": 10.0,
        "dist_mm": defpos["dist_mm"], "scale_mm": defpos["scale_mm"],
    }


def _make_plotly_figure(cur_db: list, ref_db: list, freqs: list) -> dict:
    return {
        "data": [
            {"x": freqs, "y": cur_db, "type": "scatter", "mode": "lines",
             "name": "current", "line": {"color": "#378ADD", "width": 2}},
            {"x": freqs, "y": ref_db, "type": "scatter", "mode": "lines",
             "name": "ref (knobs at 10)",
             "line": {"color": "#888", "width": 1.5, "dash": "dash"}},
        ],
        "layout": {
            "margin": {"l": 55, "r": 20, "t": 10, "b": 45},
            "height": 280,
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor":  "rgba(0,0,0,0)",
            "xaxis": {
                "type": "log", "range": [np.log10(80), np.log10(18000)],
                "title": "frequency (Hz)",
                "tickvals": [100, 200, 500, 1000, 2000, 5000, 10000],
                "ticktext": ["100", "200", "500", "1k", "2k", "5k", "10k"],
                "gridcolor": "rgba(128,128,128,0.15)",
            },
            "yaxis": {
                "title": "level (dB)",
                "gridcolor": "rgba(128,128,128,0.15)",
            },
            "legend": {"x": 0.01, "y": 0.01, "bgcolor": "rgba(0,0,0,0)",
                       "font": {"size": 11}},
        },
    }


@TrameApp()
class GuitarSim:
    def __init__(self, server=None):
        self.server = server or get_server()
        self.state  = self.server.state
        self.ctrl   = self.server.controller

        # Shared controls
        self.state.layout     = "HH"
        self.state.wiring     = "50s"
        self.state.tbleed     = "none"
        self.state.ccable_pf  = 500
        self.state.toggle_idx = 1
        self.state.tog_options = _toggle_options(2)
        self.state.n_pickups  = 2
        self.state.busy       = False
        self.state.status_msg = "ready"
        self.state.audio_b64  = ""

        # Pluck controls
        self.state.pluck_string = 1   # 0=E2 .. 5=E4, default A2
        self.state.pluck_pos    = int(DEFAULT_PLUCK_POS * 100)  # 0–50 (% of scale)
        self.state.string_items = [{"title": f"{STRING_NAMES[i]} ({OPEN_STRINGS[i]:.1f} Hz)", "value": i}
                                    for i in range(6)]

        # Pickup metadata (read-only display)
        self.state.pu_labels  = ["neck (HB)", "bridge (HB)", ""]

        # Preset lists
        self.state.hb_presets  = [p["name"] for p in PICKUPS["humbucker"]]
        self.state.sc_presets  = [p["name"] for p in PICKUPS["single"]]
        self.state.p90_presets = [p["name"] for p in PICKUPS["p90"]]

        # Flat pickup state — one key per param per pickup index
        # Initialise all 3 slots even if only 1-2 are active
        self._pu_data = [_default_pickup("neck", "humbucker"),
                         _default_pickup("bridge", "humbucker"),
                         _default_pickup("bridge", "humbucker")]
        self._push_pu_state()

        # Chart
        freqs_list = [round(f, 1) for f in FREQS.tolist()]
        self._freqs_list = freqs_list
        zeros = [0.0] * len(FREQS)
        self.state.figure      = _make_plotly_figure(zeros, zeros, freqs_list)
        self.state.chart_stats = {"peak": 0, "db200": 0.0, "db500": 0.0,
                                  "db1k": 0.0, "db4k": 0.0}
        self._compute_and_push()
        self._build_ui()

    # ── flat state helpers ────────────────────────────────────────────────
    def _push_pu_state(self):
        """Write _pu_data into flat top-level state keys."""
        for i, p in enumerate(self._pu_data):
            setattr(self.state, f"pu{i}_vol",      p["vol_knob"])
            setattr(self.state, f"pu{i}_tone",     p["tone_knob"])
            setattr(self.state, f"pu{i}_rvol",     p["Rvol"])
            setattr(self.state, f"pu{i}_rtone",    p["Rtone"])
            setattr(self.state, f"pu{i}_ctone_nf", p["Ctone_nf"])
            setattr(self.state, f"pu{i}_dist_mm",  p["dist_mm"])
            setattr(self.state, f"pu{i}_scale_mm", p["scale_mm"])

    def _pull_pu_state(self):
        """Read flat state keys back into _pu_data."""
        for i in range(MAX_PICKUPS):
            self._pu_data[i]["vol_knob"]  = getattr(self.state, f"pu{i}_vol",      10.0)
            self._pu_data[i]["tone_knob"] = getattr(self.state, f"pu{i}_tone",     10.0)
            self._pu_data[i]["Rvol"]      = getattr(self.state, f"pu{i}_rvol",     500000)
            self._pu_data[i]["Rtone"]     = getattr(self.state, f"pu{i}_rtone",    500000)
            self._pu_data[i]["Ctone_nf"]  = getattr(self.state, f"pu{i}_ctone_nf", 22)
            self._pu_data[i]["dist_mm"]   = getattr(self.state, f"pu{i}_dist_mm",  80)
            self._pu_data[i]["scale_mm"]  = getattr(self.state, f"pu{i}_scale_mm", 628)

    def _active(self) -> list[int]:
        opts = self.state.tog_options
        idx  = self.state.toggle_idx
        return opts[idx]["active"] if 0 <= idx < len(opts) else [0]

    def _make_params(self) -> list[PickupParams]:
        self._pull_pu_state()
        return [PickupParams(
            rdc=p["rdc"], L=p["L"], Cp=p["Cp"],
            Rvol=p["Rvol"], Rtone=p["Rtone"],
            Ctone=p["Ctone_nf"] * 1e-9,
            vol_knob=p["vol_knob"], tone_knob=p["tone_knob"],
            dist_mm=p["dist_mm"], scale_mm=p["scale_mm"],
        ) for p in self._pu_data]

    def _compute_and_push(self):
        self._pull_pu_state()
        cable  = self.state.ccable_pf * 1e-12
        tbleed = self.state.tbleed
        wiring = self.state.wiring
        active = self._active()
        pus    = self._make_params()

        cur = sweep(pus, active, cable, tbleed, wiring)

        ref_pus = [PickupParams(
            rdc=p["rdc"], L=p["L"], Cp=p["Cp"],
            Rvol=p["Rvol"], Rtone=p["Rtone"],
            Ctone=p["Ctone_nf"] * 1e-9,
            vol_knob=10.0, tone_knob=10.0,
            dist_mm=p["dist_mm"], scale_mm=p["scale_mm"],
        ) for p in self._pu_data]
        ref = sweep(ref_pus, active, cable, tbleed, wiring)

        anchor = float(np.max(ref)) or 1.0
        cur_db = (20 * np.log10(np.clip(cur / anchor, 1e-12, None))).tolist()
        ref_db = (20 * np.log10(np.clip(ref / anchor, 1e-12, None))).tolist()

        self.state.figure = _make_plotly_figure(cur_db, ref_db, self._freqs_list)

        def _at(f):
            i = int(np.argmin(np.abs(FREQS - f)))
            return round(cur_db[i], 1)

        pk = int(np.argmax(cur_db))
        self.state.chart_stats = {
            "peak":  round(float(FREQS[pk])),
            "db200": _at(200), "db500": _at(500),
            "db1k":  _at(1000), "db4k": _at(4000),
        }

    # ── reactive handlers ─────────────────────────────────────────────────
    @change("layout")
    def on_layout(self, layout, **_):
        defs = LAYOUTS[layout]
        n    = len(defs)
        for i, d in enumerate(defs):
            p = _default_pickup(d["pos"], d["type"])
            self._pu_data[i] = p
        self._push_pu_state()
        self.state.n_pickups   = n
        self.state.pu_labels   = [f"{d['pos']} ({'HB' if d['type']=='humbucker' else 'P90' if d['type']=='p90' else 'SC'})"
                                   for d in defs] + [""] * (MAX_PICKUPS - n)
        self.state.tog_options = _toggle_options(n)
        self.state.toggle_idx  = next(
            (i for i, t in enumerate(self.state.tog_options) if len(t["active"]) == n), 0)
        self._compute_and_push()

    @change("wiring", "tbleed", "ccable_pf", "toggle_idx")
    def on_shared(self, **_):
        self._compute_and_push()

    # Flat per-pickup param watchers — one @change per key
    def _make_pu_watcher(self, i):
        keys = [f"pu{i}_vol", f"pu{i}_tone", f"pu{i}_rvol",
                f"pu{i}_rtone", f"pu{i}_ctone_nf", f"pu{i}_dist_mm", f"pu{i}_scale_mm"]
        @self.state.change(*keys)
        def _watch(**_):
            self._compute_and_push()

    def strum(self):
        self.state.busy = True
        self.state.status_msg = "rendering..."
        try:
            self._pull_pu_state()
            cable  = self.state.ccable_pf * 1e-12
            active = self._active()
            pus    = self._make_params()
            resp   = sweep(pus, active, cable, self.state.tbleed, self.state.wiring)

            # Compute reference gain (knobs at 10) to preserve relative volume
            ref_pus = [PickupParams(
                rdc=p["rdc"], L=p["L"], Cp=p["Cp"],
                Rvol=p["Rvol"], Rtone=p["Rtone"],
                Ctone=p["Ctone_nf"] * 1e-9,
                vol_knob=10.0, tone_knob=10.0,
                dist_mm=p["dist_mm"], scale_mm=p["scale_mm"],
            ) for p in self._pu_data]
            ref_resp = sweep(ref_pus, active, cable,
                             self.state.tbleed, self.state.wiring)

            ref_peak  = float(np.max(ref_resp))  or 1.0
            cur_peak  = float(np.max(resp))
            ref_gain  = cur_peak / ref_peak   # 1.0 when at full volume, <1 when rolled off

            wav = render_pluck(
                freq_response  = resp,
                string_idx     = int(self.state.pluck_string),
                pluck_pos      = self.state.pluck_pos / 100.0,
                reference_gain = ref_gain,
            )
            self.state.audio_b64  = base64.b64encode(wav).decode()
            name = STRING_NAMES[int(self.state.pluck_string)]
            self.state.status_msg = f"plucked {name}"
        except Exception as e:
            self.state.status_msg = f"error: {e}"
            import traceback; traceback.print_exc()
        finally:
            self.state.busy = False

    # ── UI ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Register per-pickup watchers for all 3 slots
        for i in range(MAX_PICKUPS):
            self._make_pu_watcher(i)

        with SinglePageLayout(self.server) as layout:
            layout.title.set_text("Guitar Electronics Simulator")

            # Audio: poll trame state every 400ms, play WAV when audio_b64 changes
            client.Style("body { background: #f5f5f3; }")
            client.Script("""
(function() {
  var _ctx = null, _lastB64 = '';
  function ctx() {
    if (!_ctx) _ctx = new (window.AudioContext||window.webkitAudioContext)();
    if (_ctx.state === 'suspended') _ctx.resume();
    return _ctx;
  }
  function playWav(b64) {
    try {
      var bytes = Uint8Array.from(atob(b64), function(c){return c.charCodeAt(0);});
      ctx().decodeAudioData(bytes.buffer, function(buf) {
        var src = ctx().createBufferSource();
        var g   = ctx().createGain(); g.gain.value = 0.8;
        src.buffer = buf;
        src.connect(g); g.connect(ctx().destination);
        src.start();
      });
    } catch(e) { console.warn('audio error', e); }
  }
  function poll() {
    try {
      var b64 = window.trame && window.trame.state && window.trame.state.state.audio_b64;
      if (b64 && b64 !== _lastB64) { _lastB64 = b64; playWav(b64); }
    } catch(e) {}
    setTimeout(poll, 400);
  }
  poll();
})();
""")

            with layout.toolbar:
                v.VSpacer()
                v.VSelect(v_model=("layout",), items=(LAYOUT_ITEMS,),
                          label="Layout", density="compact",
                          hide_details=True, style="max-width:200px;")
                v.VSelect(v_model=("wiring",), items=(WIRING_ITEMS,),
                          label="Wiring", density="compact",
                          hide_details=True, style="max-width:160px;margin-left:8px;")

            with layout.content:
                with v.VContainer(fluid=True, classes="pa-3"):

                    # Toggle row
                    html.Div("Pickup selector", classes="text-caption text-uppercase text-medium-emphasis mb-1 mt-1")
                    with v.VBtnToggle(v_model=("toggle_idx",), mandatory=True, density="compact", classes="mb-3"):
                        with v.VBtn(v_for="(opt,ti) in tog_options", key="ti",
                                    value=("ti",), size="small"):
                            html.Span("{{ opt.label }}")

                    # Pickup cards — rendered explicitly, not via v-for
                    html.Div("Pickups", classes="text-caption text-uppercase text-medium-emphasis mb-1")
                    with v.VRow(classes="mb-2"):
                        for i in range(MAX_PICKUPS):
                            with v.VCol(cols=12, sm=6, md=4,
                                        v_show=f"n_pickups > {i}"):
                                self._pickup_card(i)

                    # Shared controls
                    html.Div("Shared", classes="text-caption text-uppercase text-medium-emphasis mb-1")
                    with v.VRow(classes="mb-2"):
                        with v.VCol(cols=12, sm=6, md=4):
                            with v.VCard(variant="outlined"):
                                with v.VCardText():
                                    v.VSelect(v_model=("tbleed",), items=(TBLEED_ITEMS,),
                                              label="Treble bleed", density="compact",
                                              hide_details=True, classes="mb-3")
                                    html.Div("Cable cap: {{ ccable_pf }} pF",
                                             classes="text-caption text-medium-emphasis")
                                    v.VSlider(v_model=("ccable_pf",), min=0, max=2000, step=50,
                                              hide_details=True)

                    # Pluck controls + button
                    with v.VRow(align="center", classes="mb-1"):
                        with v.VCol(cols=12, sm="auto"):
                            v.VSelect(
                                v_model=("pluck_string",),
                                items=("string_items",),
                                label="String", density="compact",
                                hide_details=True, style="min-width:160px;",
                            )
                        with v.VCol(cols=12, sm=4):
                            html.Div("Pluck pos: {{ pluck_pos }}%",
                                     classes="text-caption text-medium-emphasis")
                            v.VSlider(v_model=("pluck_pos",), min=3, max=45, step=1,
                                      hide_details=True)
                        with v.VCol(cols="auto"):
                            v.VBtn("Pluck",
                                   prepend_icon="mdi-music-note",
                                   color="primary", variant="outlined",
                                   loading=("busy",), click=self.strum)
                        with v.VCol():
                            html.Div("{{ status_msg }}", classes="text-caption text-medium-emphasis")
                    html.Div(
                        "Peak: {{ chart_stats.peak }} Hz  |  "
                        "200 Hz: {{ chart_stats.db200 }} dB  "
                        "500 Hz: {{ chart_stats.db500 }} dB  "
                        "1 kHz: {{ chart_stats.db1k }} dB  "
                        "4 kHz: {{ chart_stats.db4k }} dB",
                        classes="text-caption text-medium-emphasis font-weight-medium mb-2",
                    )

                    # Chart
                    with v.VCard(variant="outlined"):
                        with v.VCardText(classes="pa-1"):
                            plotly.Figure(display_mode_bar=False,
                                          state_variable_name="figure")

    def _pickup_card(self, i: int):
        """Render one pickup card with flat state keys pu{i}_*."""
        p = f"pu{i}_"   # key prefix
        with v.VCard(variant="outlined"):
            with v.VCardText(classes="pa-3"):
                html.Div(f"{{{{ pu_labels[{i}] }}}}",
                         classes="text-subtitle-2 font-weight-medium mb-2",
                         style=f"color:{COLORS[i]}")
                html.Div(f"Volume: {{{{ {p}vol.toFixed(1) }}}}",
                         classes="text-caption text-medium-emphasis")
                v.VSlider(v_model=(f"{p}vol",), min=0, max=10, step=0.1,
                          hide_details=True, color="primary")
                html.Div(f"Tone: {{{{ {p}tone.toFixed(1) }}}}",
                         classes="text-caption text-medium-emphasis")
                v.VSlider(v_model=(f"{p}tone",), min=0, max=10, step=0.1,
                          hide_details=True, color="secondary")
                with v.VRow(dense=True, classes="mt-1"):
                    with v.VCol(cols=6):
                        v.VSelect(v_model=(f"{p}rvol",), items=(POT_ITEMS,),
                                  label="Vol pot", density="compact", hide_details=True)
                    with v.VCol(cols=6):
                        v.VSelect(v_model=(f"{p}rtone",), items=(POT_ITEMS,),
                                  label="Tone pot", density="compact", hide_details=True)
                html.Div(f"Tone cap: {{{{ {p}ctone_nf }}}} nF",
                         classes="text-caption text-medium-emphasis mt-2")
                v.VSlider(v_model=(f"{p}ctone_nf",), min=1, max=100, step=1,
                          hide_details=True)
                v.VDivider(classes="my-2")
                html.Div("Position", classes="text-caption text-uppercase text-medium-emphasis")
                html.Div(f"Dist from bridge: {{{{ {p}dist_mm }}}} mm",
                         classes="text-caption text-medium-emphasis")
                v.VSlider(v_model=(f"{p}dist_mm",), min=5, max=320, step=1,
                          hide_details=True, color="success")
                html.Div(f"Scale length: {{{{ {p}scale_mm }}}} mm",
                         classes="text-caption text-medium-emphasis")
                v.VSlider(v_model=(f"{p}scale_mm",), min=580, max=710, step=1,
                          hide_details=True)


def main():
    app = GuitarSim()
    app.server.start()


if __name__ == "__main__":
    main()
