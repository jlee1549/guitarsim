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
from trame.decorators import TrameApp, change

import numpy as np, base64

from taper_utils import vol_pct_to_knob, knob_to_vol_pct
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
            "base_rdc":db[0]["rdc"],"base_L":db[0]["L"],"base_Cp":db[0]["Cp"],
            "Rvol":500000,"Rtone":500000,"Ctone_nf":22,
            "vol_knob":10.0,"tone_knob":10.0,
            "vol_pct":100.0,"tone_pct":100.0,
            "polarity":1, "coil_config":"series", "coil_side":"outer",
            "dist_mm":dp["dist_mm"],"tbleed":"none","has_tone":True}

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
        self.state.r_amp_kohm  = 500       # amp input impedance in kΩ (500kΩ typical)
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
        self.state.chart_stats  = {"peak":0,"db200":0.0,"db500":0.0,"db1k":0.0,"db4k":0.0}
        self.state.chart_note   = ""

        self._compute_and_push()
        self._build_ui()

    # ── flat state helpers ────────────────────────────────────────────────
    def _push_pu_state(self):
        for i,p in enumerate(self._pu_data):
            ptype = p["type"]
            presets_list = {"humbucker": self.state.hb_presets,
                            "single":    self.state.sc_presets,
                            "p90":       self.state.p90_presets}.get(ptype, self.state.hb_presets)
            setattr(self.state,f"pu{i}_presets",     presets_list)
            setattr(self.state,f"pu{i}_vol",         p["vol_pct"])
            setattr(self.state,f"pu{i}_tone",        p["tone_pct"])
            setattr(self.state,f"pu{i}_rvol",        p["Rvol"])
            setattr(self.state,f"pu{i}_rtone",       p["Rtone"])
            setattr(self.state,f"pu{i}_ctone_nf",    p["Ctone_nf"])
            setattr(self.state,f"pu{i}_dist_mm",     p["dist_mm"])
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
            if t == "tone1":   t_alpha = tone1_pct / 100.0
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

        self.state.chart_cur = cur_db
        self.state.chart_ref = ref_db

        def at(f): return round(cur_db[int(np.argmin(np.abs(FREQS-f)))],1)
        self.state.chart_stats = {"peak":round(float(FREQS[int(np.argmax(cur_db))])),"db200":at(200),"db500":at(500),"db1k":at(1000),"db4k":at(4000)}

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
                f"pu{i}_ctone_nf",f"pu{i}_dist_mm",f"pu{i}_tbleed",
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
                self._pu_data[i]["base_rdc"] = p["rdc"]
                self._pu_data[i]["base_L"]   = p["L"]
                self._pu_data[i]["base_Cp"]  = p["Cp"]
                self._pu_data[i]["rdc"]      = p["rdc"]
                self._pu_data[i]["L"]        = p["L"]
                self._pu_data[i]["Cp"]       = p["Cp"]
                # Reset coil config to series when preset changes
                self._pu_data[i]["coil_config"] = "series"
                setattr(self.state, f"pu{i}_coil_config", "series")
            self._compute_and_push()

    def pluck(self):
        self.state.busy = True; self.state.status_msg = "rendering..."
        try:
            self._pull_pu_state()
            active = self._active()
            cable  = self.state.ccable_pf * 1e-12
            r_amp  = self.state.r_amp_kohm * 1e3
            pus    = self._make_params()
            si     = int(self.state.pluck_string)
            f0     = OPEN_STRINGS[si]      # per-string comb velocity
            resp   = sweep(pus, active, cable, self.state.wiring, R_amp=r_amp, f0=f0)
            ref    = sweep(self._make_ref_params(), active, cable, self.state.wiring, R_amp=r_amp, f0=f0)
            ref_gain = float(np.max(resp))/(float(np.max(ref)) or 1.0)
            wav = render_pluck(resp,string_idx=si,
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
        for i in range(MAX_PU):
            self._make_pu_watcher(i)
            self._make_preset_watcher(i)
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
                                    v.VSlider(v_model=("ccable_pf",),min=0,max=2000,step=50,hide_details=True,classes="mb-2")
                                    html.Div("Amp input: {{ r_amp_kohm }} kΩ",classes="text-caption text-medium-emphasis")
                                    v.VSlider(v_model=("r_amp_kohm",),min=100,max=2000,step=100,hide_details=True)
                        with v.VCol(cols=12,sm=6,md=4):
                            with v.VCard(variant="outlined"):
                                with v.VCardText():
                                    v.VSelect(v_model=("vol_taper",),items=(TAPER_ITEMS,),label="Volume pot taper",density="compact",hide_details=True,classes="mb-3")
                                    v.VSelect(v_model=("tone_taper",),items=(TAPER_ITEMS,),label="Tone pot taper",density="compact",hide_details=True)
                        # Shared master controls — only visible for shared-vol layouts
                        with v.VCol(cols=12,sm=6,md=4,v_show="shared_vol"):
                            with v.VCard(variant="outlined"):
                                with v.VCardText():
                                    html.Div("Master volume: {{ master_vol.toFixed(0) }}%",classes="text-caption text-medium-emphasis")
                                    v.VSlider(v_model=("master_vol",),min=0,max=100,step=1,hide_details=True,color="primary",classes="mb-2")
                                    html.Div("Tone 1 (neck): {{ tone1_knob.toFixed(0) }}%",classes="text-caption text-medium-emphasis")
                                    v.VSlider(v_model=("tone1_knob",),min=0,max=100,step=1,hide_details=True,color="secondary",classes="mb-2")
                                    # Tone 2 only visible for SSS/HSS (has 2 tone pots)
                                    with html.Div(v_show="tone_map.filter(t=>t==='tone2').length > 0"):
                                        html.Div("Tone 2 (mid): {{ tone2_knob.toFixed(0) }}%",classes="text-caption text-medium-emphasis")
                                        v.VSlider(v_model=("tone2_knob",),min=0,max=100,step=1,hide_details=True,color="secondary")

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
                             classes="text-caption text-medium-emphasis font-weight-medium mb-1")
                    html.Div("{{ chart_note }}",
                             classes="text-caption text-medium-emphasis font-italic mb-2",
                             style="color: #F9A825;",
                             v_show="chart_note")

                    # Chart
                    with v.VCard(variant="outlined"):
                        with v.VCardText(classes="pa-1"):
                            html.Div(
                                '<div style="position:relative;height:300px;width:100%;"><canvas id="freqChart" style="display:block;"></canvas></div>',
                                style="width:100%;",
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
                v.VDivider(classes="my-2")
                v.VSelect(v_model=(f"{p}tbleed",),items=(TBLEED_ITEMS,),label="Treble bleed",density="compact",hide_details=True)


def main():
    app = GuitarSim()
    app.server.start(host="0.0.0.0")

if __name__ == "__main__":
    main()
