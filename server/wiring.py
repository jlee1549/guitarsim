"""
wiring.py — SVG wiring diagram generator for guitar circuit simulator.
Light background, guitarist-readable schematic style.
"""
import math

# ── Palette ──────────────────────────────────────────────────────────────────
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
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'

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

# ── Pickup ────────────────────────────────────────────────────────────────────
def draw_pickup(x, y, w, h, pos, ptype, coil_config, coil_side, polarity, active):
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
            active_coil = (ci==0 and coil_side=="outer") or (ci==1 and coil_side=="inner")
            cc = COMP_BD if (active and active_coil) else INACTIVE
            lx = x + 8 + ci*(w/2-4)
            for i in range(3):
                cx = lx + i*loop_r*2 + loop_r
                s += _path(f"M{cx-loop_r:.1f} {loop_y:.1f} A{loop_r} {loop_r} 0 0 1 {cx+loop_r:.1f} {loop_y:.1f}", stroke=cc, sw=1.5)
        mx = x + w/2
        s += _line(mx, y+h/2-6, mx, y+h/2+14, stroke="#cccccc", sw=1, dash="3 2")
    else:
        n = 5 if ptype in ("single","p90") else 6
        total = n*loop_r*2; lx0 = x+(w-total)/2
        lc = COMP_BD if active else INACTIVE
        for i in range(n):
            cx = lx0 + i*loop_r*2 + loop_r
            s += _path(f"M{cx-loop_r:.1f} {loop_y:.1f} A{loop_r} {loop_r} 0 0 1 {cx+loop_r:.1f} {loop_y:.1f}", stroke=lc, sw=1.5)
    by = loop_y + loop_r + 3
    s += _rect(x+8, by, w-16, 5, rx=2, fill="#e8e8e8" if active else "#f0f0f0", stroke=col, sw=1)
    hot_y = y + h//2 - 6; gnd_y = y + h//2 + 10
    s += _circle(x+w, hot_y, 3.5, fill=HOT if active else INACTIVE, stroke=HOT if active else INACTIVE)
    s += _text(x+w+5, hot_y, "hot", size=7, fill=HOT if active else INACTIVE, anchor="start")
    s += _circle(x+w, gnd_y, 3.5, fill=GND_COL, stroke=GND_COL)
    s += _text(x+w+5, gnd_y, "gnd", size=7, fill=GND_COL, anchor="start")
    return s, (x+w, hot_y), (x+w, gnd_y)

# ── Pot (horizontal resistor + wiper arrow) ───────────────────────────────────
def draw_pot(x, y, w, h, label, value_pct, pot_type="vol", active=True):
    col  = COMP_BD if active else INACTIVE
    tcol = LABEL   if active else INACTIVE
    scol = SIG if pot_type=="vol" else TONE_C
    if not active: scol = INACTIVE
    s = _rect(x, y, w, h, rx=4, fill=COMP_BG, stroke=col, sw=1.2)
    s += _text(x+w/2, y+10, label, size=9, fill=tcol, weight="500")
    tx, ty, tw, th = x+8, y+h//2-4, w-16, 8
    s += _rect(tx, ty, tw, th, rx=2, fill="#eeeeee" if active else "#f5f5f5", stroke=col, sw=1)
    wx = tx + tw*(value_pct/100.0)
    ay1 = ty+th; ay2 = ty+th+12
    s += _line(wx, ay1, wx, ay2, stroke=scol, sw=1.5)
    s += _path(f"M{wx-4:.1f} {ay1+5:.1f} L{wx:.1f} {ay1:.1f} L{wx+4:.1f} {ay1+5:.1f}", stroke=scol, sw=1.5)
    s += _text(x+w/2, y+h-8, f"{int(value_pct)}%", size=8, fill=scol)
    l1 = (tx, ty+th/2); l3 = (tx+tw, ty+th/2); l2 = (wx, ay2)
    s += _circle(l1[0], l1[1], 3, fill=HOT, stroke=HOT)
    s += _circle(l3[0], l3[1], 3, fill=GND_COL, stroke=GND_COL)
    s += _circle(l2[0], l2[1], 3, fill=scol, stroke=scol)
    return s, l1, l2, l3

# ── Tone cap ──────────────────────────────────────────────────────────────────
def draw_cap(cx, y, h=36, label="22nF", active=True):
    col = COMP_BD if active else INACTIVE
    pw = 28; gap = 7
    p1y = y+h/2-gap/2-3; p2y = y+h/2+gap/2+3
    s  = _line(cx-pw/2, p1y, cx+pw/2, p1y, stroke=col, sw=3)
    s += _line(cx-pw/2, p2y, cx+pw/2, p2y, stroke=col, sw=3)
    s += _text(cx+pw/2+4, y+h/2, label, size=8, fill=col, anchor="start")
    return s, (cx, p1y), (cx, p2y)

# ── Output jack ───────────────────────────────────────────────────────────────
def draw_jack(x, y, w=60, h=44):
    s  = _rect(x, y, w, h, rx=5, fill=COMP_BG, stroke=COMP_BD, sw=1.2)
    s += _text(x+w/2, y+12, "Output", size=9, fill=LABEL, weight="500")
    s += _text(x+w/2, y+24, "jack",   size=9, fill=LABEL)
    tip = (x+w/4, y+h); slv = (x+3*w/4, y+h)
    s += _circle(tip[0], tip[1], 3, fill=SIG, stroke=SIG)
    s += _text(tip[0], tip[1]+9, "tip", size=7, fill=SIG)
    s += _circle(slv[0], slv[1], 3, fill=GND_COL, stroke=GND_COL)
    s += _text(slv[0], slv[1]+9, "slv", size=7, fill=GND_COL)
    return s, tip, slv


# ── Selector switch ───────────────────────────────────────────────────────────
def draw_selector_switch(cx, cy, n_pos, active_pos, label="selector"):
    r = 18
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
    s += _circle(inp[0], inp[1], 3, fill=HOT,  stroke=HOT)
    s += _circle(out[0], out[1], 3, fill=SIG, stroke=SIG)
    return s, inp, out

# ── Main ──────────────────────────────────────────────────────────────────────
def make_wiring_svg(pu_data, layout, wiring, active_indices, shared_vol,
                    tone_map, width=None):
    n            = len(pu_data)
    PU_W, PU_H   = 120, 80
    POT_W, POT_H = 110, 56
    ROW_GAP      = 28
    CAP_H, CAP_GAP = 36, 8
    JACK_W, JACK_H = 60, 44
    SW_R         = 18
    ROW_H        = max(PU_H, POT_H + CAP_GAP + CAP_H) + ROW_GAP
    COL_A        = 10
    COL_B        = 165
    COL_C        = 300
    JACK_X       = 420
    top_margin   = 20
    bot_margin   = 60

    n_tones = 0
    if shared_vol:
        seen_t = set()
        for i in range(n):
            tm = tone_map[i] if i < len(tone_map) else ""
            if tm and tm not in seen_t:
                seen_t.add(tm); n_tones += 1

    if width is None:
        if shared_vol:
            width = COL_C + n_tones*(POT_W+16) + JACK_W + 40
        else:
            width = JACK_X + JACK_W + 16

    total_h = top_margin + n*ROW_H + bot_margin
    GND_Y   = total_h - bot_margin + 10

    s  = f'<svg width="100%" viewBox="0 0 {width} {total_h}" xmlns="http://www.w3.org/2000/svg">'
    s += f'<rect width="100%" height="100%" fill="{BG}"/>'
    s += _text(width/2, 12, f"{layout} — {wiring} wiring", size=10, fill=SUB, italic=True)
    s += _line(COL_A, GND_Y, width-10, GND_Y, stroke=GND_COL, sw=1, dash="6 3")

    # ── Pickups ──────────────────────────────────────────────────────────
    hot_lugs = []
    for i, p in enumerate(pu_data):
        act = i in active_indices
        ry  = top_margin + i*ROW_H
        svg_pu, hot_lug, gnd_lug = draw_pickup(
            COL_A, ry, PU_W, PU_H,
            p["pos"], p["type"], p["coil_config"], p["coil_side"],
            p["polarity"], act)
        s += svg_pu
        hot_lugs.append((hot_lug[0], hot_lug[1], act))
        gx = COL_A + PU_W + 8
        s += _line(gnd_lug[0], gnd_lug[1], gx, gnd_lug[1], stroke=GND_COL, sw=1.2)
        s += _line(gx, gnd_lug[1], gx, GND_Y, stroke=GND_COL, sw=1.2)
        s += _gnd(gx, GND_Y)

    # ── SHARED-VOL (SSS / HSS / HHS / SS-shared) ─────────────────────────
    if shared_vol:
        bus_x = COL_B - SW_R*2 - 16
        sw_cx = COL_B - SW_R - 6
        ys    = [hl[1] for hl in hot_lugs]

        # Hot wires → vertical bus
        for (hx, hy, act) in hot_lugs:
            s += _line(hx, hy, bus_x, hy,
                       stroke=HOT if act else INACTIVE, sw=WIRE_W,
                       dash="" if act else "4 2")
        if len(ys) > 1:
            s += _line(bus_x, min(ys), bus_x, max(ys), stroke=HOT, sw=WIRE_W)
            for hy in ys[1:]:
                s += _dot(bus_x, hy, fill=HOT)

        # Selector switch
        sw_cy  = top_margin + (n*ROW_H)/2
        n_pos  = 5 if n >= 3 else 3
        mid_ai = sorted(active_indices)[len(active_indices)//2] if active_indices else 0
        sw_pos = round(mid_ai*(n_pos-1)/max(n-1, 1))
        svg_sw, sw_inp, sw_out = draw_selector_switch(sw_cx, sw_cy, n_pos, sw_pos)
        s += svg_sw
        s += _line(bus_x, sw_cy, sw_inp[0], sw_inp[1], stroke=HOT, sw=WIRE_W)
        if min(ys) < sw_cy - 2:
            s += _line(bus_x, min(ys), bus_x, sw_cy, stroke=HOT, sw=WIRE_W)

        # Master vol
        vol_pot_y = sw_cy - POT_H/2
        vol_pct   = pu_data[0].get("vol_pct", 100)
        svg_v, vl1, vl2, vl3 = draw_pot(COL_B, vol_pot_y, POT_W, POT_H,
                                          "Master vol", vol_pct, "vol", True)
        s += svg_v
        s += _line(sw_out[0], sw_out[1], vl1[0], vl1[1], stroke=SIG, sw=WIRE_W)
        s += _line(vl3[0], vl3[1], vl3[0], GND_Y, stroke=GND_COL, sw=1.2)
        s += _gnd(vl3[0], GND_Y)

        # Tone pots + caps
        seen = {}; tone_slots = []
        for i, p in enumerate(pu_data):
            tm = tone_map[i] if i < len(tone_map) else ""
            if tm and tm not in seen:
                seen[tm] = i; tone_slots.append((tm, p))

        src     = vl2 if wiring == "50s" else vl1
        src_col = SIG  if wiring == "50s" else HOT
        if tone_slots:
            s += _dot(src[0], src[1], fill=src_col)

        for ti, (tname, p) in enumerate(tone_slots):
            tone_pct = p.get("tone_pct", 100)
            cap_nf   = int(p.get("Ctone_nf", 22))
            tcx      = COL_C + ti*(POT_W+16)
            svg_t, tl1, tl2, tl3 = draw_pot(tcx, vol_pot_y, POT_W, POT_H,
                                              tname.replace("tone","Tone "),
                                              tone_pct, "tone", True)
            s += svg_t
            # Horizontal bus → tone lug1
            bus_y = src[1]
            s += _line(src[0] if ti==0 else COL_C+(ti-1)*(POT_W+16)+POT_W+8,
                       bus_y, tl1[0], bus_y, stroke=src_col, sw=1.2, dash="4 2")
            if abs(bus_y - tl1[1]) > 1:
                s += _line(tl1[0], bus_y, tl1[0], tl1[1],
                           stroke=src_col, sw=1.2, dash="4 2")
            s += _line(tl3[0], tl3[1], tl3[0], GND_Y, stroke=GND_COL, sw=1.2)
            s += _gnd(tl3[0], GND_Y)
            cap_y = vol_pot_y + POT_H + CAP_GAP
            svg_cap, cap_top, cap_bot = draw_cap(tl2[0], cap_y, h=CAP_H,
                                                  label=f"{cap_nf}nF", active=True)
            s += svg_cap
            s += _line(tl2[0], tl2[1], cap_top[0], cap_top[1], stroke=TONE_C, sw=1.2)
            s += _line(cap_bot[0], cap_bot[1], cap_bot[0], GND_Y, stroke=GND_COL, sw=1.2)
            s += _gnd(cap_bot[0], GND_Y)

        # Vol wiper → jack
        last_tcx   = COL_C + max(0, len(tone_slots)-1)*(POT_W+16)
        jack_x_pos = last_tcx + POT_W + 24
        jack_y     = vol_pot_y + (POT_H-JACK_H)//2
        s += _line(vl2[0], vl2[1], jack_x_pos, vl2[1], stroke=SIG, sw=WIRE_W)
        svg_jack, tip, slv = draw_jack(jack_x_pos, jack_y, JACK_W, JACK_H)
        s += svg_jack
        s += _line(jack_x_pos, vl2[1], tip[0], tip[1], stroke=SIG, sw=WIRE_W)
        s += _line(slv[0], slv[1], slv[0], GND_Y, stroke=GND_COL, sw=1.2)
        s += _gnd(slv[0], GND_Y)

    # ── INDEPENDENT-VOL (HH / SS / PP / H) ───────────────────────────────
    else:
        sig_bus_x = JACK_X - 12

        for i, p in enumerate(pu_data):
            act      = i in active_indices
            ry       = top_margin + i*ROW_H
            pot_y    = ry + max(0, (PU_H-POT_H)//2)
            vol_pct  = p.get("vol_pct", 100)
            tone_pct = p.get("tone_pct", 100)
            cap_nf   = int(p.get("Ctone_nf", 22))
            has_tone = p.get("has_tone", True)
            hx, hy   = hot_lugs[i][0], hot_lugs[i][1]

            svg_v, vl1, vl2, vl3 = draw_pot(COL_B, pot_y, POT_W, POT_H,
                                              "Vol", vol_pct, "vol", act)
            s += svg_v

            # Hot → vol lug1 (horizontal then drop if needed)
            s += _line(hx, hy, vl1[0], hy,
                       stroke=HOT if act else INACTIVE, sw=WIRE_W,
                       dash="" if act else "4 2")
            if abs(hy - vl1[1]) > 1:
                s += _line(vl1[0], hy, vl1[0], vl1[1],
                           stroke=HOT if act else INACTIVE, sw=WIRE_W)

            s += _line(vl3[0], vl3[1], vl3[0], GND_Y, stroke=GND_COL, sw=1.2)
            s += _gnd(vl3[0], GND_Y)

            if has_tone:
                svg_t, tl1, tl2, tl3 = draw_pot(COL_C, pot_y, POT_W, POT_H,
                                                  "Tone", tone_pct, "tone", act)
                s += svg_t

                src     = vl2 if wiring == "50s" else vl1
                src_col = SIG  if wiring == "50s" else HOT
                bus_y   = src[1]
                # Horizontal bus → tone lug1
                s += _line(src[0], bus_y, tl1[0], bus_y,
                           stroke=src_col, sw=1.2, dash="4 2")
                if abs(bus_y - tl1[1]) > 1:
                    s += _line(tl1[0], bus_y, tl1[0], tl1[1],
                               stroke=src_col, sw=1.2, dash="4 2")
                s += _dot(src[0], src[1], fill=src_col)

                s += _line(tl3[0], tl3[1], tl3[0], GND_Y, stroke=GND_COL, sw=1.2)
                s += _gnd(tl3[0], GND_Y)

                cap_y = pot_y + POT_H + CAP_GAP
                svg_cap, cap_top, cap_bot = draw_cap(tl2[0], cap_y, h=CAP_H,
                                                      label=f"{cap_nf}nF", active=act)
                s += svg_cap
                s += _line(tl2[0], tl2[1], cap_top[0], cap_top[1],
                           stroke=TONE_C if act else INACTIVE, sw=1.2)
                s += _line(cap_bot[0], cap_bot[1], cap_bot[0], GND_Y,
                           stroke=GND_COL, sw=1.2)
                s += _gnd(cap_bot[0], GND_Y)

            # Vol wiper → signal bus
            s += _line(vl2[0], vl2[1], sig_bus_x, vl2[1],
                       stroke=SIG if act else INACTIVE, sw=WIRE_W,
                       dash="" if act else "4 2")

        # Vertical signal bus + jack
        wiper_ys = [top_margin + i*ROW_H + max(0,(PU_H-POT_H)//2) + POT_H + 14
                    for i in range(n)]
        if len(wiper_ys) > 1:
            s += _line(sig_bus_x, min(wiper_ys), sig_bus_x, max(wiper_ys),
                       stroke=SIG, sw=WIRE_W)
        mid_y  = (min(wiper_ys)+max(wiper_ys))/2
        jack_y = mid_y - JACK_H/2
        s += _line(sig_bus_x, mid_y, JACK_X, mid_y, stroke=SIG, sw=WIRE_W)
        svg_jack, tip, slv = draw_jack(JACK_X, jack_y, JACK_W, JACK_H)
        s += svg_jack
        s += _line(JACK_X, mid_y, tip[0], tip[1], stroke=SIG, sw=WIRE_W)
        s += _line(slv[0], slv[1], slv[0], GND_Y, stroke=GND_COL, sw=1.2)
        s += _gnd(slv[0], GND_Y)

    note = ("50s: tone shunts at vol wiper" if wiring=="50s"
            else "Modern: tone shunts at vol input lug")
    s += _text(width/2, total_h-10, note, size=8, fill=SUB, italic=True)
    s += "</svg>"
    return s
