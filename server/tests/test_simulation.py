"""tests/test_simulation.py — smoke tests"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pytest
from simulation import PickupParams, sweep, FREQS, position_comb
from audio import triangular_excitation, ks_string, render_pluck


def make_lp():
    return PickupParams(rdc=7500, L=3.8, Cp=120e-12)


def test_sweep_shape():
    resp = sweep([make_lp()], [0], 500e-12, "none", "50s")
    assert resp.shape == FREQS.shape and np.all(resp >= 0)


def test_knobs_at_10_unchanged():
    pu  = make_lp()
    pu2 = PickupParams(**{**vars(pu), "vol_knob": 10, "tone_knob": 10})
    np.testing.assert_array_almost_equal(
        sweep([pu], [0], 500e-12, "none", "50s"),
        sweep([pu2], [0], 500e-12, "none", "50s"),
    )


def test_tone_rolloff():
    r_open   = sweep([PickupParams(rdc=7500, L=3.8, Cp=120e-12, tone_knob=10)],
                     [0], 500e-12, "none", "50s")
    r_rolled = sweep([PickupParams(rdc=7500, L=3.8, Cp=120e-12, tone_knob=0)],
                     [0], 500e-12, "none", "50s")
    hi = np.searchsorted(FREQS, 5000)
    assert np.mean(r_rolled[hi:]) < np.mean(r_open[hi:])


def test_volume_rolloff():
    r_full = sweep([PickupParams(rdc=7500, L=3.8, Cp=120e-12, vol_knob=10)],
                   [0], 500e-12, "none", "50s")
    r_low  = sweep([PickupParams(rdc=7500, L=3.8, Cp=120e-12, vol_knob=5)],
                   [0], 500e-12, "none", "50s")
    assert np.mean(r_low) < np.mean(r_full)


def test_position_comb():
    f = np.array([500.0, 4000.0])
    assert position_comb(f, 38)[0] > position_comb(f, 170)[0]


def test_modern_loses_more_treble():
    pu = PickupParams(rdc=7500, L=3.8, Cp=120e-12, vol_knob=7)
    r_50s    = sweep([pu], [0], 500e-12, "none", "50s")
    r_modern = sweep([pu], [0], 500e-12, "none", "modern")
    hi = np.searchsorted(FREQS, 3000)
    assert np.mean(r_modern[hi:]) < np.mean(r_50s[hi:])


def test_two_pickup_valid():
    r = sweep([PickupParams(rdc=7500, L=3.8, Cp=120e-12),
               PickupParams(rdc=8500, L=4.2, Cp=140e-12)],
              [0, 1], 500e-12, "none", "50s")
    assert r.shape == FREQS.shape and np.all(np.isfinite(r))


def test_triangular_excitation():
    dl = triangular_excitation(500, 0.12)
    assert len(dl) == 500
    assert np.max(dl) <= 1.0 + 1e-9
    assert abs(np.mean(dl)) < 0.01   # DC removed — mean near zero


def test_ks_harmonics():
    sr = 44100; f0 = 110.0
    sig   = ks_string(f0, 4.0, 0.0, 0.12, sr, sr)
    spec  = np.abs(np.fft.rfft(sig * np.hanning(len(sig))))
    freqs = np.fft.rfftfreq(len(sig), 1.0/sr)
    def at(f): return float(spec[int(np.argmin(np.abs(freqs - f)))])
    pk = np.max(spec)
    assert at(f0) > 0.01 * pk
    assert at(f0 * 2) > 0.01 * pk


def test_render_pluck_wav():
    resp = sweep([make_lp()], [0], 500e-12, "none", "50s")
    wav  = render_pluck(resp, string_idx=1)
    assert wav[:4] == b'RIFF'
    assert len(wav) > 50_000
