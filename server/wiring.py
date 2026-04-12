"""
wiring.py — SVG wiring diagram generator for guitar circuit simulator.

Guitarist-readable schematic on a light background.
Conventions (matching Seymour Duncan / Gibson style):
  - White/light grey background
  - Black wires for hot signal
  - Black/dark wires for ground  
  - Coloured highlights for tone branch
  - Components: white fill, black border, clear labels
"""
import math

# ── Palette (light background) ──────────────────────────────────────────────
BG       = "#f8f8f6"
HOT      = "#1a1a1a"      # hot wire — black
GND_COL  = "#888888"      # ground wire — grey
SIG      = "#1a5fa8"      # signal after vol wiper — blue
TONE_C   = "#c04020"      # tone branch — red
COMP_BG  = "#ffffff"      # component fill
COMP_BD  = "#333333"      # component border
LABEL    = "#222222"      # main labels
SUB      = "#666666"      # sub-labels / values
INACTIVE = "#cccccc"      # greyed-out inactive components
WIRE_W   = 1.8            # wire stroke width

def _line(x1, y1, x2, y2, stroke=HOT, sw=WIRE_W, dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{stroke}" stroke-width="{sw}"{d} fill="none"/>')

def _rect(x, y, w, h, rx=4, fill=COMP_BG, stroke=COMP_BD, sw=1):
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

def _text(x, y, txt, size=10, fill=LABEL, anchor="middle", weight="normal", italic=False):
    style = "font-style:italic;" if italic else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" '
            f'text-anchor="{anchor}" font-weight="{weight}" font-style="{style}" '
            f'font-family="system-ui" dominant-baseline="central">{txt}</text>')

def _circle(x, y, r, fill=COMP_BG, stroke=COMP_BD, sw=1):
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'

def _path(d, stroke=COMP_BD, sw=1.5, fill="none"):
    return f'<path d="{d}" stroke="{stroke}" stroke-width="{sw}" fill="{fill}"/>'

def _gnd(x, y):
    """Standard ground symbol."""
    s  = _line(x, y, x, y+6, stroke=GND_COL, sw=1.5)
    s += _line(x-7, y+6, x+7, y+6, stroke=GND_COL, sw=1.5)
    s += _line(x-5, y+10, x+5, y+10, stroke=GND_COL, sw=1.2)
    s += _line(x-3, y+14, x+3, y+14, stroke=GND_COL, sw=1)
    return s

def _dot(x, y, r=3, fill=HOT):
    """Junction dot on wire."""
    return _circle(x, y, r, fill=fill, stroke=fill, sw=0)

# ── Component: pickup ────────────────────────────────────────────────────────
def draw_pickup(x, y, w, h, pos, ptype, coil_config, coil_side, polarity, active):
    """Pickup as a labelled rectangle with coil loops inside."""
    col  = COMP_BD if active else INACTIVE
    tcol = LABEL   if active else INACTIVE
    s = _rect(x, y, w, h, rx=5, fill=COMP_BG, stroke=col, sw=1.5)

    # Type label (top)
    type_str = {"humbucker":"Humbucker","single":"Single coil","p90":"P-90"}.get(ptype, ptype)
    s += _text(x + w/2, y + 12, type_str, size=9, fill=tcol, weight="500")

    # Pos label
    pol_mark = " [R]" if polarity == -1 else ""
    s += _text(x + w/2, y + 24, pos + pol_mark, size=8, fill=SUB if active else INACTIVE)

    # Coil loops
    loop_y = y + h/2 + 4
    loop_r = 6

    if ptype == "humbucker" and coil_config == "split":
        # Two coil banks, inactive one greyed
        for ci in range(2):
            active_coil = (ci == 0 and coil_side == "outer") or \
                          (ci == 1 and coil_side == "inner")
            cc = COMP_BD if (active and active_coil) else INACTIVE
            lx = x + 8 + ci * (w/2 - 4)
            n = 3
            for i in range(n):
                cx = lx + i * loop_r * 2 + loop_r
                s += _path(f"M{cx-loop_r:.1f} {loop_y:.1f} A{loop_r} {loop_r} 0 0 1 {cx+loop_r:.1f} {loop_y:.1f}",
                           stroke=cc, sw=1.5)
        # Centre divider
        mx = x + w/2
        s += _line(mx, y+h/2-6, mx, y+h/2+14, stroke="#cccccc", sw=1, dash="3 2")
    else:
        n = 5 if ptype in ("single","p90") else 6
        total = n * loop_r * 2
        lx0 = x + (w - total) / 2
        lc = COMP_BD if active else INACTIVE
        for i in range(n):
            cx = lx0 + i * loop_r * 2 + loop_r
            s += _path(f"M{cx-loop_r:.1f} {loop_y:.1f} A{loop_r} {loop_r} 0 0 1 {cx+loop_r:.1f} {loop_y:.1f}",
                       stroke=lc, sw=1.5)

    # Magnet bar
    by = loop_y + loop_r + 3
    bc = col
    s += _rect(x+8, by, w-16, 5, rx=2, fill="#e8e8e8" if active else "#f0f0f0",
               stroke=bc, sw=1)

    # Hot lug (right side)
    hot_y = y + h//2 - 6
    gnd_y = y + h//2 + 10
    s += _circle(x+w, hot_y, 3.5, fill=HOT if active else INACTIVE,
                 stroke=HOT if active else INACTIVE)
    s += _text(x+w+5, hot_y, "hot", size=7, fill=HOT if active else INACTIVE, anchor="start")
    s += _circle(x+w, gnd_y, 3.5, fill=GND_COL, stroke=GND_COL)
    s += _text(x+w+5, gnd_y, "gnd", size=7, fill=GND_COL, anchor="start")

    return s, (x+w, hot_y), (x+w, gnd_y)


# ── Component: pot (rectangle with slider) ────────────────────────────────────
def draw_pot(x, y, w, h, label, value_pct, pot_type="vol", active=True):
    """
    Pot drawn as a horizontal resistor body with a vertical wiper tap —
    the standard schematic symbol guitarists see on wiring diagrams.
    """
    col   = COMP_BD if active else INACTIVE
    tcol  = LABEL   if active else INACTIVE
    scol  = SIG     if pot_type == "vol" else TONE_C
    if not active: scol = INACTIVE

    s = _rect(x, y, w, h, rx=4, fill=COMP_BG, stroke=col, sw=1.2)
    s += _text(x + w/2, y + 10, label, size=9, fill=tcol, weight="500")

    # Resistance track: horizontal rect, inset
    tx, ty, tw, th = x+8, y+h//2-4, w-16, 8
    s += _rect(tx, ty, tw, th, rx=2, fill="#eeeeee" if active else "#f5f5f5",
               stroke=col, sw=1)

    # Wiper position along track
    wx = tx + tw * (value_pct / 100.0)
    # Wiper arrow: vertical line down from track, then arrowhead
    arrow_y1 = ty + th
    arrow_y2 = ty + th + 12
    s += _line(wx, arrow_y1, wx, arrow_y2, stroke=scol, sw=1.5)
    # Arrowhead (pointing up — touching the track)
    s += _path(f"M{wx-4:.1f} {arrow_y1+5:.1f} L{wx:.1f} {arrow_y1:.1f} L{wx+4:.1f} {arrow_y1+5:.1f}",
               stroke=scol, sw=1.5, fill="none")

    # Value label
    s += _text(x + w/2, y + h - 8, f"{int(value_pct)}%", size=8, fill=scol)

    # Lugs: left=lug1(in), right=lug3(gnd), bottom=lug2(wiper)
    l1 = (tx, ty + th/2)          # left end of track
    l3 = (tx + tw, ty + th/2)     # right end of track
    l2 = (wx, arrow_y2)           # wiper tap point

    s += _circle(l1[0], l1[1], 3, fill=HOT, stroke=HOT)
    s += _circle(l3[0], l3[1], 3, fill=GND_COL, stroke=GND_COL)
    s += _circle(l2[0], l2[1], 3, fill=scol, stroke=scol)

    return s, l1, l2, l3


# ── Component: tone cap ────────────────────────────────────────────────────────
def draw_cap(cx, y, h=36, label="22nF", active=True):
    """Cap as two horizontal parallel plates."""
    col  = COMP_BD if active else INACTIVE
    tcol = LABEL   if active else INACTIVE
    pw = 28  # plate width
    gap = 7  # gap between plates
    p1y = y + h/2 - gap/2 - 3
    p2y = y + h/2 + gap/2 + 3
    s  = _line(cx - pw/2, p1y, cx + pw/2, p1y, stroke=col, sw=3)
    s += _line(cx - pw/2, p2y, cx + pw/2, p2y, stroke=col, sw=3)
    s += _text(cx + pw/2 + 4, y + h/2, label, size=8, fill=tcol, anchor="start")
    # Connection points: top and bottom
    top = (cx, p1y)
    bot = (cx, p2y)
    return s, top, bot


# ── Component: output jack ─────────────────────────────────────────────────────
def draw_jack(x, y, w=60, h=44):
    """Output jack as labelled rectangle."""
    s  = _rect(x, y, w, h, rx=5, fill=COMP_BG, stroke=COMP_BD, sw=1.2)
    s += _text(x + w/2, y + 12, "Output", size=9, fill=LABEL, weight="500")
    s += _text(x + w/2, y + 24, "jack", size=9, fill=LABEL)
    tip = (x + w/4, y + h)
    slv = (x + 3*w/4, y + h)
    s += _circle(tip[0], tip[1], 3, fill=SIG, stroke=SIG)
    s += _text(tip[0], tip[1]+9, "tip", size=7, fill=SIG)
    s += _circle(slv[0], slv[1], 3, fill=GND_COL, stroke=GND_COL)
    s += _text(slv[0], slv[1]+9, "slv", size=7, fill=GND_COL)
    return s, tip, slv


# ── Main layout ───────────────────────────────────────────────────────────────
def make_wiring_svg(pu_data, layout, wiring, active_indices, shared_vol,
                    tone_map, width=None):
    """
    Generate a clean, light-background wiring diagram.

    Layout (top→bottom, left→right):
      Column A (x=10):  pickups, stacked
      Column B (x=160): vol pots, one per pickup (or shared master)
      Column C (x=310): tone pots + caps
      Far right:        output jack
    """
    n       = len(pu_data)
    PU_W, PU_H   = 120, 80
    POT_W, POT_H = 110, 56
    ROW_GAP      = 24
    COL_A        = 10
    COL_B        = 155
    COL_C        = 290
    JACK_X       = 390
    ROW_H        = max(PU_H, POT_H) + ROW_GAP
    CAP_H        = 36
    CAP_GAP      = 8
    JACK_W, JACK_H = 60, 44

    # Compute n_tones for shared-vol layouts (affects needed width)
    n_tones = 0
    if shared_vol:
        seen_t = set()
        for i in range(len(pu_data)):
            tm = tone_map[i] if i < len(tone_map) else ""
            if tm and tm not in seen_t:
                seen_t.add(tm)
                n_tones += 1

    # Dynamic width: shared-vol needs room for vol + n_tones tones + jack
    if width is None:
        if shared_vol:
            width = COL_C + n_tones * (POT_W + 16) + JACK_W + 40
        else:
            width = JACK_X + JACK_W + 20

    # Total height
    top_margin  = 20
    bot_margin  = 60        # room for ground symbols
    content_h   = n * ROW_H
    # Cap rows below tone pots if shared_vol (one cap column at right)
    cap_extra   = 0 if not shared_vol else (CAP_H + CAP_GAP + 10)
    total_h     = top_margin + content_h + cap_extra + JACK_H + bot_margin

    s = (f'<svg width="100%" viewBox="0 0 {width} {total_h}" '
         f'xmlns="http://www.w3.org/2000/svg">')
    s += f'<rect width="100%" height="100%" fill="{BG}"/>'

    # Title
    s += _text(width/2, 12, f"{layout} — {wiring} wiring",
               size=10, fill=SUB, italic=True)

    GND_Y = total_h - bot_margin + 10   # ground rail y

    # Ground rail (light grey dashed)
    s += _line(COL_A, GND_Y, width-10, GND_Y, stroke=GND_COL, sw=1, dash="6 3")

    # ── Draw each pickup row ──────────────────────────────────────────────
    for i, p in enumerate(pu_data):
        act = i in active_indices
        row_y = top_margin + i * ROW_H

        # Pickup
        svg_pu, hot_lug, gnd_lug = draw_pickup(
            COL_A, row_y, PU_W, PU_H,
            p["pos"], p["type"], p["coil_config"], p["coil_side"],
            p["polarity"], act
        )
        s += svg_pu

        # Ground wire from pickup
        s += _line(gnd_lug[0], gnd_lug[1], COL_A + PU_W + 10, gnd_lug[1],
                   stroke=GND_COL, sw=1.2)
        s += _line(COL_A + PU_W + 10, gnd_lug[1], COL_A + PU_W + 10, GND_Y,
                   stroke=GND_COL, sw=1.2)
        s += _gnd(COL_A + PU_W + 10, GND_Y)

        if shared_vol:
            # All hot wires route to a vertical bus at COL_B left edge
            bus_x = COL_B - 12
            s += _line(hot_lug[0], hot_lug[1], bus_x, hot_lug[1],
                       stroke=HOT if act else INACTIVE, sw=WIRE_W,
                       dash="" if act else "4 2")
        else:
            # Independent vol+tone per pickup
            vol_pct  = p.get("vol_pct", 100)
            tone_pct = p.get("tone_pct", 100)
            cap_nf   = int(p.get("Ctone_nf", 22))
            has_tone = p.get("has_tone", True)
            pot_y    = row_y + (PU_H - POT_H) // 2

            # Vol pot
            svg_v, vl1, vl2, vl3 = draw_pot(
                COL_B, pot_y, POT_W, POT_H,
                "Vol", vol_pct, "vol", act
            )
            s += svg_v

            # Hot → vol lug1
            s += _line(hot_lug[0], hot_lug[1], vl1[0], vl1[1],
                       stroke=HOT if act else INACTIVE, sw=WIRE_W,
                       dash="" if act else "4 2")

            # Vol lug3 → ground
            s += _line(vl3[0], vl3[1], vl3[0], GND_Y,
                       stroke=GND_COL, sw=1.2)
            s += _gnd(vl3[0], GND_Y)

            if has_tone:
                # Tone pot
                svg_t, tl1, tl2, tl3 = draw_pot(
                    COL_C, pot_y, POT_W, POT_H,
                    "Tone", tone_pct, "tone", act
                )
                s += svg_t

                # 50s: tone lug1 from vol wiper; modern: from vol lug1
                src = vl2 if wiring == "50s" else vl1
                src_col = SIG if wiring == "50s" else HOT
                # Route wire: src → right → tone lug1
                mid_x = COL_C + 8
                s += _line(src[0], src[1], mid_x, src[1],
                           stroke=src_col, sw=1.2, dash="4 2")
                s += _line(mid_x, src[1], mid_x, tl1[1],
                           stroke=src_col, sw=1.2, dash="4 2")
                s += _line(mid_x, tl1[1], tl1[0], tl1[1],
                           stroke=src_col, sw=1.2, dash="4 2")
                if wiring == "50s":
                    s += _dot(src[0], src[1], fill=SIG)
                else:
                    s += _dot(vl1[0], vl1[1], fill=HOT)

                # Tone lug3 → ground
                s += _line(tl3[0], tl3[1], tl3[0], GND_Y,
                           stroke=GND_COL, sw=1.2)
                s += _gnd(tl3[0], GND_Y)

                # Tone wiper → cap
                cap_y = pot_y + POT_H + CAP_GAP
                cap_cx = tl2[0]  # follow wiper x
                svg_cap, cap_top, cap_bot = draw_cap(
                    cap_cx, cap_y, h=CAP_H,
                    label=f"{cap_nf}nF", active=act
                )
                s += svg_cap
                s += _line(tl2[0], tl2[1], cap_top[0], cap_top[1],
                           stroke=TONE_C if act else INACTIVE, sw=1.2)
                s += _line(cap_bot[0], cap_bot[1], cap_bot[0], GND_Y,
                           stroke=GND_COL, sw=1.2)
                s += _gnd(cap_bot[0], GND_Y)

            # Vol wiper → right bus → jack
            jack_y = top_margin + n * ROW_H / 2 - JACK_H / 2
            bus_x  = JACK_X - 12
            s += _line(vl2[0], vl2[1], bus_x, vl2[1],
                       stroke=SIG if act else INACTIVE, sw=WIRE_W,
                       dash="" if act else "4 2")

    # ── Shared-vol: master vol + shared tones + jack ─────────────────────
    if shared_vol:
        bus_x     = COL_B - 12
        hot_ys    = [top_margin + i * ROW_H + PU_H//2 - 6 for i in range(n)]
        vol_cy    = top_margin + n * ROW_H / 2   # centre vol pot on content height
        vol_pot_y = vol_cy - POT_H / 2

        # Vertical hot bus
        s += _line(bus_x, min(hot_ys), bus_x, max(hot_ys), stroke=HOT, sw=WIRE_W)
        s += _dot(bus_x, min(hot_ys), fill=HOT)

        # Hot bus → master vol lug1
        s += _line(bus_x, vol_cy, COL_B, vol_cy, stroke=HOT, sw=WIRE_W)

        # Master vol pot
        vol_pct = pu_data[0].get("vol_pct", 100)
        svg_v, vl1, vl2, vl3 = draw_pot(COL_B, vol_pot_y, POT_W, POT_H,
                                          "Master vol", vol_pct, "vol", True)
        s += svg_v
        s += _line(vl3[0], vl3[1], vl3[0], GND_Y, stroke=GND_COL, sw=1.2)
        s += _gnd(vl3[0], GND_Y)

        # Find unique tone assignments
        seen = {}
        tone_slots = []
        for i, p in enumerate(pu_data):
            tm = tone_map[i] if i < len(tone_map) else ""
            if tm and tm not in seen:
                seen[tm] = i
                tone_slots.append((tm, p))

        for ti, (tname, p) in enumerate(tone_slots):
            tone_pct = p.get("tone_pct", 100)
            cap_nf   = int(p.get("Ctone_nf", 22))
            tcx      = COL_C + ti * (POT_W + 16)
            tone_pot_y = vol_pot_y

            svg_t, tl1, tl2, tl3 = draw_pot(tcx, tone_pot_y, POT_W, POT_H,
                                              tname.replace("tone","Tone "),
                                              tone_pct, "tone", True)
            s += svg_t

            # 50s: from vol wiper; modern: from vol lug1
            src = vl2 if wiring == "50s" else vl1
            src_col = SIG if wiring == "50s" else HOT
            mid_x = tcx + 8
            s += _line(src[0], src[1], mid_x, src[1],
                       stroke=src_col, sw=1.2, dash="4 2")
            s += _line(mid_x, src[1], mid_x, tl1[1],
                       stroke=src_col, sw=1.2, dash="4 2")
            s += _line(mid_x, tl1[1], tl1[0], tl1[1],
                       stroke=src_col, sw=1.2, dash="4 2")
            if ti == 0:
                s += _dot(src[0], src[1], fill=src_col)

            s += _line(tl3[0], tl3[1], tl3[0], GND_Y, stroke=GND_COL, sw=1.2)
            s += _gnd(tl3[0], GND_Y)

            cap_y = tone_pot_y + POT_H + CAP_GAP
            svg_cap, cap_top, cap_bot = draw_cap(tl2[0], cap_y, h=CAP_H,
                                                  label=f"{cap_nf}nF", active=True)
            s += svg_cap
            s += _line(tl2[0], tl2[1], cap_top[0], cap_top[1],
                       stroke=TONE_C, sw=1.2)
            s += _line(cap_bot[0], cap_bot[1], cap_bot[0], GND_Y,
                       stroke=GND_COL, sw=1.2)
            s += _gnd(cap_bot[0], GND_Y)

        # Vol wiper → jack
        last_tcx   = COL_C + max(0, len(tone_slots)-1) * (POT_W + 16)
        jack_x_pos = last_tcx + POT_W + 24
        jack_y     = vol_pot_y + (POT_H - JACK_H) // 2
        s += _line(vl2[0], vl2[1], jack_x_pos, vl2[1], stroke=SIG, sw=WIRE_W)
        svg_jack, tip, slv = draw_jack(jack_x_pos, jack_y, JACK_W, JACK_H)
        s += svg_jack
        s += _line(jack_x_pos, vl2[1], tip[0], tip[1], stroke=SIG, sw=WIRE_W)
        s += _line(slv[0], slv[1], slv[0], GND_Y, stroke=GND_COL, sw=1.2)
        s += _gnd(slv[0], GND_Y)

    # ── Independent-vol: output jack ─────────────────────────────────────
    if not shared_vol:
        jack_y = top_margin + n * ROW_H / 2 - JACK_H / 2
        bus_x  = JACK_X - 12
        # Vertical bus joining all wiper outputs
        ys = [top_margin + i * ROW_H + (PU_H - POT_H)//2 + POT_H//2 + 14
              for i in range(n)]
        if len(ys) > 1:
            s += _line(bus_x, min(ys), bus_x, max(ys), stroke=SIG, sw=WIRE_W)
        mid_y = (min(ys) + max(ys)) / 2
        s += _line(bus_x, mid_y, JACK_X, jack_y + JACK_H/2,
                   stroke=SIG, sw=WIRE_W)

        svg_jack, tip, slv = draw_jack(JACK_X, jack_y, JACK_W, JACK_H)
        s += svg_jack
        s += _line(JACK_X, jack_y + JACK_H/2, tip[0], tip[1],
                   stroke=SIG, sw=WIRE_W)
        s += _line(slv[0], slv[1], slv[0], GND_Y,
                   stroke=GND_COL, sw=1.2)
        s += _gnd(slv[0], GND_Y)

    # ── Wiring note ───────────────────────────────────────────────────────
    note = ("50s: tone cap taps vol wiper" if wiring == "50s"
            else "Modern: tone cap taps vol input lug")
    s += _text(width/2, total_h - 10, note, size=8, fill=SUB, italic=True)

    s += "</svg>"
    return s
