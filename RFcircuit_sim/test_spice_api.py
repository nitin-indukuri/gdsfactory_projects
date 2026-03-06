## Create a basic circuit with IHP NMOS
import os
import sys

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from gplugin.spice_gen import *


PDK_ROOT = os.environ.get("PDK_ROOT", "/home/nindukuri/IHP-Open-PDK")
PDK = os.environ.get("PDK", "ihp-sg13g2")
pdk_models = os.path.join(PDK_ROOT, PDK, "libs.tech", "ngspice", "models")
mos_lib_path = os.path.join(pdk_models, "cornerMOSlv.lib")
res_lib_path = os.path.join(pdk_models, "cornerRES.lib")
cap_lib_path = os.path.join(pdk_models, "cornerCAP.lib")
hbt_lib_path = os.path.join(pdk_models, "cornerHBT.lib")

circuit = SpiceNetlist('API_test.cir')

circuit.write_text("API Test Circuit")
circuit.write_text(".options TEMP=25")

circuit.add_spice(lib, mos_lib_path, "mos_tt")
circuit.add_spice(lib, res_lib_path, "res_typ")
circuit.add_spice(lib, cap_lib_path, "cap_typ")
circuit.add_spice(lib, hbt_lib_path, "hbt_typ")

circuit.add_spice(mosfet, 'M1', 'out', 'gate', '0', '0', 'sg13_lv_nmos', l=0.13e-6, w=0.15e-6, ng=1)
circuit.add_spice(vsource, 'supply', 'vdd', '0', 5)
# circuit.add_spice(vsource, 'in', 'gate', '0', 2.5)
circuit.add_spice(resistor, 'Rg1', 'vdd', 'gate', 1000)
circuit.add_spice(resistor, 'Rg2', 'gate', '0', 1000)
# circuit.add_spice(resistor, 'Rload', 'vdd', 'out', 1000)
circuit.add_spice(xsubckt, 'Rsload', 'rsil', 'vdd', 'out', 0, l=100e-6, w=0.5e-6)
circuit.add_spice(xsubckt, 'Cout', 'cap_cmim', 'out', 0, l=10e-6, w=10e-6)

circuit.add_spice(op)

circuit.write_text(".control")
circuit.write_text("run")
circuit.write_text("save all")
# circuit.write_text("show all")
circuit.write_text("print @n.xm1.nsg13_lv_nmos[gm]")
circuit.write_text("print @n.xm1.nsg13_lv_nmos[ids]")
circuit.write_text("print v(out)")
circuit.write_text("print v(gate)")
circuit.write_text(".endc")

circuit.write_text(".END")

# circuit.print_netlist()

circuit.save()
run_sim('API_test.cir')