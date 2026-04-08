import sys, numpy as np, importlib
sys.path.insert(0, '.')
import audio; importlib.reload(audio)
from audio import ks_string, render_pluck, OPEN_STRINGS, STRING_T60, STRING_STIFFNESS, STRING_BRIGHTNESS, STRING_NAMES
from simulation import PickupParams, sweep

SR = 44100
print("Per-string harmonic content (b near 1.0):")
print(f"{'str':4s} {'b':6s}  {'H1':>6}  {'H2':>6}  {'H4':>6}  {'H8':>6}  clicks")
for si in range(6):
    f0  = OPEN_STRINGS[si]; b = STRING_BRIGHTNESS[si]
    sig = ks_string(f0, STRING_T60[si], STRING_STIFFNESS[si], 0.12, int(SR*0.3), SR, brightness=b)
    clicks = int(np.sum(np.abs(np.diff(sig)) > 0.1))
    spec = np.abs(np.fft.rfft(sig*np.hanning(len(sig))))
    fr   = np.fft.rfftfreq(len(sig), 1.0/SR)
    pk   = np.max(spec)+1e-12
    def db(f): return 20*np.log10(spec[int(np.argmin(np.abs(fr-f)))]/pk)
    print(f"  {STRING_NAMES[si]:3s}  {b:.4f}  {db(f0):+6.1f}  {db(f0*2):+6.1f}  {db(f0*4):+6.1f}  {db(f0*8):+6.1f}  {clicks}")

print("\nRendering A2 and E4 WAVs...")
pu = PickupParams(rdc=7500, L=4.5, Cp=100e-12)
resp = sweep([pu], [0], 200e-12, "50s")  # 200pF cable
for si in [1, 5]:
    wav = render_pluck(resp, string_idx=si, pluck_pos=0.12)
    p = f"/mnt/c/Users/jlee1/Documents/pluck_{STRING_NAMES[si]}_bright.wav"
    with open(p, 'wb') as f: f.write(wav)
    print(f"  wrote {p}")
