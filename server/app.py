"""
app.py — Guitar Electronics Simulator (trame)

Graph: Chart.js rendered via client.Script — no trame-plotly dependency.
Audio: WAV bytes pushed as base64 state, decoded via Web Audio API in JS.
State: flat indexed keys for pickup params (trame watches top-level keys).
"""
from trame.app import get_server
from trame.ui.vuetify3 import SinglePageLayout
from trame.widgets import vuetify3 as v, html, client
from trame.decorators import TrameApp, change

import numpy as np, base64

from simulation import PickupParams, sweep, FREQS
from audio import render_pluck, OPEN_STRINGS, STRING_NAMES, DEFAULT_PLUCK_POS
from pickup_db import PICKUPS, LAYOUTS, POSITION_DEFAULTS

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
    return {"pos":pos,"type":ptype,"rdc":db[0]["rdc"],"L":db[0]["L"],"Cp":db[0]["Cp"],
            "Rvol":500000,"Rtone":500000,"Ctone_nf":22,"vol_knob":10.0,"tone_knob":10.0,
            "dist_mm":dp["dist_mm"],"tbleed":"none"}

@TrameApp()
class GuitarSim:
    def __init__(self, server=None):
        self.server = server or get_server()
        self.state  = self.server.state
        self.ctrl   = self.server.controller

        # Shared
        self.state.layout      = "HH"
        self.state.wiring      = "50s"
        self.state.ccable_pf   = 500
        self.state.scale_mm    = 628       # instrument scale length (shared)
        self.state.vol_taper   = "audio"
        self.state.tone_taper  = "audio"
        self.state.toggle_idx  = 1
        self.state.tog_options = _toggle_options(2)
        self.state.n_pickups   = 2
        self.state.pu_labels   = ["neck (HB)","bridge (HB)",""]
        self.state.pluck_string= 1
        self.state.pluck_pos   = 12        # percent
        self.state.string_items= [{"title":f"{STRING_NAMES[i]} — {OPEN_STRINGS[i]:.1f} Hz","value":i} for i in range(6)]
        self.state.busy        = False
        self.state.status_msg  = "ready"
        self.state.audio_b64   = ""
        self.state.audio_token = 0   # increments each pluck so JS detects new audio

        # Preset lists
        self.state.hb_presets  = [p["name"] for p in PICKUPS["humbucker"]]
        self.state.sc_presets  = [p["name"] for p in PICKUPS["single"]]
        self.state.p90_presets = [p["name"] for p in PICKUPS["p90"]]

        # Flat pickup state
        self._pu_data = [_default_pu("neck","humbucker"),
                         _default_pu("bridge","humbucker"),
                         _default_pu("bridge","humbucker")]
        self._push_pu_state()

        # Chart state — plain lists, rendered by Chart.js in client.Script
        self._freqs = [round(f,1) for f in FREQS.tolist()]
        self.state.chart_freqs  = self._freqs
        self.state.chart_cur    = [0.0]*len(FREQS)
        self.state.chart_ref    = [0.0]*len(FREQS)
        self.state.chart_stats  = {"peak":0,"db200":0.0,"db500":0.0,"db1k":0.0,"db4k":0.0}

        self._compute_and_push()
        self._build_ui()

    # ── flat state helpers ────────────────────────────────────────────────
    def _push_pu_state(self):
        for i,p in enumerate(self._pu_data):
            setattr(self.state,f"pu{i}_vol",     p["vol_knob"])
            setattr(self.state,f"pu{i}_tone",    p["tone_knob"])
            setattr(self.state,f"pu{i}_rvol",    p["Rvol"])
            setattr(self.state,f"pu{i}_rtone",   p["Rtone"])
            setattr(self.state,f"pu{i}_ctone_nf",p["Ctone_nf"])
            setattr(self.state,f"pu{i}_dist_mm", p["dist_mm"])
            setattr(self.state,f"pu{i}_tbleed",  p["tbleed"])

    def _pull_pu_state(self):
        for i in range(MAX_PU):
            self._pu_data[i]["vol_knob"]  = getattr(self.state,f"pu{i}_vol",    10.0)
            self._pu_data[i]["tone_knob"] = getattr(self.state,f"pu{i}_tone",   10.0)
            self._pu_data[i]["Rvol"]      = getattr(self.state,f"pu{i}_rvol",   500000)
            self._pu_data[i]["Rtone"]     = getattr(self.state,f"pu{i}_rtone",  500000)
            self._pu_data[i]["Ctone_nf"]  = getattr(self.state,f"pu{i}_ctone_nf",22)
            self._pu_data[i]["dist_mm"]   = getattr(self.state,f"pu{i}_dist_mm",80)
            self._pu_data[i]["tbleed"]    = getattr(self.state,f"pu{i}_tbleed", "none")

    def _active(self):
        opts = self.state.tog_options; idx = self.state.toggle_idx
        return opts[idx]["active"] if 0 <= idx < len(opts) else [0]

    def _make_params(self):
        self._pull_pu_state()
        scale = self.state.scale_mm
        return [PickupParams(rdc=p["rdc"],L=p["L"],Cp=p["Cp"],
            Rvol=p["Rvol"],Rtone=p["Rtone"],Ctone=p["Ctone_nf"]*1e-9,
            vol_knob=p["vol_knob"],tone_knob=p["tone_knob"],
            dist_mm=p["dist_mm"],scale_mm=scale,
            vol_taper=self.state.vol_taper,tone_taper=self.state.tone_taper,
            tbleed=p["tbleed"],
        ) for p in self._pu_data]

    def _compute_and_push(self):
        self._pull_pu_state()
        cable  = self.state.ccable_pf * 1e-12
        active = self._active()
        pus    = self._make_params()

        # Per-pickup tbleed is now on PickupParams.tbleed — no separate arg needed
        cur = sweep(pus, active, cable, self.state.wiring)
        ref_pus = [PickupParams(rdc=p["rdc"],L=p["L"],Cp=p["Cp"],
            Rvol=p["Rvol"],Rtone=p["Rtone"],Ctone=p["Ctone_nf"]*1e-9,
            vol_knob=10.0,tone_knob=10.0,dist_mm=p["dist_mm"],
            scale_mm=self.state.scale_mm,
            vol_taper=self.state.vol_taper,tone_taper=self.state.tone_taper,
            tbleed=p["tbleed"],
        ) for p in self._pu_data]
        ref = sweep(ref_pus, active, cable, self.state.wiring)

        anchor = float(np.max(ref)) or 1.0
        cur_db = (20*np.log10(np.clip(cur/anchor,1e-12,None))).tolist()
        ref_db = (20*np.log10(np.clip(ref/anchor,1e-12,None))).tolist()

        self.state.chart_cur = cur_db
        self.state.chart_ref = ref_db

        def at(f): return round(cur_db[int(np.argmin(np.abs(FREQS-f)))],1)
        self.state.chart_stats = {"peak":round(float(FREQS[int(np.argmax(cur_db))])),"db200":at(200),"db500":at(500),"db1k":at(1000),"db4k":at(4000)}

    # ── reactive handlers ─────────────────────────────────────────────────
    @change("layout")
    def on_layout(self, layout, **_):
        defs = LAYOUTS[layout]; n = len(defs)
        for i,d in enumerate(defs): self._pu_data[i] = _default_pu(d["pos"],d["type"])
        self._push_pu_state()
        self.state.n_pickups   = n
        self.state.pu_labels   = [f"{d['pos']} ({'HB' if d['type']=='humbucker' else 'P90' if d['type']=='p90' else 'SC'})" for d in defs]+[""]*(MAX_PU-n)
        self.state.tog_options = _toggle_options(n)
        self.state.toggle_idx  = next((i for i,t in enumerate(self.state.tog_options) if len(t["active"])==n),0)
        self._compute_and_push()

    @change("wiring","ccable_pf","toggle_idx","scale_mm","vol_taper","tone_taper")
    def on_shared(self, **_):
        self._compute_and_push()

    def _make_pu_watcher(self, i):
        keys = [f"pu{i}_vol",f"pu{i}_tone",f"pu{i}_rvol",f"pu{i}_rtone",
                f"pu{i}_ctone_nf",f"pu{i}_dist_mm",f"pu{i}_tbleed"]
        @self.state.change(*keys)
        def _watch(**_): self._compute_and_push()

    def pluck(self):
        self.state.busy = True; self.state.status_msg = "rendering..."
        try:
            self._pull_pu_state()
            active = self._active()
            cable  = self.state.ccable_pf * 1e-12
            pus    = self._make_params()
            resp   = sweep(pus, active, cable, self.state.wiring)
            ref_pus= [PickupParams(rdc=p["rdc"],L=p["L"],Cp=p["Cp"],
                Rvol=p["Rvol"],Rtone=p["Rtone"],Ctone=p["Ctone_nf"]*1e-9,
                vol_knob=10.0,tone_knob=10.0,dist_mm=p["dist_mm"],
                scale_mm=self.state.scale_mm,
                vol_taper=self.state.vol_taper,tone_taper=self.state.tone_taper,
                tbleed=p["tbleed"],
            ) for p in self._pu_data]
            ref    = sweep(ref_pus, active, cable, self.state.wiring)
            ref_gain = float(np.max(resp))/(float(np.max(ref)) or 1.0)
            wav = render_pluck(resp,string_idx=int(self.state.pluck_string),
                               pluck_pos=self.state.pluck_pos/100.0,
                               reference_gain=ref_gain)
            self.state.audio_b64  = base64.b64encode(wav).decode()
            self.state.audio_token = (self.state.audio_token or 0) + 1
            self.state.status_msg = f"plucked {STRING_NAMES[int(self.state.pluck_string)]}"
        except Exception as e:
            self.state.status_msg = f"error: {e}"
            import traceback; traceback.print_exc()
        finally:
            self.state.busy = False

    # ── UI ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        for i in range(MAX_PU): self._make_pu_watcher(i)
        with SinglePageLayout(self.server) as layout:
            layout.title.set_text("Guitar Electronics Simulator")

            # ── JS: Chart.js graph + audio playback ──────────────────────
            client.Style("body{background:#f5f5f3;}")
            client.Script("""
(function(){
// ── Audio ──────────────────────────────────────────────────────────────
var _ctx=null, _lastToken=-1;
function getCtx(){
  if(!_ctx) _ctx=new(window.AudioContext||window.webkitAudioContext)();
  if(_ctx.state==='suspended') _ctx.resume();
  return _ctx;
}
function playWav(b64){
  try{
    var binary = atob(b64);
    var bytes = new Uint8Array(binary.length);
    for(var i=0;i<binary.length;i++) bytes[i]=binary.charCodeAt(i);
    // Verify WAV header
    if(bytes[0]!==82||bytes[1]!==73||bytes[2]!==70||bytes[3]!==70){
      console.warn('Invalid WAV header'); return;
    }
    var ctx = getCtx();
    // Clone buffer — decodeAudioData detaches it
    ctx.decodeAudioData(bytes.buffer.slice(0), function(buf){
      var src=ctx.createBufferSource();
      var g=ctx.createGain(); g.gain.value=0.8;
      src.buffer=buf; src.connect(g); g.connect(ctx.destination);
      src.start();
    }, function(e){ console.warn('decodeAudioData error',e); });
  }catch(e){ console.warn('playWav error',e); }
}

// ── Chart ───────────────────────────────────────────────────────────────
var _chart=null;
function initChart(){
  var canvas=document.getElementById('freqChart');
  if(!canvas||_chart) return;
  _chart=new Chart(canvas,{
    type:'line',
    data:{datasets:[
      {label:'current',data:[],borderColor:'#378ADD',borderWidth:2,pointRadius:0,tension:0.3},
      {label:'ref (knobs@10)',data:[],borderColor:'#888',borderWidth:1.5,pointRadius:0,tension:0.3,borderDash:[6,3]}
    ]},
    options:{responsive:true,maintainAspectRatio:false,animation:false,
      plugins:{legend:{position:'bottom',labels:{boxWidth:20,font:{size:11}}},
        tooltip:{callbacks:{title:function(i){return Math.round(i[0].parsed.x)+' Hz';},
          label:function(c){return c.dataset.label+': '+c.parsed.y.toFixed(1)+' dB';}}}},
      scales:{
        x:{type:'logarithmic',min:80,max:18000,title:{display:true,text:'frequency (Hz)',font:{size:11}},
          ticks:{callback:function(v){var s=[100,200,500,1000,2000,5000,10000];
            return s.indexOf(Math.round(v))>=0?(v>=1000?v/1000+'k':v):null;}}},
        y:{title:{display:true,text:'level (dB)',font:{size:11}},grid:{color:'rgba(128,128,128,0.15)'}}
      }
    }
  });
}
function updateChart(freqs,cur,ref){
  if(!_chart) return;
  var allVals=cur.concat(ref).filter(isFinite);
  var yMin=Math.floor((Math.min.apply(null,allVals)-3)/5)*5;
  var yMax=Math.ceil((Math.max.apply(null,allVals)+2)/5)*5;
  _chart.data.datasets[0].data=freqs.map(function(f,i){return{x:f,y:cur[i]};});
  _chart.data.datasets[1].data=freqs.map(function(f,i){return{x:f,y:ref[i]};});
  _chart.options.scales.y.min=yMin; _chart.options.scales.y.max=yMax;
  _chart.update('none');
}

// ── Poll trame state ─────────────────────────────────────────────────────
function poll(){
  try{
    var s=window.trame&&window.trame.state&&window.trame.state.state;
    if(s){
      // Chart
      if(s.chart_cur&&s.chart_freqs) updateChart(s.chart_freqs,s.chart_cur,s.chart_ref||[]);
      // Audio — only play when token changes
      var tok=s.audio_token||0;
      if(tok!==_lastToken&&tok>0&&s.audio_b64){
        _lastToken=tok; playWav(s.audio_b64);
      }
      // Init chart on first connection
      if(!_chart) initChart();
    }
  }catch(e){}
  setTimeout(poll,500);
}
// Load Chart.js then start polling
var sc=document.createElement('script');
sc.src='https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js';
sc.onload=function(){initChart();poll();};
document.head.appendChild(sc);
})();
""")

            with layout.toolbar:
                v.VSpacer()
                v.VSelect(v_model=("layout",),items=(LAYOUT_ITEMS,),label="Layout",density="compact",hide_details=True,style="max-width:200px;")
                v.VSelect(v_model=("wiring",),items=(WIRING_ITEMS,),label="Wiring",density="compact",hide_details=True,style="max-width:160px;margin-left:8px;")

            with layout.content:
                with v.VContainer(fluid=True, classes="pa-3"):

                    # Toggle
                    html.Div("Pickup selector",classes="text-caption text-uppercase text-medium-emphasis mb-1")
                    with v.VBtnToggle(v_model=("toggle_idx",),mandatory=True,density="compact",classes="mb-3"):
                        with v.VBtn(v_for="(opt,ti) in tog_options",key="ti",value=("ti",),size="small"):
                            html.Span("{{ opt.label }}")

                    # Pickup cards — explicit, no v-for (trame nested state problem)
                    html.Div("Pickups",classes="text-caption text-uppercase text-medium-emphasis mb-1")
                    with v.VRow(classes="mb-2"):
                        for i in range(MAX_PU):
                            with v.VCol(cols=12,sm=6,md=4,v_show=f"n_pickups > {i}"):
                                self._pickup_card(i)

                    # Shared controls
                    html.Div("Instrument",classes="text-caption text-uppercase text-medium-emphasis mb-1")
                    with v.VRow(classes="mb-2"):
                        with v.VCol(cols=12,sm=6,md=4):
                            with v.VCard(variant="outlined"):
                                with v.VCardText():
                                    html.Div("Scale length: {{ scale_mm }} mm",classes="text-caption text-medium-emphasis")
                                    v.VSlider(v_model=("scale_mm",),min=580,max=710,step=1,hide_details=True,classes="mb-2")
                                    html.Div("Cable cap: {{ ccable_pf }} pF",classes="text-caption text-medium-emphasis")
                                    v.VSlider(v_model=("ccable_pf",),min=0,max=2000,step=50,hide_details=True)
                        with v.VCol(cols=12,sm=6,md=4):
                            with v.VCard(variant="outlined"):
                                with v.VCardText():
                                    v.VSelect(v_model=("vol_taper",),items=(TAPER_ITEMS,),label="Volume pot taper",density="compact",hide_details=True,classes="mb-3")
                                    v.VSelect(v_model=("tone_taper",),items=(TAPER_ITEMS,),label="Tone pot taper",density="compact",hide_details=True)

                    # Pluck controls
                    html.Div("Pluck",classes="text-caption text-uppercase text-medium-emphasis mb-1")
                    with v.VRow(align="center",classes="mb-1"):
                        with v.VCol(cols=12,sm="auto"):
                            v.VSelect(v_model=("pluck_string",),items=("string_items",),label="String",density="compact",hide_details=True,style="min-width:160px;")
                        with v.VCol(cols=12,sm=4):
                            html.Div("Position: {{ pluck_pos }}% from bridge",classes="text-caption text-medium-emphasis")
                            v.VSlider(v_model=("pluck_pos",),min=3,max=45,step=1,hide_details=True)
                        with v.VCol(cols="auto"):
                            v.VBtn("Pluck",prepend_icon="mdi-music-note",color="primary",variant="outlined",loading=("busy",),click=self.pluck)
                        with v.VCol():
                            html.Div("{{ status_msg }}",classes="text-caption text-medium-emphasis")

                    # Stats
                    html.Div("Peak: {{ chart_stats.peak }} Hz  |  200 Hz: {{ chart_stats.db200 }} dB  500 Hz: {{ chart_stats.db500 }} dB  1 kHz: {{ chart_stats.db1k }} dB  4 kHz: {{ chart_stats.db4k }} dB",
                             classes="text-caption text-medium-emphasis font-weight-medium mb-2")

                    # Chart
                    with v.VCard(variant="outlined"):
                        with v.VCardText(classes="pa-1"):
                            html.Div(
                                '<div style="position:relative;height:300px;width:100%;"><canvas id="freqChart" style="display:block;"></canvas></div>',
                                style="width:100%;",
                            )

    def _pickup_card(self, i):
        p = f"pu{i}_"
        with v.VCard(variant="outlined"):
            with v.VCardText(classes="pa-3"):
                html.Div(f"{{{{ pu_labels[{i}] }}}}",classes="text-subtitle-2 font-weight-medium mb-2",style=f"color:{COLORS[i]}")
                html.Div(f"Volume: {{{{ {p}vol.toFixed(1) }}}}",classes="text-caption text-medium-emphasis")
                v.VSlider(v_model=(f"{p}vol",),min=0,max=10,step=0.1,hide_details=True,color="primary")
                html.Div(f"Tone: {{{{ {p}tone.toFixed(1) }}}}",classes="text-caption text-medium-emphasis")
                v.VSlider(v_model=(f"{p}tone",),min=0,max=10,step=0.1,hide_details=True,color="secondary")
                with v.VRow(dense=True,classes="mt-1"):
                    with v.VCol(cols=6):
                        v.VSelect(v_model=(f"{p}rvol",),items=(POT_ITEMS,),label="Vol pot",density="compact",hide_details=True)
                    with v.VCol(cols=6):
                        v.VSelect(v_model=(f"{p}rtone",),items=(POT_ITEMS,),label="Tone pot",density="compact",hide_details=True)
                html.Div(f"Tone cap: {{{{ {p}ctone_nf }}}} nF",classes="text-caption text-medium-emphasis mt-2")
                v.VSlider(v_model=(f"{p}ctone_nf",),min=1,max=100,step=1,hide_details=True)
                v.VDivider(classes="my-2")
                html.Div("Position",classes="text-caption text-uppercase text-medium-emphasis")
                html.Div(f"Dist from bridge: {{{{ {p}dist_mm }}}} mm",classes="text-caption text-medium-emphasis")
                v.VSlider(v_model=(f"{p}dist_mm",),min=5,max=320,step=1,hide_details=True,color="success")
                v.VDivider(classes="my-2")
                v.VSelect(v_model=(f"{p}tbleed",),items=(TBLEED_ITEMS,),label="Treble bleed",density="compact",hide_details=True)


def main():
    app = GuitarSim()
    app.server.start(host="0.0.0.0")

if __name__ == "__main__":
    main()
