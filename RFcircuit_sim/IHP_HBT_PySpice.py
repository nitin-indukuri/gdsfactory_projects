import os
import subprocess
import PySpice.Logging.Logging as Logging
logger = Logging.setup_logging()

from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *
from PySpice.Spice.NgSpice.Server import SpiceServer
from PySpice.Spice.NgSpice.RawFile import RawFile
from PySpice.Spice.NgSpice.Shared import NgSpiceShared
import matplotlib.pyplot as plt
import numpy as np

NgSpiceShared.LIBRARY_PATH = "/usr/lib/x86_64-linux-gnu/libngspice.so"


PDK_ROOT = os.environ.get("PDK_ROOT", "/home/nindukuri/IHP-Open-PDK")
PDK = os.environ.get("PDK", "ihp-sg13g2")
osdi_dir = os.path.join(PDK_ROOT, PDK, "libs.tech", "ngspice", "osdi")
pdk_models = os.path.join(PDK_ROOT, PDK, "libs.tech", "ngspice", "models")
# cornerMOSlv.lib has .LIB sections and .include's sg13g2_moslv_mod.lib (defines sg13_lv_nmos)
# sg13g2_moslv_stat.lib has no .LIB sections, only .param — use cornerMOSlv.lib + mos_tt
pdk_lib_path = os.path.join(pdk_models, "cornerHBT.lib")
pdk_lib_path2 = os.path.join(pdk_models, "cornerRES.lib")
pdk_lib_path3 = os.path.join(pdk_models, "cornerCAP.lib")
# Resistor rsil uses rmod_rsil -> r3_cmc (OSDI). Run ngspice from IHP dir so .spiceinit loads OSDI.
ngspice_cwd = os.path.join(PDK_ROOT, PDK, "libs.tech", "ngspice")

def _filter_stdout(stdout):
    binary_marker = b"Binary:" + os.linesep.encode("ascii")
    idx = stdout.find(binary_marker)
    if idx < 0:
        return stdout
    header = stdout[:idx].splitlines()
    variables_line = b"Variables" + os.linesep.encode("ascii")
    # Parser expects: ... "Variables" then "No. of Data Columns " then variable data lines. Ngspice may print "Variable" (singular).
    keep = ("Circuit: ", "Doing analysis at TEMP", "Warning:", "Title: ", "Date: ", "Plotname: ", "Flags: ",
            "No. Variables: ", "No. Points: ", "Variables", "No. of Data Columns", "Binary:")
    filtered = []
    seen_variables_section = False  # have we already output "Variables" for this plot?
    for ln in header:
        try:
            s = ln.decode("utf-8").strip()
        except Exception:
            filtered.append(ln)
            continue
        is_var_data = len(s.split("\t")) >= 3 and s.split("\t")[0].strip().isdigit()
        # Singular "Variable" (or "Variable:") → emit "Variables" and do not pass the line
        if not is_var_data and s.startswith("Variable") and not s.startswith("Variables"):
            filtered.append(variables_line)
            seen_variables_section = True
            continue
        # If ngspice put "No. of Data Columns" before "Variables", emit "Variables" first
        if s.startswith("No. of Data Columns"):
            if not seen_variables_section:
                filtered.append(variables_line)
            seen_variables_section = True
            filtered.append(ln)
            continue
        if s == "Variables" or s.startswith("Variables"):
            seen_variables_section = True
        if any(s.startswith(k) for k in keep) or is_var_data:
            # Parser expects "Variables" (plural); never pass through "Variable" (singular)
            if s == "Variable" or (s.startswith("Variable") and not s.startswith("Variables")):
                filtered.append(variables_line)
            else:
                filtered.append(ln)
    # Final pass: replace any remaining "Variable" (singular) line that slipped through
    filtered = [
        variables_line if ln.rstrip() == b"Variable" else ln
        for ln in filtered
    ]
    return b"\n".join(filtered) + os.linesep.encode("ascii") + stdout[idx:]

def _patched_server_call(self, spice_input):
    env = os.environ.copy()
    env["PDK_ROOT"] = PDK_ROOT
    env["PDK"] = PDK
    process = subprocess.Popen(
        (self._spice_command, "-s"),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=ngspice_cwd, env=env,
    )
    stdout, stderr = process.communicate(str(spice_input).encode("utf-8"))
    stderr_str = stderr.decode("utf-8")
    stdout = _filter_stdout(stdout)
    self._parse_stdout(stdout)
    number_of_points = self._parse_stderr(stderr_str)
    if number_of_points is None:
        raise NameError("The number of points was not found in the standard error buffer, ngspice returned:" + os.linesep + stderr_str)
    return RawFile(stdout, number_of_points)
SpiceServer.__call__ = _patched_server_call



# Setup the plots
figure, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(20, 10))

## The NETLIST generation and simulation starts from here
circuit = Circuit('IHP SG13G2 NMOS Test')

# Load OSDI at start of netlist (r3_cmc for rsil/rmod_rsil); .spiceinit often not run when netlist from stdin
osdi_files = ["r3_cmc.osdi", "psp103.osdi", "psp103_nqs.osdi", "mosvar.osdi"]
pre_osdi_lines = [f"pre_osdi {os.path.join(osdi_dir, n)}" for n in osdi_files if os.path.isfile(os.path.join(osdi_dir, n))]
if pre_osdi_lines:
    circuit.raw_spice = "\n".join([".control"] + pre_osdi_lines + [".endc"]) + "\n"
# Convergence help for VBIC (avoids singular matrix / op failure)
# circuit.raw_spice = (circuit.raw_spice or "") + (
#     ".options gmin=1e-12 reltol=1e-2 abstol=1e-9 vntol=1e-6 cshunt=1e-12\n"
#     ".nodeset v(base)=0.7 v(collector)=2\n"
# )

circuit.lib(pdk_lib_path, 'hbt_typ')
circuit.lib(pdk_lib_path2, 'res_typ')
circuit.lib(pdk_lib_path3, 'cap_typ')


# 2. Add the IHP NMOS (sg13_lv_nmos)
# Syntax: name, subcircuit_name, drain, gate, source, bulk
# Parameters like w and l are passed as keyword arguments
# M <name> <drain node> <gate node> <source node> <bulk/substrate node>
circuit.X('M1', 'npn13G2', 'collector', 'base', circuit.gnd, circuit.gnd, Nx=1)


Vbase = circuit.V('base', '1', circuit.gnd, 1@u_V)
circuit.R('base', '1', 'base', 1@u_kΩ)
Vcollector = circuit.V('collector', '2', circuit.gnd, 0@u_V)
circuit.R('collector', '2', 'collector', 1@u_kΩ)

# Use subprocess backend (IHP env + stdout filter) so DC sweeps can converge
simulator = circuit.simulator(temperature=25, nominal_temperature=25, simulator="ngspice-subprocess")
try:
    analysis = simulator.dc(Vbase=slice(0.1, 3, 0.1))
    ax1.plot(analysis.base, u_mA(-analysis.Vbase))
    ax1.axvline(x=0.65, color="red")
    ax1.legend(("Base-Emitter Diode curve",), loc=(0.1, 0.8))
except Exception as e:
    print(f"ax1 (diode) failed: {e}")
    ax1.text(0.5, 0.5, "Simulation failed", ha="center", va="center", transform=ax1.transAxes)
ax1.grid()
ax1.set_xlabel("Vbe [V]")
ax1.set_ylabel("Ib [mA]")

print(circuit)



## The NETLIST generation and simulation starts from here
circuit2 = Circuit('IHP SG13G2 NMOS Test')

# Load OSDI at start of netlist (r3_cmc for rsil/rmod_rsil); .spiceinit often not run when netlist from stdin
osdi_files = ["r3_cmc.osdi", "psp103.osdi", "psp103_nqs.osdi", "mosvar.osdi"]
pre_osdi_lines = [f"pre_osdi {os.path.join(osdi_dir, n)}" for n in osdi_files if os.path.isfile(os.path.join(osdi_dir, n))]
if pre_osdi_lines:
    circuit2.raw_spice = "\n".join([".control"] + pre_osdi_lines + [".endc"]) + "\n"
# Convergence help for VBIC (avoids singular matrix / op failure)
# circuit2.raw_spice = (circuit2.raw_spice or "") + (
#     ".options gmin=1e-12 reltol=1e-2 abstol=1e-9 vntol=1e-6 cshunt=1e-12\n"
#     ".nodeset v(base2)=0.7 v(collector2)=2\n"
# )

circuit2.lib(pdk_lib_path, 'hbt_typ')
circuit2.lib(pdk_lib_path2, 'res_typ')
circuit2.lib(pdk_lib_path3, 'cap_typ')



Ibase = circuit2.I('base', 'base', circuit2.gnd, 10@u_uA) # take care to the orientation
# circuit2.R('rb', 'input', 'base', 1@u_kΩ)  # DC path for solver (avoids singular matrix)
Vcollector = circuit2.V('collector', '2', circuit2.gnd, 5)
circuit2.R('collector', '2', 'collector', 1@u_kΩ)
circuit2.X('M1', 'npn13G2', 'collector', 'base', circuit2.gnd, circuit2.gnd, Nx=1)

# Fixme: ngspice doesn't support multi-sweep ???
#   it works in interactive mode


ax2.grid()
# ax2.legend(('Ic(Vce, Ib)',), loc=(.5,.5))
ax2.set_xlabel('Vce [V]')
ax2.set_ylabel('Ic [mA]')
ax2.axvline(x=.2, color='red')

ax3.grid()
# ax3.legend(('beta(Vce)',), loc=(.5,.5))
ax3.set_xlabel('Vce [V]')
ax3.set_ylabel('beta')
ax3.axvline(x=.2, color='red')

# for base_current in np.arange(10, 100, 10):  # start at 10 µA (Ib=0 causes singular matrix)
# Ibase.dc_value = 10@u_uA
# base_current = 10
# print(Ibase.dc_value)
# print(base_current)
# try:
#     sim = circuit2.simulator(temperature=25, nominal_temperature=25, simulator="ngspice-subprocess")
#     analysis = sim.dc(Vcollector=slice(0.1@u_V, 5@u_V, 0.1@u_V))
#     ax2.plot(analysis.collector, u_mA(-analysis.Vcollector))
#     ax3.plot(analysis.collector, -analysis.Vcollector / float(base_current))
# except Exception as e:
#     print(f"Vce sweep at Ib={float(base_current):.0f} µA failed: {e}")

print(Ibase.dc_value)
simulation = circuit2.simulator(temperature=25, nominal_temperature=25, simulator="ngspice-subprocess")
analysis = simulation.dc(Vcollector=slice(1@u_V, 5@u_V, 0.1@u_V))
ax2.plot(analysis.collector, u_mA(-analysis.Vcollector))
ax3.plot(analysis.collector, -analysis.Vcollector / float(Ibase.dc_value))


ax4.grid()
ax4.set_xlabel('Ib [uA]')
ax4.set_ylabel('Ic [mA]')

# # Ic vs Ib: sweep base current 20–200 µA, step 20 µA
# Ib_start, Ib_stop, Ib_step = 20e-6, 200e-6, 20e-6
# try:
#     sim = circuit2.simulator(temperature=25, nominal_temperature=25, simulator="ngspice-subprocess")
#     analysis = sim.dc(Ibase=slice(Ib_start, Ib_stop, Ib_step))
#     try:
#         Ib_A = np.asarray(analysis.sweep)
#     except (AttributeError, KeyError):
#         Ib_A = np.arange(Ib_start, Ib_stop + Ib_step * 0.5, Ib_step)
#     Ib_uA = Ib_A * 1e6
#     try:
#         Ic = np.asarray(-analysis.Vcollector)
#     except Exception:
#         Ic = np.asarray(analysis["i(vcollector)"])
#     ax4.plot(Ib_uA, u_mA(Ic), "o-")
#     ax4.legend(("Ic(Ib)",), loc=(0.1, 0.8))
# except Exception as e:
#     print(f"Ic vs Ib sweep failed: {e}")
#     Ib_uA = np.arange(20, 220, 20)
#     ax4.plot(Ib_uA, np.zeros_like(Ib_uA), "x", color="gray", label="(sweep failed)")
#     ax4.legend(loc=(0.1, 0.8))


print(circuit2)

plt.tight_layout()
out_file = "pyspice_test_plots.png"
plt.savefig(out_file, dpi=150)
print(f"Figure saved to {out_file}")
plt.show()