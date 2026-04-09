# guitarsim

Guitar electronics passive circuit simulator with Karplus-Strong audio synthesis.
Helps guitarists understand how pickup choice, wiring, pot values, cable capacitance,
and pickup height interact — and hear the differences before buying anything.

## Running

```bash
cd server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py --server
# open http://localhost:8080
```

## Features

### Layouts
HH (Les Paul), SSS (Strat), HSS, HHS, H (single), SS (Tele).
Each layout sets the correct vol/tone routing, wiring topology, and pickup positions.

### Per-pickup controls
- **Preset** — 35+ pickups: PAF/Seth Lover/57 Classic (with measured Rd/Ld), JB, Super
  Distortion, Texas Special, CS69, Fender VN, MIJ Tele, P90s, Wide Range HB, and more
- **Volume** — per-pickup (HH) or master (SSS/HSS)
- **Tone** — per-pickup (HH) or shared tone-1/tone-2 (SSS/HSS)
- **Vol pot / Tone pot** — 250 kΩ, 500 kΩ, 1 MΩ
- **Tone cap** — 1–100 nF
- **Coil config** — Series / Parallel / Split (HB only), with measured Cp scaling
- **Inner / Outer coil tap** — split mode only; adjusts position ±10 mm
- **Polarity** — Normal / Reversed (RWRP)
- **Treble bleed** — None / Cap / RC network
- **Pickup position** — distance from bridge (mm)
- **Pickup height** — 1–8 mm from strings (inverse-square output gain + inharmonicity model)

### Global controls
- **Wiring** — 50s (tone shunts at wiper) vs modern (tone shunts at input lug)
- **Scale length**, **Cable capacitance**, **Amp input impedance**
- **Pot taper** — Audio/log (A), Linear (B)

### Pluck / Audio FR
- **String** selector (E2–E4) and **pluck position** (% from bridge)
- KS synthesis → electronics IR convolution → WAV playback
- **Audio FR** (green): dense 4000-point sweep with position comb and pluck-position
  harmonic weighting, band-averaged to chart axis — updates on each Pluck
- **Set ref** — freeze current audio FR as amber reference for A/B comparison

## Simulation model

### Electronics circuit
- **Pickup source impedance**: Rdc + jwL in parallel with self-cap Cp
- **Eddy current loss**: parallel RL shunt (Rd + jwLd) — models cover/baseplate damping.
  GuitarFreak-measured values for 57 Classic (covered/uncovered), JB, SuperDistortion, PAF
- **Volume pot**: two-stage model — wiper voltage preserves resonant peak at all vol settings.
  50s wiring: tone cap shunts at wiper. Modern: tone cap shunts at input lug.
- **Tone**: RC shunt admittance, series resistance from wiper position
- **Multi-pickup (chart)**: sum of individual channel gains, no comb, polarity ignored
- **Multi-pickup (audio)**: full phasor sum with position comb and polarity — produces quack
- **Coil scaling from GuitarFreak measurements**:
  - Parallel: rdc/4, L/4, Cp×2.3
  - Split: rdc/2, L/4, Cp×1.5

### Position comb
`sin(π × f × 2d / v)` at string wave velocity `v = 2 × scale × f0`.
For the audio FR: evaluated on a 4000-point dense grid, then 1/3-octave band-averaged
to the chart axis so comb nulls are properly resolved rather than aliased.
Polarity is only applied in the audio path — on the chart it causes unphysical
cancellation because without the comb there is no frequency-dependent phase relationship.

### Pluck position weighting
Audio FR is weighted by `|sin(π × f × pluck_pos / f0)|` — the continuous-frequency
version of the triangular excitation harmonic envelope. Bridge pluck (small p) is bright;
middle pluck (p=0.5) kills all even harmonics.

### Pickup height effects
- **Output level**: `gain = (2.5 / h)²` — inverse-square law relative to 2.5 mm reference
- **Magnetic inharmonicity** (h < 2 mm): models "stratitis" / magnetic chorus from
  negative spring stiffness. Implemented as a pitch-shifted copy mixed into the KS signal.
  Calibrated: h=2.5 mm → no effect; h=1.5 mm → subtle beating; h=1.0 mm → audible chorus.

### Karplus-Strong synthesis
- Per-string T60, stiffness, and loss taper (tuned for wound vs plain strings)
- Triangular velocity excitation (1/n harmonic rolloff)
- First-order all-pass fractional delay (flat magnitude)
- Electronics IR: 4096-sample windowed zero-phase filter from sweep response
- Body EQ: mild 180 Hz and 2.5 kHz resonances

## Key physics captured

- **Two-pickup phasor cancellation** — for two pickups with position combs
  `sin(π·f·2d/v)`, partial cancellation occurs at frequencies where the combs have
  opposite sign. A notch appears near `f = v / (2·Δd)` where `Δd` is the pickup
  separation. For standard HH (neck at 170 mm, bridge at 38 mm, Δd = 132 mm) this
  falls at ~523 Hz for A2 (v = 138 m/s) and ~1568 Hz for E4 (v = 414 m/s). Depth
  is controlled by the relative vol_alpha of the two pickups.
- **Tone pot effectiveness in a two-source mix** — each pickup's tone pot shunts only
  its own source. In the combined output, the effective treble cut from pickup i's tone
  pot is weighted by that pickup's contribution to the mix at each frequency. The
  neck pickup's comb pattern emphasises different frequencies than the bridge; the
  perceptual prominence of each tone pot therefore depends on pickup position, pickup
  height, and volume setting.
- **Vol pot series resistance and tone decoupling** — at wiper position α, Rv1 = R·(1−α)
  appears in series with the pickup source. The tone cap shunt admittance must overcome
  this series impedance; at low α (low volume) the tone cap becomes less effective.
  50s wiring places the tone shunt downstream of the wiper, partially mitigating this.

## License

BSD 3-Clause — Copyright (c) 2025, Jeff Lee
