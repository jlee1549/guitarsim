import sys, numpy as np, wave, io
sys.path.insert(0, '.')
from simulation import PickupParams, sweep, FREQS
from audio import render_pluck, OPEN_STRINGS, STRING_NAMES, SAMPLE_RATE as SR

# Render E4 with PAF vs Super Distortion and compare spectral balance
def render(pickup_rdc, pickup_L, pickup_Cp, string_idx=5):
    pu = PickupParams(rdc=pickup_rdc, L=pickup_L, Cp=pickup_Cp,
                      dist_mm=38, scale_mm=628,
                      Rvol=500000, Rtone=500000, Ctone=22e-9,
                      vol_alpha=1.0, tone_alpha=1.0)
    resp = sweep([pu],[0],200e-12,'50s',R_amp=1e6,f0=OPEN_STRINGS[string_idx])
    wav_bytes = render_pluck(resp, string_idx=string_idx, pluck_pos=0.12)
    with wave.open(io.BytesIO(wav_bytes)) as wf:
        raw = wf.readframes(wf.getnframes())
    pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return pcm

# FFT and compute spectral balance
def spectral_balance(pcm, label, n_attack=int(SR*0.3)):
    seg = pcm[:n_attack] * np.hanning(n_attack)
    N = 65536
    spec = np.abs(np.fft.rfft(seg, n=N))
    freqs_fft = np.fft.rfftfreq(N, 1.0/SR)
    ref = np.max(spec)+1e-12

    print(f"\n{label}:")
    for band_name, lo, hi in [
        ("200-500 Hz (body)",   200, 500),
        ("500-1k Hz (mid)",     500, 1000),
        ("1-2k Hz (presence)",  1000, 2000),
        ("2-4k Hz (bite)",      2000, 4000),
        ("4-8k Hz (air)",       4000, 8000),
    ]:
        mask = (freqs_fft >= lo) & (freqs_fft <= hi)
        val = np.mean(spec[mask]) if mask.any() else 1e-12
        db = 20*np.log10(val/ref)
        bar = '#' * max(0, int(db + 40))
        print(f"  {band_name:20s}  {db:+5.1f} dB  {bar}")

print("E4 string spectral balance comparison:")
for name, rdc, L, Cp in [
    ("PAF bridge",      8200,  5.0,  100e-12),
    ("Super Distortion",16373, 10.0, 75e-12),
    ("Texas Special SC",6340,  2.55, 160e-12),
    ("Fender VN SC",   10400,  2.86, 38e-12),
]:
    pcm = render(rdc, L, Cp)
    spectral_balance(pcm, name)
