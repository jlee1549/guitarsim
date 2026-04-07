"""tests/test_simulation.py — basic smoke tests"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pytest
from simulation import PickupParams, sweep, FREQS, position_comb


def make_lp():
    return PickupParams(rdc=7500, L=3.8, Cp=120e-12)


def test_sweep_shape():
    pu = make_lp()
    resp = sweep([pu], [0], 500e-12, "none", "50s")
    assert resp.shape == FREQS.shape
    assert np.all(resp >= 0)


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
    # Bridge first null ~2.6kHz, neck ~590Hz: at 500Hz bridge > neck
    assert position_comb(f, 38)[0] > position_comb(f, 170)[0]


def test_modern_loses_more_treble():
    pu = PickupParams(rdc=7500, L=3.8, Cp=120e-12, vol_knob=7)
    r_50s    = sweep([pu], [0], 500e-12, "none", "50s")
    r_modern = sweep([pu], [0], 500e-12, "none", "modern")
    hi = np.searchsorted(FREQS, 3000)
    assert np.mean(r_modern[hi:]) < np.mean(r_50s[hi:])


def test_two_pickup_valid():
    pu1 = PickupParams(rdc=7500, L=3.8, Cp=120e-12)
    pu2 = PickupParams(rdc=8500, L=4.2, Cp=140e-12)
    r = sweep([pu1, pu2], [0, 1], 500e-12, "none", "50s")
    assert r.shape == FREQS.shape
    assert np.all(np.isfinite(r))
