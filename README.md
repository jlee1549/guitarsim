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

- **HH blend cancellation** — partial RWRP cancellation between pickups creates a notch
  at `f = v / (2 × pickup_separation)`. For standard HH (132 mm separation), this falls
  around 500 Hz on A2, 1.6 kHz on E4 — the "wah" vowel formant guitarists chase by
  blending pickups with the neck volume slightly rolled back.
- **Tone asymmetry in mix** — neck pickup tone has more audible effect in the mix than
  bridge tone at equal settings, because the neck comb emphasizes frequencies (500 Hz,
  3 kHz) where the ear is more sensitive. At low neck volume, bridge tone becomes more
  dominant — models the real-world observation that neck height and volume affect which
  tone pot has more leverage.
- **Treble loss on volume rollback** — the vol pot series resistance (Rv1) at mid-position
  decouples the tone cap from the signal; 50s wiring reduces this effect.

## License

BSD 3-Clause — Copyright (c) 2025, Jeff Lee
