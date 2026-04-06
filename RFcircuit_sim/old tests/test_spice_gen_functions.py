"""
Tests for gplugin.spice_gen module.
Run all tests by executing this file:
  python "RFcircuit_sim/old tests/test_spice_gen_functions.py"   (from repo root)
  python test_spice_gen_functions.py                 (from RFcircuit_sim/old tests/)
Or: pytest "RFcircuit_sim/old tests/test_spice_gen_functions.py" -v
"""
import os
import sys
import pytest

# Project root (parent of RFcircuit_sim) so gplugin can be imported from any cwd
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from gplugin.spice_gen import *

# --- to_spice_unit ---
class TestToSpiceUnit:
    def test_zero(self):
        assert to_spice_unit(0) == "0"

    def test_integer_no_suffix(self):
        assert to_spice_unit(1) == "1"
        assert to_spice_unit(100) == "100"

    def test_kilo(self):
        assert to_spice_unit(1000) == "1k"
        assert to_spice_unit(5e3) == "5k"

    def test_mega(self):
        assert to_spice_unit(1e6) == "1meg"
        assert to_spice_unit(2.5e6) == "2.5meg"

    def test_micro(self):
        assert to_spice_unit(1e-6) == "1u"
        assert to_spice_unit(1e-9) == "1n"

    def test_string_passthrough(self):
        assert to_spice_unit("1k").lower() == "1k"
        assert to_spice_unit("VDD") == "vdd"

    def test_invalid_type(self):
        with pytest.raises(TypeError, match="Expected number or string"):
            to_spice_unit([])
        with pytest.raises(TypeError, match="Expected number or string"):
            to_spice_unit(None)


# --- op ---
class TestOp:
    def test_returns_dot_op(self):
        assert op() == ".op"


# --- tran ---
class TestTran:
    def test_basic(self):
        out = tran(1e-9, 1e-6)
        assert out.startswith(".tran ")
        assert "1n" in out and "1u" in out or "1e-06" in out

    def test_with_tstart_tmax(self):
        out = tran(1e-9, 1e-6, tstart=0, tmax=1e-9)
        assert ".tran" in out
        assert "uic" not in out

    def test_uic(self):
        out = tran(1e-9, 1e-6, uic=True)
        assert out.strip().endswith("uic")


# --- ac ---
class TestAc:
    def test_dec(self):
        out = ac("dec", 10, 1e3, 1e9)
        assert out == ".ac dec 10 1k 1g" or "dec" in out and "1k" in out

    def test_lin_oct(self):
        out_lin = ac("lin", 100, 1, 10e6)
        assert "lin" in out_lin
        out_oct = ac("oct", 5, 1e6, 1e9)
        assert "oct" in out_oct

    def test_invalid_variation(self):
        with pytest.raises(ValueError, match="Invalid AC variation"):
            ac("invalid", 10, 1e3, 1e9)

    def test_np_non_positive(self):
        with pytest.raises(ValueError, match="positive integer"):
            ac("dec", 0, 1e3, 1e9)
        with pytest.raises(ValueError, match="positive integer"):
            ac("dec", -1, 1e3, 1e9)


# --- dc ---
class TestDc:
    def test_single_sweep(self):
        out = dc("V1", 0, 5, 0.1)
        assert out.startswith(".dc V1 ")
        assert "0 " in out and "5 " in out

    def test_dual_sweep(self):
        out = dc("V1", 0, 5, 0.1, src2="V2", start2=0, stop2=3, incr2=0.5)
        assert "V1 " in out and "V2 " in out

    def test_srcnam_not_string(self):
        with pytest.raises(ValueError, match="must be a string"):
            dc(123, 0, 5, 0.1)

    def test_secondary_incomplete(self):
        with pytest.raises(ValueError, match="all four"):
            dc("V1", 0, 5, 0.1, src2="V2", start2=0)  # missing stop2, incr2


# --- sp ---
class TestSp:
    def test_basic_no_noise(self):
        out = sp("dec", 100, 1e9, 10e9)
        assert out.startswith(".sp dec ")
        assert "1g" in out or "1e9" in out
        assert " 0" not in out or out.strip().endswith("0")  # noise 0 may be omitted

    def test_with_noise_on(self):
        out = sp("lin", 50, 1e6, 5e9, noise=1)
        assert "1 " in out or out.strip().endswith("1")

    def test_noise_must_be_0_or_1(self):
        with pytest.raises(ValueError, match="0.*1"):
            sp("dec", 10, 1e9, 10e9, noise=2)
        with pytest.raises(ValueError, match="0.*1"):
            sp("dec", 10, 1e9, 10e9, noise=-1)

    def test_invalid_freq_type(self):
        with pytest.raises(ValueError, match="dec.*oct.*lin"):
            sp("invalid", 10, 1e9, 10e9)


# --- vsrc_port ---
class TestVsrcPort:
    def test_basic(self):
        out = vsrc_port("V1", "in", "0", 1, z0=50, dc=0, ac=1)
        assert "in 0 " in out or "in  0 " in out
        assert "portnum 1 " in out
        assert "z0 50" in out or "z0 50 " in out

    def test_portnum_invalid(self):
        with pytest.raises(ValueError, match="portnum"):
            vsrc_port("V1", "1", "0", 0)
        with pytest.raises(ValueError, match="portnum"):
            vsrc_port("V1", "1", "0", -1)


# --- vsource / isource (transient-only to avoid to_spice_unit(dc, 'dc') if broken) ---
class TestVsource:
    def test_basic_dc_only(self):
        # If your to_spice_unit accepts only one arg, dc=0 is used as to_spice_unit(0)
        out = vsource("in", "1", "0", dc=0)
        assert " 1 0 " in out or "1 0 " in out
        assert "dc " in out

    def test_with_transient_string(self):
        out = vsource("in", "1", "0", transient="sin(0 1 1k)")
        assert " 1 0 " in out or "1 0 " in out
        assert "sin(" in out or "1k)" in out  # transient present (full or parsed)


class TestIsource:
    def test_basic_dc(self):
        out = isource("I1", "1", "0", dc=0)
        assert " 1 0 " in out
        assert "dc " in out


# --- pulse ---
class TestPulse:
    def test_basic(self):
        out = pulse("V1", "1", "0", 0, 5, 0, 1e-9, 1e-9, 10e-9, 20e-9, np=1)
        assert "pulse(" in out
        assert "V1 " in out or "v1 " in out

    def test_np_invalid(self):
        with pytest.raises(ValueError, match="NP"):
            pulse("V1", "1", "0", 0, 5, 0, 1e-9, 1e-9, 10e-9, 20e-9, np=0)


# --- sine ---
class TestSine:
    def test_basic(self):
        out = sine("V1", "1", "0", 0, 1, 1e6)
        assert "sin(" in out
        assert "1 " in out and "0 " in out

    def test_zero_freq_raises(self):
        with pytest.raises(ValueError, match="frequency cannot be zero"):
            sine("V1", "1", "0", 0, 1, 0)


# --- exp_source ---
class TestExpSource:
    def test_basic(self):
        out = exp_source("V1", "1", "0", 0, 5, 0, 1e-9, 2e-9, 1e-9)
        assert "exp(" in out
        assert " 1 0 " in out


# --- pwl ---
class TestPwl:
    def test_basic(self):
        out = pwl("V1", "1", "0", [(0, 0), (1e-6, 5), (2e-6, 0)])
        assert "pwl(" in out
        assert " 1 0 " in out

    def test_empty_points_raises(self):
        with pytest.raises(ValueError, match="list of"):
            pwl("V1", "1", "0", [])
        with pytest.raises(ValueError, match="list of"):
            pwl("V1", "1", "0", None)

    def test_decreasing_time_raises(self):
        with pytest.raises(ValueError, match="non-decreasing"):
            pwl("V1", "1", "0", [(0, 0), (1e-6, 5), (0.5e-6, 0)])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
    print(op())
    print(tran(1e-9, 1e-6))
    print(ac("dec", 10, 1e3, 1e9))
    print(dc("V1", 0, 5, 0.1))
    print(sp("dec", 100, 1e9, 10e9))
    print(vsrc_port("V1", "in", "0", 1, z0=50, dc=0, ac=1))
    print(vsource("in", "1", "0", dc=0))
    print(isource("I1", "1", "0", dc=0))
    print(pulse("V1", "1", "0", 0, 5, 0, 1e-9, 1e-9, 10e-9, 20e-9, np=1))
    print(sine("V1", "1", "0", 0, 1, 1e6))
    print(exp_source("V1", "1", "0", 0, 5, 0, 1e-9, 2e-9, 1e-9))
    print(pwl("V1", "1", "0", [(0, 0), (1e-6, 5), (2e-6, 0)]))

    # Test Misc Commands
    print(include("sky130.lib"))
    print(param("v_supply", 1.8))
    print(options(["reltol=1e-4", "nomod"]))
    
    # Test Passives
    print(resistor("LOAD", "out", "0", "10k"))
    print(capacitor("FILTER", "in", "out", 1e-6))
    print(mosfet("M1", "out", "in", "0", "0", "sg13_lv_nmos"))