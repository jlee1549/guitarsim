# guitarsim

Guitar electronics passive circuit simulator with Karplus-Strong audio synthesis.

## Structure

```
frontend/   standalone HTML/JS prototype — open index.html directly in Chrome/Firefox
server/     Python trame application (work in progress)
```

## Frontend (standalone, no server needed)

```bash
# Just open in browser
open frontend/index.html        # macOS
xdg-open frontend/index.html    # Linux
# Windows: double-click frontend/index.html
```

Features: HH/HSS/HHS/SSS/H/SS layouts, 50s vs modern wiring, per-pickup pot/cap/position
controls, pickup position comb filter, 6-string strum audio (E A D G B e).

## Server (trame app)

```bash
cd server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
# open http://localhost:8080
```

## Simulation model

- Pickup: RLC source impedance — Rdc + jwL in parallel with self-cap Cp
- Volume pot: 50s wiring (tone shunts at wiper) vs modern (tone shunts at input lug)
- Tone: RC shunt, series resistance set by pot wiper position
- Position: comb filter |sin(pi*f*2d/v)| at v=200 m/s representative wave speed
- Multi-pickup: Thevenin combination of active channel source impedances
- Audio: Karplus-Strong string → overlap-add FFT convolution with electronics IR
