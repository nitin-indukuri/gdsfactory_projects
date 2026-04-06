## 40 GHz HBT PA-style netlist — matches ``old tests/RFampcir.cir`` (Qucs reference) using gplugin.spice_gen.
import os
import sys

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from gplugin.spice_gen import *

_script_dir = os.path.dirname(os.path.abspath(__file__))
# Generated deck with resolved PDK paths; Qucs-style reference: old tests/RFampcir.cir
_out_cir = os.path.join(_script_dir, "spicegen_test.cir")

PDK_ROOT = os.environ.get("PDK_ROOT", "/home/nindukuri/IHP-Open-PDK")
PDK = os.environ.get("PDK", "ihp-sg13g2")
pdk_models = os.path.join(PDK_ROOT, PDK, "libs.tech", "ngspice", "models")
mos_lib_path = os.path.join(pdk_models, "cornerMOSlv.lib")
res_lib_path = os.path.join(pdk_models, "cornerRES.lib")
cap_lib_path = os.path.join(pdk_models, "cornerCAP.lib")
hbt_lib_path = os.path.join(pdk_models, "cornerHBT.lib")

# Qucs/ngspice math include (override if your install differs)
_mathfunc_default = os.path.join(
    os.environ.get("QUCS_SHARE", "/foss/tools/qucs-s/share/qucs-s"),
    "xspice_cmlib",
    "include",
    "ngspice_mathfunc.inc",
)


def vsrc_port_with_sin(name, n_plus, n_minus, portnum, z0, dc, ac, vo, va, freq, td=0, theta=0):
    """Port voltage source with transient SIN(...) between ac and portnum (RFampcir / Qucs style)."""
    sin_params = " ".join(to_spice_unit(x) for x in (vo, va, freq, td, theta))
    return (
        f"{name} {n_plus} {n_minus} "
        f"dc {to_spice_unit(dc)} ac {to_spice_unit(ac)} "
        f"SIN({sin_params}) "
        f"portnum {portnum} z0 {to_spice_unit(z0)}"
    )


circuit = SpiceNetlist(_out_cir)

circuit.write_text("* 40G HBT PA output match")
#circuit.add_spice(include, _mathfunc_default)

# circuit.write_text(".SUBCKT IHP_PDK_nonlinear_components_npn13G2 gnd c b e bn Nx=1")
# circuit.write_text("X1 c b e bn npn13G2 Nx={Nx}")
# circuit.write_text(".ENDS")

circuit.add_spice(lib, hbt_lib_path, "hbt_typ")
circuit.add_spice(lib, res_lib_path, "res_wcs")
circuit.add_spice(lib, cap_lib_path, "cap_typ")
circuit.add_spice(lib, mos_lib_path, "mos_tt")

circuit.add_spice(vsource, "Pr1", "_net0", "_net1", dc=0)
circuit.write_text(
    vsrc_port_with_sin(
        "VP1", "_net2", 0, 1, 50, dc=0, ac=0.158866, vo=0, va=0.158866, freq=3e9
    )
)

circuit.add_spice(vsource, "1", "_net5", 0, dc=1.65)
circuit.add_spice(vsource, "2", "_net6", 0, dc=0.97)

# circuit.add_spice(
#     xsubckt,
#     "npn13G1",
#     "IHP_PDK_nonlinear_components_npn13G2",
#     0,
#     "_net1",
#     "_net7",
#     0,
#     0,
#     Nx=10,
# )

circuit.add_spice(hbt, name="npn13G1", c="_net1", b="_net7", e=0, bn=0, mname="npn13G2", Nx=10)
# R1: extra tc1/tc2 — resistor() has no tc kwargs; match reference line
circuit.write_text(
    f"R1 _net8 _net7 {to_spice_unit(881.5)} tc1=0.0 tc2=0.0"
)

# Qucs "F" on caps here is fF scale (32 fF, etc.)
circuit.add_spice(capacitor, "2", "_net8", "_net7", 32e-15)
circuit.write_text(
    vsrc_port_with_sin(
        "VP2", "_net4", 0, 2, 50, dc=0, ac=0.632456, vo=0, va=0.632456, freq=1e6
    )
)

circuit.add_spice(inductor, "2", "_net6", "_net8", 395.1e-12)
circuit.add_spice(capacitor, "3", "_net9", "_net8", 9.103e-15)
circuit.add_spice(capacitor, "4", "_net2", "_net9", 34.427e-15)
circuit.add_spice(capacitor, "5", "_net3", "_net4", 116.569e-15)
circuit.add_spice(inductor, "4", "_net0", "_net5", "119.152p")
circuit.add_spice(inductor, "5", "_net1", "_net3", 168.944e-12)
circuit.add_spice(inductor, "3", 0, "_net9", 293.55e-12)

circuit.write_text("")
circuit.write_text(".control")
circuit.write_text("")
circuit.add_amplifier_plots()

circuit.write_text("")
# circuit.write_text("exit")
circuit.write_text(".endc")
circuit.write_text(".END")

circuit.save()


# quiet=None: non-quiet when netlist has ``plot`` (ngspice GUI); quiet batch otherwise.
run_sim(_out_cir, cwd=_script_dir, quiet=None)

# Post-process: matplotlib PDF + PNGs — skipped if netlist has ``plot`` (use ngspice plots instead).
# Override with NO_MATPLOTLIB_PLOT=1 to always skip, or FORCE_MATPLOTLIB_PLOT=1 to always run.
_plot_file = os.path.join(_script_dir, "spice4qucs.sp1.plot")
_ngspice_plot = circuit.has_ngspice_plot_command()
if os.environ.get("FORCE_MATPLOTLIB_PLOT") == "1":
    _ngspice_plot = False
if _ngspice_plot:
    print(
        "Netlist contains a ngspice `plot` command — skipping matplotlib post-processing.",
        file=sys.stderr,
    )
elif os.environ.get("NO_MATPLOTLIB_PLOT") == "1":
    pass
elif not os.path.isfile(_plot_file):
    print(
        f"Note: {_plot_file} not found — ngspice did not produce raw data (check simulation / paths).",
        file=sys.stderr,
    )
else:
    os.environ.setdefault(
        "MPLCONFIGDIR",
        os.path.join(_script_dir, ".mplconfig"),
    )
    os.environ.setdefault("MPLBACKEND", "Agg")
    try:
        from gplugin.ngspice_raw_plot import plot_spice4qucs_matplotlib

        _r = plot_spice4qucs_matplotlib(_plot_file)
        print(
            "Matplotlib output:",
            _r["out_dir"],
            "| PDF:",
            _r["pdf_path"] if _r["pdf_path"] else "(disabled)",
        )
    except ImportError as exc:
        print(
            "Skipping matplotlib plots (need: pip install matplotlib numpy):",
            exc,
            file=sys.stderr,
        )
