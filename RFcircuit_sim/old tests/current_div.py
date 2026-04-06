import PySpice.Logging.Logging as Logging
from yaml import nodes
logger = Logging.setup_logging()


from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import *


circuit = Circuit('Current Divider')


circuit.I('input', circuit.gnd, 'input', 1@u_A) # Fixme: current value
r1 = circuit.R(1, 'input', circuit.gnd, 2@u_kΩ)
# r2 = circuit.R(2, 'input', circuit.gnd, 1@u_kΩ)

# for resistance in (circuit.R1, circuit.R2):
#     resistance.minus.add_current_probe(circuit) # to get positive value

print(circuit.nodes)

simulator = circuit.simulator(temperature=25, nominal_temperature=25, simulator="ngspice-shared")
analysis = simulator.operating_point()

# Fixme: current over resistor
i_r1 = float(analysis.input) / float(r1.resistance)
# i_r2 = float(analysis.input) / float(r2.resistance)

print(f"Current through R1: {i_r1 * 1000:.2f} mA")
# print(f"Current through R2: {i_r2 * 1000:.2f} mA")

for node in analysis.branches.values():
    print('Node {}: {:5.2f} A'.format(str(node), float(node))) # Fixme: format value + unit

for node in analysis.nodes.values():
    print('Node {}: {:5.2f} V'.format(str(node), float(node)))


circuit = Circuit('Voltage Divider')

circuit.V('input', 1, circuit.gnd, 10@u_V)
circuit.R(1, 1, 2, 2@u_kΩ)
circuit.R(2, 2, circuit.gnd, 1@u_kΩ)

print(circuit.nodes)

simulator = circuit.simulator(temperature=25, nominal_temperature=25)
analysis = simulator.operating_point()

for node in analysis.nodes.values():
    print('Node {}: {:5.2f} V'.format(str(node), float(node)))