"""
wiring.py — SVG wiring diagram generator for guitar circuit simulator.

Layout philosophy: flow-based, left-to-right signal chain.
Each stage is placed at x = previous_right + gap. No hardcoded column offsets.

Signal chain:
  Pickups → [Selector Switch] → [Vol] → [Tone+Cap] → Jack
  (switch before vol for shared-vol; after vol-bus for independent-vol)
"""
import math

# ── Palette ───────────────────────────────────────────────────────────────────
BG       = "#f8f8f6"
HOT      = "#1a1a1a"
GND_COL  = "#888888"
SIG      = "#1a5fa8"
TONE_C   = "#c04020"
COMP_BG  = "#ffffff"
COMP_BD  = "#333333"
LABEL    = "#222222"
SUB      = "#666666"
INACTIVE = "#cccccc"
WIRE_W   = 1.8

# ── Primitives ────────────────────────────────────────────────────────────────
def _line(x1, y1, x2, y2, stroke=HOT, sw=WIRE_W, dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{stroke}" stroke-width="{sw}"{d} fill="none"/>')

def _rect(x, y, w, h, rx=4, fill=COMP_BG, stroke=COMP_BD, sw=1):
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

def _text(x, y, txt, size=10, fill=LABEL, anchor="middle", weight="normal", italic=False):
    fs = "italic" if italic else "normal"
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" '
            f'text-anchor="{anchor}" font-weight="{weight}" font-style="{fs}" '
            f'font-family="system-ui" dominant-baseline="central">{txt}</text>')

def _circle(x, y, r, fill=COMP_BG, stroke=COMP_BD, sw=1):
    return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

def _path(d, stroke=COMP_BD, sw=1.5, fill="none"):
    return f'<path d="{d}" stroke="{stroke}" stroke-width="{sw}" fill="{fill}"/>'

def _gnd(x, y):
    s  = _line(x, y, x, y+6, stroke=GND_COL, sw=1.5)
    s += _line(x-7, y+6, x+7, y+6, stroke=GND_COL, sw=1.5)
    s += _line(x-5, y+10, x+5, y+10, stroke=GND_COL, sw=1.2)
    s += _line(x-3, y+14, x+3, y+14, stroke=GND_COL, sw=1)
    return s

def _dot(x, y, r=3, fill=HOT):
    return _circle(x, y, r, fill=fill, stroke=fill, sw=0)

# ── Component drawers ─────────────────────────────────────────────────────────
# Each returns (svg_string, named_lugs_dict)
# Lugs are (x, y) connection points.

def draw_pickup(x, y, w, h, pos, ptype, coil_config, coil_side, polarity, active,
                height_mm=2.5, tbleed="none"):
    col  = COMP_BD if active else INACTIVE
    tcol = LABEL   if active else INACTIVE
    s = _rect(x, y, w, h, rx=5, fill=COMP_BG, stroke=col, sw=1.5)
    type_str = {"humbucker":"Humbucker","single":"Single coil","p90":"P-90"}.get(ptype, ptype)
    s += _text(x+w/2, y+12, type_str, size=9, fill=tcol, weight="500")
    pol_mark = " [R]" if polarity == -1 else ""
    s += _text(x+w/2, y+24, pos+pol_mark, size=8, fill=SUB if active else INACTIVE)
    loop_y = y + h/2 + 4
    loop_r = 6
    if ptype == "humbucker" and coil_config == "split":
        for ci in range(2):
            ac = (ci==0 and coil_side=="outer") or (ci==1 and coil_side=="inner")
            cc = COMP_BD if (active and ac) else INACTIVE
            lx = x + 8 + ci*(w/2-4)
            for i in range(3):
                cx = lx + i*loop_r*2 + loop_r
                s += _path(f"M{cx-loop_r:.1f} {loop_y:.1f} A{loop_r} {loop_r} 0 0 1 {cx+loop_r:.1f} {loop_y:.1f}", stroke=cc, sw=1.5)
        mx = x + w/2
        s += _line(mx, y+h/2-6, mx, y+h/2+14, stroke="#cccccc", sw=1, dash="3 2")
    else:
        nc = 5 if ptype in ("single","p90") else 6
        total = nc*loop_r*2; lx0 = x+(w-total)/2
        lc = COMP_BD if active else INACTIVE
        for i in range(nc):
            cx = lx0 + i*loop_r*2 + loop_r
            s += _path(f"M{cx-loop_r:.1f} {loop_y:.1f} A{loop_r} {loop_r} 0 0 1 {cx+loop_r:.1f} {loop_y:.1f}", stroke=lc, sw=1.5)
    by = loop_y + loop_r + 3
    s += _rect(x+8, by, w-16, 5, rx=2, fill="#e8e8e8" if active else "#f0f0f0", stroke=col, sw=1)
    h_col = "#c04020" if height_mm < 1.8 else (SUB if active else INACTIVE)
    s += _text(x+4, by+14, f"h:{height_mm:.1f}mm", size=7, fill=h_col, anchor="start")
    if tbleed != "none" and active:
        s += _text(x+w-4, by+14, "TB cap" if tbleed=="cap" else "TB RC", size=7, fill=SIG, anchor="end")
    hot_y = y + h//2 - 6
    gnd_y = y + h//2 + 10
    s += _circle(x+w, hot_y, 3.5, fill=HOT if active else INACTIVE, stroke=HOT if active else INACTIVE)
    s += _circle(x+w, gnd_y, 3.5, fill=GND_COL, stroke=GND_COL)
    # hot lug on right edge, gnd lug on right edge below
    return s, {"hot": (x+w, hot_y), "gnd": (x+w, gnd_y), "right": x+w}

def draw_pot(x, y, w, h, label, value_pct, pot_type="vol", active=True):
    col  = COMP_BD if active else INACTIVE
    tcol = LABEL   if active else INACTIVE
    scol = (SIG if pot_type=="vol" else TONE_C) if active else INACTIVE
    s = _rect(x, y, w, h, rx=4, fill=COMP_BG, stroke=col, sw=1.2)
    s += _text(x+w/2, y+10, label, size=9, fill=tcol, weight="500")
    tx, ty, tw, th = x+8, y+h//2-4, w-16, 8
    s += _rect(tx, ty, tw, th, rx=2, fill="#eeeeee" if active else "#f5f5f5", stroke=col, sw=1)
    wx = tx + tw*(value_pct/100.0)
    ay1 = ty+th; ay2 = ty+th+12
    s += _line(wx, ay1, wx, ay2, stroke=scol, sw=1.5)
    s += _path(f"M{wx-4:.1f} {ay1+5:.1f} L{wx:.1f} {ay1:.1f} L{wx+4:.1f} {ay1+5:.1f}", stroke=scol, sw=1.5)
    s += _text(x+w/2, y+h-8, f"{int(value_pct)}%", size=8, fill=scol)
    # Fixed output terminal at bottom-centre; dashed internal stub from wiper
    out_x = x + w/2; out_y = y + h
    s += _line(wx, ay2, out_x, ay2, stroke=scol, sw=1, dash="2 2")
    s += _line(out_x, ay2, out_x, out_y, stroke=scol, sw=1.5)
    l1 = (tx,       ty+th/2)   # input lug  (left end of track)
    l3 = (tx+tw,    ty+th/2)   # gnd lug    (right end of track)
    l2 = (out_x,    out_y)     # output lug (bottom-centre, fixed)
    s += _circle(l1[0], l1[1], 3, fill=HOT,    stroke=HOT)
    s += _circle(l3[0], l3[1], 3, fill=GND_COL,stroke=GND_COL)
    s += _circle(l2[0], l2[1], 3, fill=scol,   stroke=scol)
    return s, {"in": l1, "out": l2, "gnd": l3, "right": x+w}

def draw_cap(cx, y, h=36, label="22nF", active=True):
    col = COMP_BD if active else INACTIVE
    pw = 28; gap = 7
    p1y = y+h/2-gap/2-3; p2y = y+h/2+gap/2+3
    s  = _line(cx-pw/2, p1y, cx+pw/2, p1y, stroke=col, sw=3)
    s += _line(cx-pw/2, p2y, cx+pw/2, p2y, stroke=col, sw=3)
    s += _text(cx+pw/2+4, y+h/2, label, size=8, fill=col, anchor="start")
    return s, {"top": (cx, p1y), "bot": (cx, p2y)}

def draw_jack(x, y, w=60, h=56):
    """Signal enters from left (inp lug). Sleeve exits right of jack circle to ground."""
    s  = _rect(x, y, w, h, rx=5, fill=COMP_BG, stroke=COMP_BD, sw=1.2)
    s += _text(x+w/2, y+14, "Output", size=9, fill=LABEL, weight="500")
    s += _text(x+w/2, y+26, "jack",   size=9, fill=LABEL)
    jcx, jcy, jr = x+w/2, y+h-16, 8
    s += _circle(jcx, jcy, jr, fill="#f0f0f0", stroke=COMP_BD, sw=1)
    s += _circle(jcx, jcy, 2.5, fill=COMP_BD, stroke=COMP_BD, sw=0)
    s += _text(jcx, jcy-jr-5, "tip", size=7, fill=SIG)
    s += _text(jcx+jr+4, jcy, "slv", size=7, fill=GND_COL, anchor="start")
    inp = (x, y+h/2)
    slv = (jcx+jr, jcy)
    s += _circle(inp[0], inp[1], 3, fill=SIG,     stroke=SIG)
    s += _circle(slv[0], slv[1], 3, fill=GND_COL, stroke=GND_COL)
    tip_top = (jcx, jcy-jr)
    s += _line(inp[0], inp[1], x+8, inp[1],         stroke=SIG, sw=1)
    s += _line(x+8, inp[1],    x+8, tip_top[1],     stroke=SIG, sw=1)
    s += _line(x+8, tip_top[1],tip_top[0],tip_top[1],stroke=SIG,sw=1)
    return s, {"inp": inp, "slv": slv, "right": x+w}

def draw_selector_switch(cx, cy, n_pos, active_pos):
    """Rotary switch. Input lug on left, output on right."""
    r = 18
    label = f"{n_pos}-way"
    s = _circle(cx, cy, r, fill=COMP_BG, stroke=COMP_BD, sw=1.2)
    s += _text(cx, cy+r+9, label, size=8, fill=SUB)
    spread = 140; start = -90 - spread/2
    for i in range(n_pos):
        angle = math.radians(start + i*spread/(n_pos-1))
        dx = r*math.cos(angle); dy = r*math.sin(angle)
        fill = COMP_BD if i == active_pos else "#cccccc"
        s += _circle(cx+dx, cy+dy, 3, fill=fill, stroke=COMP_BD, sw=0.8)
    angle = math.radians(start + active_pos*spread/(n_pos-1))
    ex = (r-4)*math.cos(angle); ey = (r-4)*math.sin(angle)
    s += _line(cx, cy, cx+ex, cy+ey, stroke=HOT, sw=1.5)
    s += _circle(cx, cy, 3, fill=HOT, stroke=HOT, sw=0)
    inp = (cx-r, cy); out = (cx+r, cy)
    s += _circle(inp[0], inp[1], 3, fill=HOT, stroke=HOT)
    s += _circle(out[0], out[1], 3, fill=SIG, stroke=SIG)
    return s, {"inp": inp, "out": out, "right": cx+r}

# ── Layout constants (sizes only, no positions) ───────────────────────────────
PU_W, PU_H   = 120, 80
POT_W, POT_H = 110, 56
CAP_H, CAP_GAP = 36, 8
SW_R         = 18
JACK_W, JACK_H = 60, 56
GAP          = 24   # horizontal gap between stages
ROW_GAP      = 28   # vertical gap between pickup rows

# ROW_H accommodates pickup box AND pot + cap below it
ROW_H = max(PU_H, POT_H + CAP_GAP + CAP_H) + ROW_GAP

def make_wiring_svg(pu_data, layout, wiring, active_indices, shared_vol,
                    tone_map, width=None):
    """
    Flow-based layout: every x-position is computed from the previous stage's
    right edge + GAP. No hardcoded column numbers.

    Independent-vol signal chain (HH, PP, H, SS-indep):
      Pickups | vol-bus | [3-way switch] | Jack
      each pickup row: Pickup → Vol → Tone → Cap (stacked vertically)

    Shared-vol signal chain (SSS, HSS, HHS, SS-shared):
      Pickups | hot-bus | [5-way switch] | Master-Vol | Tone(s)+Cap(s) | Jack
    """
    n = len(pu_data)
    top_margin = 24
    bot_margin = 68   # room for ground symbols + legend

    # Count unique tone slots for shared-vol width planning
    n_tones = 0
    if shared_vol:
        seen = set()
        for i in range(n):
            tm = tone_map[i] if i < len(tone_map) else ""
            if tm and tm not in seen:
                seen.add(tm); n_tones += 1

    # ── Compute stage x-positions flowing left to right ───────────────────
    x = GAP  # start x for pickups

    # Stage 1: Pickups (tallest row * n)
    pu_x = x
    x = pu_x + PU_W + GAP

    if shared_vol:
        # Stage 2a: Selector switch (shared-vol: before vol)
        sw_x = x + SW_R         # cx of switch circle
        x = sw_x + SW_R + GAP

        # Stage 2b: Master vol pot
        vol_x = x
        x = vol_x + POT_W + GAP

        # Stage 2c: Tone pots (one per unique tone slot)
        tone_xs = []
        for _ in range(n_tones):
            tone_xs.append(x)
            x += POT_W + GAP

    else:
        # Stage 2a: Vol pots (per pickup, at same x; stacked vertically in rows)
        vol_x = x
        x = vol_x + POT_W + GAP

        # Stage 2b: Tone pots + caps (per pickup, stacked)
        # Only if any pickup has a tone pot
        has_any_tone = any(p.get("has_tone", True) for p in pu_data)
        tone_x = x if has_any_tone else None
        if has_any_tone:
            x = tone_x + POT_W + GAP

        # Stage 2c: Signal collection bus
        bus_x = x
        x = bus_x + GAP

        # Stage 2d: Selector switch (independent-vol: after vol-bus, only if n>1)
        if n > 1:
            sw_x = x + SW_R
            x = sw_x + SW_R + GAP
        else:
            sw_x = None

    # Stage 3: Output jack
    jack_x = x
    total_w = jack_x + JACK_W + GAP

    # Total height: n pickup rows + margins
    total_h = top_margin + n * ROW_H + bot_margin
    GND_Y   = total_h - bot_margin + 10

    if width is None:
        width = total_w

    # ── SVG header ────────────────────────────────────────────────────────
    s  = f'<svg width="100%" viewBox="0 0 {width} {total_h}" xmlns="http://www.w3.org/2000/svg">'
    s += f'<rect width="100%" height="100%" fill="{BG}"/>'
    s += _text(width/2, 14, f"{layout} — {wiring} wiring", size=10, fill=SUB, italic=True)
    # Dashed ground rail
    s += _line(GAP, GND_Y, width-GAP, GND_Y, stroke=GND_COL, sw=1, dash="6 3")

    # ── Draw pickups ──────────────────────────────────────────────────────
    hot_lugs = []   # (x, y, active) per pickup — right edge of pickup box
    for i, p in enumerate(pu_data):
        act = i in active_indices
        ry  = top_margin + i * ROW_H
        svg_pu, lugs = draw_pickup(
            pu_x, ry, PU_W, PU_H,
            p["pos"], p["type"], p["coil_config"], p["coil_side"],
            p["polarity"], act,
            height_mm=p.get("height_mm", 2.5),
            tbleed=p.get("tbleed", "none"),
        )
        s += svg_pu
        hot_lugs.append((lugs["hot"][0], lugs["hot"][1], act))
        # Ground wire: short stub right then down
        gx = pu_x + PU_W + 6
        s += _line(lugs["gnd"][0], lugs["gnd"][1], gx, lugs["gnd"][1], stroke=GND_COL, sw=1.2)
        s += _line(gx, lugs["gnd"][1], gx, GND_Y, stroke=GND_COL, sw=1.2)
        s += _gnd(gx, GND_Y)

    # ── SHARED-VOL layout ─────────────────────────────────────────────────
    if shared_vol:
        ys = [hl[1] for hl in hot_lugs]
        cluster_mid_y = top_margin + (n * ROW_H) / 2   # vertical centre of pickup cluster
        bus_x = sw_x - SW_R - GAP//2                   # hot bus just left of switch

        # Hot wires from each pickup to the vertical bus
        for (hx, hy, act) in hot_lugs:
            s += _line(hx, hy, bus_x, hy,
                       stroke=HOT if act else INACTIVE, sw=WIRE_W,
                       dash="" if act else "4 2")
        if len(ys) > 1:
            s += _line(bus_x, min(ys), bus_x, max(ys), stroke=HOT, sw=WIRE_W)
            for hy in ys[1:]:
                s += _dot(bus_x, hy, fill=HOT)

        # Selector switch centred on pickup cluster
        n_pos  = 5 if n >= 3 else 3
        mid_ai = sorted(active_indices)[len(active_indices)//2] if active_indices else 0
        sw_pos = round(mid_ai * (n_pos-1) / max(n-1, 1))
        svg_sw, sw_lugs = draw_selector_switch(sw_x, cluster_mid_y, n_pos, sw_pos)
        s += svg_sw
        # Bus → switch input (horizontal)
        s += _line(bus_x, cluster_mid_y, sw_lugs["inp"][0], sw_lugs["inp"][1],
                   stroke=HOT, sw=WIRE_W)
        # Extend bus from top pickup to switch level if needed
        if min(ys) < cluster_mid_y - 2:
            s += _line(bus_x, min(ys), bus_x, cluster_mid_y, stroke=HOT, sw=WIRE_W)

        # Switch output → Master vol lug1 (horizontal)
        vol_pot_y = cluster_mid_y - POT_H/2
        vol_pct   = pu_data[0].get("vol_pct", 100)
        svg_v, v_lugs = draw_pot(vol_x, vol_pot_y, POT_W, POT_H,
                                  "Master vol", vol_pct, "vol", True)
        s += svg_v
        s += _line(sw_lugs["out"][0], sw_lugs["out"][1],
                   v_lugs["in"][0],  v_lugs["in"][1], stroke=SIG, sw=WIRE_W)
        s += _line(v_lugs["gnd"][0], v_lugs["gnd"][1],
                   v_lugs["gnd"][0], GND_Y, stroke=GND_COL, sw=1.2)
        s += _gnd(v_lugs["gnd"][0], GND_Y)

        # Unique tone pots + caps
        seen = {}; tone_slots = []
        for i, p in enumerate(pu_data):
            tm = tone_map[i] if i < len(tone_map) else ""
            if tm and tm not in seen:
                seen[tm] = i; tone_slots.append((tm, p))

        # 50s: tone from vol wiper; modern: from vol input lug
        src     = v_lugs["out"] if wiring == "50s" else v_lugs["in"]
        src_col = SIG            if wiring == "50s" else HOT
        if tone_slots:
            s += _dot(src[0], src[1], fill=src_col)

        last_tone_out = src   # wire daisy-chains through tone pots
        for ti, (tname, p) in enumerate(tone_slots):
            tx      = tone_xs[ti]
            t_pct   = p.get("tone_pct", 100)
            cap_nf  = int(p.get("Ctone_nf", 22))
            svg_t, t_lugs = draw_pot(tx, vol_pot_y, POT_W, POT_H,
                                      tname.replace("tone","Tone "),
                                      t_pct, "tone", True)
            s += svg_t
            # Horizontal wire from previous source to this tone pot input
            s += _line(last_tone_out[0], last_tone_out[1],
                       t_lugs["in"][0],  last_tone_out[1],
                       stroke=src_col, sw=1.2, dash="4 2")
            s += _line(t_lugs["in"][0], last_tone_out[1],
                       t_lugs["in"][0], t_lugs["in"][1],
                       stroke=src_col, sw=1.2, dash="4 2")
            s += _line(t_lugs["gnd"][0], t_lugs["gnd"][1],
                       t_lugs["gnd"][0], GND_Y, stroke=GND_COL, sw=1.2)
            s += _gnd(t_lugs["gnd"][0], GND_Y)
            # Cap below tone pot
            cap_y = vol_pot_y + POT_H + CAP_GAP
            svg_cap, cap_lugs = draw_cap(t_lugs["out"][0], cap_y, CAP_H,
                                          f"{cap_nf}nF", True)
            s += svg_cap
            s += _line(t_lugs["out"][0], t_lugs["out"][1],
                       cap_lugs["top"][0], cap_lugs["top"][1], stroke=TONE_C, sw=1.2)
            s += _line(cap_lugs["bot"][0], cap_lugs["bot"][1],
                       cap_lugs["bot"][0], GND_Y, stroke=GND_COL, sw=1.2)
            s += _gnd(cap_lugs["bot"][0], GND_Y)
            last_tone_out = t_lugs["out"]

        # Vol wiper → jack (straight horizontal)
        jack_in_y = v_lugs["out"][1]
        jack_y    = jack_in_y - JACK_H/2
        s += _line(v_lugs["out"][0], jack_in_y, jack_x, jack_in_y, stroke=SIG, sw=WIRE_W)
        svg_jack, j_lugs = draw_jack(jack_x, jack_y, JACK_W, JACK_H)
        s += svg_jack
        s += _line(j_lugs["slv"][0], j_lugs["slv"][1],
                   j_lugs["slv"][0], GND_Y, stroke=GND_COL, sw=1.2)
        s += _gnd(j_lugs["slv"][0], GND_Y)

    # ── INDEPENDENT-VOL layout ────────────────────────────────────────────
    else:
        sig_ys = []   # y of each vol wiper output, for signal bus

        for i, p in enumerate(pu_data):
            act      = i in active_indices
            ry       = top_margin + i * ROW_H
            # Vertically centre the pot within the row
            pot_y    = ry + max(0, (PU_H - POT_H) // 2)
            vol_pct  = p.get("vol_pct", 100)
            tone_pct = p.get("tone_pct", 100)
            cap_nf   = int(p.get("Ctone_nf", 22))
            has_tone = p.get("has_tone", True)
            hx, hy   = hot_lugs[i][0], hot_lugs[i][1]

            # Vol pot
            svg_v, v_lugs = draw_pot(vol_x, pot_y, POT_W, POT_H,
                                      "Vol", vol_pct, "vol", act)
            s += svg_v
            # Hot → vol input: horizontal to vol_x then drop to lug
            s += _line(hx, hy, v_lugs["in"][0], hy,
                       stroke=HOT if act else INACTIVE, sw=WIRE_W,
                       dash="" if act else "4 2")
            if abs(hy - v_lugs["in"][1]) > 1:
                s += _line(v_lugs["in"][0], hy, v_lugs["in"][0], v_lugs["in"][1],
                           stroke=HOT if act else INACTIVE, sw=WIRE_W)
            s += _line(v_lugs["gnd"][0], v_lugs["gnd"][1],
                       v_lugs["gnd"][0], GND_Y, stroke=GND_COL, sw=1.2)
            s += _gnd(v_lugs["gnd"][0], GND_Y)

            if has_tone and tone_x is not None:
                svg_t, t_lugs = draw_pot(tone_x, pot_y, POT_W, POT_H,
                                          "Tone", tone_pct, "tone", act)
                s += svg_t
                # 50s: from vol wiper; modern: from vol input
                src     = v_lugs["out"] if wiring == "50s" else v_lugs["in"]
                src_col = SIG            if wiring == "50s" else HOT
                s += _line(src[0], src[1], t_lugs["in"][0], src[1],
                           stroke=src_col, sw=1.2, dash="4 2")
                if abs(src[1] - t_lugs["in"][1]) > 1:
                    s += _line(t_lugs["in"][0], src[1], t_lugs["in"][0], t_lugs["in"][1],
                               stroke=src_col, sw=1.2, dash="4 2")
                s += _dot(src[0], src[1], fill=src_col)
                s += _line(t_lugs["gnd"][0], t_lugs["gnd"][1],
                           t_lugs["gnd"][0], GND_Y, stroke=GND_COL, sw=1.2)
                s += _gnd(t_lugs["gnd"][0], GND_Y)
                # Cap below tone pot
                cap_y = pot_y + POT_H + CAP_GAP
                svg_cap, cap_lugs = draw_cap(t_lugs["out"][0], cap_y, CAP_H,
                                              f"{cap_nf}nF", act)
                s += svg_cap
                s += _line(t_lugs["out"][0], t_lugs["out"][1],
                           cap_lugs["top"][0], cap_lugs["top"][1],
                           stroke=TONE_C if act else INACTIVE, sw=1.2)
                s += _line(cap_lugs["bot"][0], cap_lugs["bot"][1],
                           cap_lugs["bot"][0], GND_Y, stroke=GND_COL, sw=1.2)
                s += _gnd(cap_lugs["bot"][0], GND_Y)

            # Vol wiper → signal bus (horizontal)
            s += _line(v_lugs["out"][0], v_lugs["out"][1], bus_x, v_lugs["out"][1],
                       stroke=SIG if act else INACTIVE, sw=WIRE_W,
                       dash="" if act else "4 2")
            sig_ys.append(v_lugs["out"][1])

        # Vertical signal collection bus
        if len(sig_ys) > 1:
            s += _line(bus_x, min(sig_ys), bus_x, max(sig_ys), stroke=SIG, sw=WIRE_W)
        mid_y = (min(sig_ys) + max(sig_ys)) / 2

        if sw_x is not None:
            # 3-way selector switch between bus and jack
            n_pos  = 3
            mid_ai = sorted(active_indices)[len(active_indices)//2] if active_indices else 0
            sw_pos = round(mid_ai * (n_pos-1) / max(n-1, 1))
            svg_sw, sw_lugs = draw_selector_switch(sw_x, mid_y, n_pos, sw_pos)
            s += svg_sw
            s += _line(bus_x, mid_y, sw_lugs["inp"][0], sw_lugs["inp"][1],
                       stroke=SIG, sw=WIRE_W)
            # Switch output → jack (horizontal)
            jack_in_x = sw_lugs["out"][0]
            jack_in_y = sw_lugs["out"][1]
        else:
            jack_in_x = bus_x
            jack_in_y = mid_y

        jack_y = jack_in_y - JACK_H/2
        s += _line(jack_in_x, jack_in_y, jack_x, jack_in_y, stroke=SIG, sw=WIRE_W)
        svg_jack, j_lugs = draw_jack(jack_x, jack_y, JACK_W, JACK_H)
        s += svg_jack
        s += _line(j_lugs["slv"][0], j_lugs["slv"][1],
                   j_lugs["slv"][0], GND_Y, stroke=GND_COL, sw=1.2)
        s += _gnd(j_lugs["slv"][0], GND_Y)

    # ── Footer ─────────────────────────────────────────────────────────────
    note = ("50s: tone shunts at vol wiper" if wiring == "50s"
            else "Modern: tone shunts at vol input lug")
    s += _text(width/2, total_h-46, note, size=8, fill=SUB, italic=True)
    # Colour legend
    lx, ly = GAP, total_h-30
    for col, label in [(HOT,"hot"),(SIG,"signal"),(TONE_C,"tone"),(GND_COL,"ground")]:
        s += _line(lx, ly, lx+16, ly, stroke=col, sw=2)
        s += _text(lx+20, ly, label, size=7, fill=SUB, anchor="start")
        lx += 62
    s += "</svg>"
    return s
