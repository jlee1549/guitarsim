"""
app.py — trame Guitar Electronics Simulator

Run:
    cd server && python app.py
Open: http://localhost:8080
"""

from trame.app import get_server
from trame.ui.vuetify3 import SinglePageLayout
from trame.widgets import vuetify3 as v, html, client
from trame.decorators import TrameApp, change

import numpy as np
import base64

from simulation import PickupParams, sweep, FREQS
from audio import render_strum
from pickup_db import PICKUPS, LAYOUTS, POSITION_DEFAULTS

COLORS = ["#378ADD", "#D85A30", "#1D9E75", "#7F77DD"]


def _toggle_options(n: int) -> list:
    presets = {
        1: [{"label": "bridge",    "active": [0]}],
        2: [{"label": "neck",      "active": [0]},
            {"label": "both",      "active": [0, 1]},
            {"label": "bridge",    "active": [1]}],
        3: [{"label": "neck",      "active": [0]},
            {"label": "neck+mid",  "active": [0, 1]},
            {"label": "mid",       "active": [1]},
            {"label": "mid+brdg",  "active": [1, 2]},
            {"label": "bridge",    "active": [2]}],
    }
    return presets.get(n, presets[2])


def _default_pickups(layout_name: str) -> list:
    defs = LAYOUTS[layout_name]
    result = []
    for i, d in enumerate(defs):
        db      = PICKUPS[d["type"]]
        pos     = d["pos"]
        defpos  = POSITION_DEFAULTS.get(pos, {"dist_mm": 80, "scale_mm": 628})
        result.append({
            "pos": pos, "type": d["type"], "preset_idx": 0,
            "rdc": db[0]["rdc"], "L": db[0]["L"], "Cp": db[0]["Cp"],
            "Rvol": 500e3, "Rtone": 500e3, "Ctone": 22e-9,
            "vol_knob": 10.0, "tone_knob": 10.0,
            "dist_mm": defpos["dist_mm"], "scale_mm": defpos["scale_mm"],
        })
    return result

@TrameApp()
class GuitarSim:
    def __init__(self, server=None):
        self.server = server or get_server()
        self.state  = self.server.state
        self.ctrl   = self.server.controller

        self.state.layout      = "HH"
        self.state.wiring      = "50s"
        self.state.tbleed      = "none"
        self.state.ccable_pf   = 500
        self.state.toggle_idx  = 1
        self.state.pickups     = _default_pickups("HH")
        self.state.tog_options = _toggle_options(2)
        self.state.audio_b64   = ""
        self.state.audio_error = ""
        self.state.busy        = False

        # Chart data
        self.state.chart_freqs  = [round(f, 1) for f in FREQS.tolist()]
        self.state.chart_cur    = [0.0] * len(FREQS)
        self.state.chart_ref    = [0.0] * len(FREQS)
        self.state.chart_peak   = 0
        self.state.chart_stats  = {}

        self._compute_and_push()
        self._build_ui()

    # ── helpers ──────────────────────────────────────────────────────────
    def _active(self) -> list[int]:
        opts = self.state.tog_options
        idx  = self.state.toggle_idx
        return opts[idx]["active"] if idx < len(opts) else [0]

    def _make_params(self, override=None) -> list[PickupParams]:
        pus = []
        for p in self.state.pickups:
            src = override(p) if override else p
            pus.append(PickupParams(
                rdc=src["rdc"], L=src["L"], Cp=src["Cp"],
                Rvol=src["Rvol"], Rtone=src["Rtone"], Ctone=src["Ctone"],
                vol_knob=src["vol_knob"], tone_knob=src["tone_knob"],
                dist_mm=src["dist_mm"], scale_mm=src["scale_mm"],
            ))
        return pus

    def _compute_and_push(self):
        cable  = self.state.ccable_pf * 1e-12
        tbleed = self.state.tbleed
        wiring = self.state.wiring
        active = self._active()

        cur = sweep(self._make_params(), active, cable, tbleed, wiring)
        ref = sweep(self._make_params(lambda p: {**p, "vol_knob": 10, "tone_knob": 10}),
                    active, cable, tbleed, wiring)

        anchor = float(np.max(ref)) or 1.0
        cur_db = (20 * np.log10(np.clip(cur / anchor, 1e-12, None))).tolist()
        ref_db = (20 * np.log10(np.clip(ref / anchor, 1e-12, None))).tolist()

        pk_idx = int(np.argmax(cur_db))
        self.state.chart_cur   = cur_db
        self.state.chart_ref   = ref_db
        self.state.chart_peak  = round(float(FREQS[pk_idx]))

        def _db_at(f):
            idx = int(np.argmin(np.abs(FREQS - f)))
            return round(cur_db[idx], 1)

        self.state.chart_stats = {
            "200":  _db_at(200),
            "500":  _db_at(500),
            "1000": _db_at(1000),
            "4000": _db_at(4000),
        }

    # ── reactive handlers ─────────────────────────────────────────────────
    @change("layout")
    def on_layout(self, layout, **_):
        defs = LAYOUTS[layout]
        self.state.pickups     = _default_pickups(layout)
        self.state.tog_options = _toggle_options(len(defs))
        n = len(defs)
        self.state.toggle_idx  = next(
            (i for i, t in enumerate(self.state.tog_options) if len(t["active"]) == n), 0
        )
        self._compute_and_push()

    @change("wiring", "tbleed", "ccable_pf", "toggle_idx")
    def on_shared_change(self, **_):
        self._compute_and_push()

    @change("pickups")
    def on_pickups_change(self, **_):
        self._compute_and_push()

    def strum(self):
        self.state.busy = True
        self.state.audio_error = ""
        try:
            cable  = self.state.ccable_pf * 1e-12
            active = self._active()
            resp   = sweep(self._make_params(), active, cable,
                           self.state.tbleed, self.state.wiring)
            wav    = render_strum(resp)
            self.state.audio_b64 = base64.b64encode(wav).decode()
        except Exception as e:
            self.state.audio_error = str(e)
        finally:
            self.state.busy = False

    # ── UI ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.ctrl.strum = self.strum

        with SinglePageLayout(self.server) as layout:
            layout.title.set_text("Guitar Electronics Simulator")

            with layout.toolbar:
                v.VSpacer()
                v.VSelect(
                    v_model=("layout",),
                    items=([
                        {"title": "HH — Les Paul",      "value": "HH"},
                        {"title": "HSS — Strat",        "value": "HSS"},
                        {"title": "HHS",                "value": "HHS"},
                        {"title": "SSS — 3× single",    "value": "SSS"},
                        {"title": "H — single HB",      "value": "H"},
                        {"title": "SS — Telecaster",    "value": "SS"},
                    ],),
                    label="Layout", density="compact",
                    hide_details=True, style="max-width:200px;",
                )
                v.VSelect(
                    v_model=("wiring",),
                    items=([{"title": "50s wiring", "value": "50s"},
                            {"title": "Modern wiring", "value": "modern"}],),
                    label="Wiring", density="compact",
                    hide_details=True, style="max-width:160px; margin-left:8px;",
                )

            with layout.content:
                with v.VContainer(fluid=True, classes="pa-3"):
                    # ── toggle row ────────────────────────────────────────
                    with v.VRow(classes="mb-2"):
                        with v.VCol():
                            html.Div("Pickup selector", classes="text-caption text-uppercase text-medium-emphasis mb-1")
                            with html.Div(style="display:flex;gap:6px;flex-wrap:wrap;"):
                                with v.VBtnToggle(
                                    v_model=("toggle_idx",),
                                    mandatory=True, density="compact",
                                ):
                                    with v.VBtn(
                                        v_for="(opt, i) in tog_options",
                                        key="i", value=("i",),
                                        size="small",
                                    ):
                                        html.Span("{{ opt.label }}")

                    # ── pickup cards ─────────────────────────────────────
                    html.Div("Pickups", classes="text-caption text-uppercase text-medium-emphasis mb-1")
                    with v.VRow(classes="mb-2"):
                        with v.VCol(
                            v_for="(pu, idx) in pickups",
                            key="idx",
                            cols=12, sm=6, md=4,
                        ):
                            self._pickup_card()

                    # ── shared controls ──────────────────────────────────
                    html.Div("Shared", classes="text-caption text-uppercase text-medium-emphasis mb-1")
                    with v.VRow(classes="mb-2"):
                        with v.VCol(cols=12, sm=6, md=4):
                            with v.VCard(variant="outlined"):
                                with v.VCardText():
                                    v.VSelect(
                                        v_model=("tbleed",),
                                        items=([
                                            {"title": "No treble bleed",          "value": "none"},
                                            {"title": "Cap only (100 pF)",        "value": "cap"},
                                            {"title": "Cap + resistor (100pF/150k)", "value": "network"},
                                        ],),
                                        label="Treble bleed", density="compact", hide_details=True,
                                        classes="mb-3",
                                    )
                                    html.Div("Cable capacitance", classes="text-caption text-medium-emphasis")
                                    v.VSlider(
                                        v_model=("ccable_pf",),
                                        min=0, max=2000, step=50,
                                        thumb_label=True, thumb_size=20,
                                        append_icon="mdi-cable-data",
                                        __properties=[("thumb_label", "thumb-label")],
                                    )

                    # ── strum button + stats ─────────────────────────────
                    with v.VRow(classes="mb-2", align="center"):
                        with v.VCol(cols="auto"):
                            v.VBtn(
                                "Strum  E A D G B e",
                                prepend_icon="mdi-music-note",
                                color="primary", variant="outlined",
                                loading=("busy",),
                                click=self.strum,
                            )
                        with v.VCol():
                            html.Span(
                                "Peak: {{ chart_peak }} Hz  |  "
                                "200 Hz: {{ chart_stats['200'] }} dB  "
                                "500 Hz: {{ chart_stats['500'] }} dB  "
                                "1 kHz: {{ chart_stats['1000'] }} dB  "
                                "4 kHz: {{ chart_stats['4000'] }} dB",
                                classes="text-caption text-medium-emphasis",
                            )

                    # ── frequency response chart ─────────────────────────
                    with v.VCard(variant="outlined"):
                        with v.VCardText():
                            # Chart.js rendered via trame client-side JS
                            html.Div(style="position:relative;height:300px;")

                    # ── audio playback (client-side) ─────────────────────
                    client.Script("""
window.trameReady = () => {
  trame.state.watch('audio_b64', (b64) => {
    if (!b64) return;
    const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    const blob = new Blob([bytes], {type:'audio/wav'});
    const url  = URL.createObjectURL(blob);
    const a    = new Audio(url);
    a.play().catch(e => console.warn('Audio play:', e));
  });
};
                    """)

    def _pickup_card(self):
        """Pickup card template — uses v-for binding from parent."""
        with v.VCard(variant="outlined"):
            with v.VCardText():
                html.Div(
                    "{{ pu.pos }} ({{ pu.type === 'humbucker' ? 'HB' : pu.type === 'p90' ? 'P90' : 'SC' }})",
                    classes="text-subtitle-2 font-weight-medium mb-2",
                    style="color: #378ADD",
                )
                # Knob controls — note these use inline JS to mutate pickups array
                html.Div("Volume", classes="text-caption text-medium-emphasis")
                v.VSlider(
                    v_model=("pickups[idx].vol_knob",),
                    min=0, max=10, step=0.1,
                    thumb_label=True, thumb_size=18,
                    __properties=[("thumb_label", "thumb-label")],
                )
                html.Div("Tone", classes="text-caption text-medium-emphasis")
                v.VSlider(
                    v_model=("pickups[idx].tone_knob",),
                    min=0, max=10, step=0.1,
                    thumb_label=True, thumb_size=18,
                    __properties=[("thumb_label", "thumb-label")],
                )
                with v.VRow(dense=True):
                    with v.VCol(cols=6):
                        v.VSelect(
                            v_model=("pickups[idx].Rvol",),
                            items=([{"title": "250kΩ", "value": 250000},
                                    {"title": "500kΩ", "value": 500000},
                                    {"title": "1MΩ",   "value": 1000000}],),
                            label="Vol pot", density="compact", hide_details=True,
                        )
                    with v.VCol(cols=6):
                        v.VSelect(
                            v_model=("pickups[idx].Rtone",),
                            items=([{"title": "250kΩ", "value": 250000},
                                    {"title": "500kΩ", "value": 500000},
                                    {"title": "1MΩ",   "value": 1000000}],),
                            label="Tone pot", density="compact", hide_details=True,
                        )
                html.Div("Tone cap (nF)", classes="text-caption text-medium-emphasis mt-2")
                v.VSlider(
                    v_model=("pickups[idx].Ctone_nf",),
                    min=1, max=100, step=1,
                    thumb_label=True, thumb_size=18,
                    __properties=[("thumb_label", "thumb-label")],
                )
                v.VDivider(classes="my-2")
                html.Div("Position", classes="text-caption text-medium-emphasis")
                html.Div("Dist from bridge (mm)", classes="text-caption text-medium-emphasis")
                v.VSlider(
                    v_model=("pickups[idx].dist_mm",),
                    min=5, max=320, step=1,
                    thumb_label=True, thumb_size=18,
                    __properties=[("thumb_label", "thumb-label")],
                )


def main():
    app = GuitarSim()
    app.server.start()


if __name__ == "__main__":
    main()
