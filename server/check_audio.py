from simulation import PickupParams, sweep
from audio import render_strum
import numpy as np

pu = PickupParams(rdc=7500, L=3.8, Cp=120e-12)
resp = sweep([pu], [0], 500e-12, "none", "50s")
print(f"Response: {len(resp)} points, peak at {round(float(sweep.__module__ and 0 or 0))} Hz")

wav = render_strum(resp)
print(f"WAV size: {len(wav)} bytes ({len(wav)/1024:.1f} kB)")
assert wav[:4] == b'RIFF', "Not a valid WAV"
assert len(wav) > 100_000, "WAV suspiciously short"
print("Audio pipeline OK")
