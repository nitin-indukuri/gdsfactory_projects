import gdsfactory as gf
from ihp import PDK
from ihp.cells import nmos, rfnmos, npn13G2, rsil, cmim, pmos, rppd, via_stack
from ihp.tech import LAYER

PDK.activate()

"""print(PDK.layers)
layers = vars(PDK.layers)
for name, value in layers.items():
    print(f"{name}: {value}")"""

def _inverted_layer_map(layer_map):
    """(layer, datatype) -> name from a LayerMap class. Handles kfactory LayerEnum (.layer/.datatype) and plain tuples."""
    inverted = {}
    for name in dir(layer_map):
        if name.startswith("_"):
            continue
        try:
            val = getattr(layer_map, name)
            # kfactory LayerEnum: .value is KLayout index; use .layer and .datatype for (layer, dt)
            if hasattr(val, "layer") and hasattr(val, "datatype"):
                inverted[(int(val.layer), int(val.datatype))] = name
            else:
                if hasattr(val, "value"):
                    val = val.value
                if isinstance(val, tuple) and len(val) == 2:
                    inverted[(int(val[0]), int(val[1]))] = name
        except (TypeError, ValueError, AttributeError):
            continue
    return inverted


def resolve_ihp_layer_name(layer_input):
    """
    Standardizes any IHP layer input into a clean drawing layer string.
    Works for:
      - Tuples: (8, 0) or (8, 10) -> "Metal1"
      - Strings: "Metal1pin" or "Metal1drawing" -> "Metal1"
    """
    pdk = gf.get_active_pdk()
    
    # 1. Handle Tuple inputs (GDS_Layer, GDS_Datatype)
    if isinstance(layer_input, (tuple, list)):
        # Normalize to int: port.layer_info can be float/numpy (8.0, 2.0) so (8.0, 0) != (8, 0)
        layer_int = int(layer_input[0])
        dt_int = int(layer_input[1])
        inverted_map = _inverted_layer_map(pdk.layers)
        name = inverted_map.get((layer_int, dt_int))
        # If not found (e.g. pin datatype 2), look up drawing layer (layer, 0)
        if not name:
            name = inverted_map.get((layer_int, 0), f"UNKNOWN_{layer_int}")
        layer_input = name

    # 2. Handle String inputs
    # Strip 'pin' or 'drawing' suffixes to get the core metal name
    clean_name = layer_input.replace("pin", "").replace("drawing", "")
    
    return clean_name


# 1. Load the PDK (Important: Ensure IHP PDK is in your path)
# gf.pdk.activate("ihp")


import gdsfactory as gf
import numpy as np


def auto_bridge_taper(port1, port2):
    pdk = gf.get_active_pdk()
    c = gf.Component()

    li = port1.layer_info               # KLayout LayerInfo
    layer_tuple = (int(li.layer), 0)  # e.g. (67, 2) for Metal5pin

    li2 = port2.layer_info               # KLayout LayerInfo
    layer_tuple2 = (int(li2.layer), 0)  # e.g. (67, 2) for Metal5pin

    print(layer_tuple, layer_tuple2)

    # Determine which port is lower
    lvl1 = li.layer
    lvl2 = li2.layer
    
    # Identify the 'source' (lower) and 'destination' (upper)
    if lvl1 <= lvl2:
        lower_port, upper_port = port1, port2
        lp_layer = resolve_ihp_layer_name(layer_tuple)
        up_layer = resolve_ihp_layer_name(layer_tuple2)
        is_p1_lower = True
    else:
        lower_port, upper_port = port2, port1
        lp_layer = resolve_ihp_layer_name(layer_tuple2)
        up_layer = resolve_ihp_layer_name(layer_tuple)
        is_p1_lower = False

    print(lp_layer, up_layer)

    # Same layer: just taper between the two ports, no via
    if lp_layer == up_layer:
        dist = np.linalg.norm(
            np.array(upper_port.center) - np.array(lower_port.center)
        )
        taper_ref = c << gf.components.taper(
            length=max(dist, 0.01),
            width1=lower_port.width,
            width2=upper_port.width,
            layer=lp_layer,
        )
        taper_ref.connect("o1", lower_port, allow_width_mismatch=True, allow_layer_mismatch=True, allow_type_mismatch=True)
        # Orient taper toward upper port (connect places it along lower_port direction)
        o1_center = np.array(taper_ref.ports["o1"].center)
        o2_center = np.array(taper_ref.ports["o2"].center)
        target = np.array(upper_port.center)
        angle_to_target = np.arctan2(
            target[1] - o1_center[1], target[0] - o1_center[0]
        )
        angle_current = np.arctan2(
            o2_center[1] - o1_center[1], o2_center[0] - o1_center[0]
        )
        taper_ref.rotate(
            np.degrees(angle_to_target - angle_current),
            center=taper_ref.ports["o1"].center,
        )
        return c
    else:
        # 1. Create via stack on the lower layer port
        # Size it to match the lower port's width
        vs = c << via_stack(
            bottom_layer=lp_layer,
            top_layer=up_layer,
            size=(lower_port.width, lower_port.width)
        )
        
        # 2. Place via on the lower port
        vs.connect("bottom", lower_port)
        
        # 3. Create the taper on the UPPER layer
        via_top_port = vs.ports["top"]
        dist = np.linalg.norm(np.array(via_top_port.center) - np.array(upper_port.center))
        
        taper_ref = c << gf.components.taper(
            length=dist,
            width1=via_top_port.width,
            width2=upper_port.width,
            layer=up_layer,
        )
        
        # 4. Connect taper to the via exit and the upper port
        taper_ref.connect("o1", via_top_port, allow_width_mismatch=True, allow_layer_mismatch=True, allow_type_mismatch=True)
        
        return c

def bridge_strategy(component, ports1, ports2, **kwargs):
    routes = []
    for p1, p2 in zip(ports1, ports2):
        taper_comp = auto_bridge_taper(p1, p2)
        ref = component.add_ref(taper_comp)
        
        # Connect the reference based on the original port 1
        # Since auto_bridge_taper internally handles the 'lower' logic,
        # we just need to align the reference to the first port in the pair.
        #ref.connect("o1", p1)
        routes.append(ref)
    return routes


from gdsfactory.typings import InstanceOrVInstance, LayerSpec, Route, RoutingStrategies
from gdsfactory.pdk import get_routing_strategies



def export_netlist_to_txt(netlist, filename="netlist_output.txt"):
    """Export gdsfactory netlist to a text file. Handles nets as list of {p1, p2} dicts."""
    # gdsfactory get_netlist() returns nets as a list of {"p1": "inst,port", "p2": "inst,port"}
    nets = netlist.get("nets")
    if nets is None:
        raise ValueError("netlist has no 'nets' key")
    # Accept list or tuple (iteration is the same)
    nets = list(nets) if not isinstance(nets, list) else nets

    # Build inst,port -> net label (use connection pair as label)
    inst_port_to_net = {}
    for net in nets:
        p1, p2 = net["p1"], net["p2"]
        label = f"{p1}--{p2}"
        inst_port_to_net[p1] = label
        inst_port_to_net[p2] = label

    with open(filename, "w") as f:
        f.write("--- NETLIST FOR amp ---\n")
        f.write("Generated on: 2026-02-28\n\n")

        # Section 1: Top-Level Ports (The Interface)
        f.write("EXTERNAL INTERFACE (PINS):\n")
        for port_name, net_name in netlist.get("ports", {}).items():
            f.write(f"  Port: {port_name:10} -> Connected to: {net_name}\n")
        f.write("\n")

        # Section 2: Instances and Connectivity
        f.write("INSTANCES:\n")
        for inst_name, inst_data in netlist.get("instances", {}).items():
            comp_type = inst_data.get("component", "?")
            inst_nets = []
            for key, label in inst_port_to_net.items():
                if key.startswith(f"{inst_name},"):
                    port_name = key.split(",", 1)[1]
                    inst_nets.append(f"{port_name}:{label}")
            nets_str = " | ".join(sorted(inst_nets))
            f.write(f"  Device: {inst_name:12} Type: {comp_type:15} Connections: {nets_str}\n")

        f.write("\n--- END OF NETLIST ---")


import gdsfactory as gf

def _netlist_inst_port_to_net_name(netlist):
    """Build inst,port -> net name from netlist (ports dict + nets list)."""
    inst_port_to_net = {}
    for ext_name, inst_port in (netlist.get("ports") or {}).items():
        if isinstance(inst_port, str) and "," in inst_port:
            inst_port_to_net[inst_port] = ext_name
    nets = netlist.get("nets") or []
    if not isinstance(nets, list):
        nets = list(nets)
    net_counter = [0]
    for net in nets:
        p1, p2 = net.get("p1"), net.get("p2")
        if p1 is None or p2 is None:
            continue
        n1 = inst_port_to_net.get(p1)
        n2 = inst_port_to_net.get(p2)
        if n1 is None:
            net_counter[0] += 1
            n1 = f"n{net_counter[0]}"
            inst_port_to_net[p1] = n1
        if n2 is None:
            inst_port_to_net[p2] = n1
        else:
            inst_port_to_net[p1] = n2
            inst_port_to_net[p2] = n2
    return inst_port_to_net


def generate_ngspice_from_vlsir(component, filename="ngspice_vlsir_netlist.txt"):
    netlist = component.get_netlist()
    inst_port_to_net = _netlist_inst_port_to_net_name(netlist)

    with open(filename, "w") as f:
        f.write("* RF Circuit Extracted via GDSFactory VLSIR Metadata\n")
        f.write(".lib '/path/to/ihp/sg13g2.lib' tt\n\n")

        # component.ports is a DPorts object (iterable), not a dict — use port names from iteration
        port_names = [p.name for p in component.ports if getattr(p, "name", None)]
        ports = " ".join(port_names)
        f.write(f".subckt {component.name} {ports}\n")

        for inst_name, inst_info in (netlist.get("instances") or {}).items():
            vlsir = inst_info.get("info", {}).get("vlsir", {})
            if vlsir:
                conn_list = []
                for p in vlsir.get("port_order", []):
                    key = f"{inst_name},{str(p).upper()}"
                    net = inst_port_to_net.get(key, "0")
                    conn_list.append(net)
                conns = " ".join(conn_list)
                params = " ".join([f"{k}={v}" for k, v in vlsir.get("params", {}).items()])
                f.write(f"X{inst_name} {conns} {vlsir.get('model', 'unknown')} {params}\n")
        f.write(".ends\n")



# Start from PDK/default strategies and add your custom one
new_routing_strategies: RoutingStrategies = {
    **get_routing_strategies(),  # all PDK/default strategies (route_bundle, etc.)
    "bridge_strategy": bridge_strategy,  # your custom strategy; use routing_strategy: bridge_strategy in YAML
}


# Ensure gplugin (sibling of RFcircuit_sim) is importable
import os
import sys
_gplugin_parent = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _gplugin_parent not in sys.path:
    sys.path.insert(0, _gplugin_parent)
from gplugin.yml_spice_plugin import *

if __name__ == "__main__":
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(_script_dir)
    # 2. Read the YAML file (pass custom strategies so YAML can use routing_strategy: bridge_strategy)
    component = gf.read.from_yaml("circuit.yaml", routing_strategies=new_routing_strategies)

    # 3. Show in KLayout
    component.show()

    # Usage Example:
    yaml_to_spice("divider.yaml", "divider_reconstructed.spice")

    netlist = component.get_netlist()
    export_netlist_to_txt(netlist, "yaml_circuit_netlist.txt")
    generate_ngspice_from_vlsir(component)
    component.write_gds("circuit_from_yaml.gds")

    # 4. Optional: SPICE via gplugins.vlsir (GDS -> KLayout LVS netlist -> VLSIR -> SPICE)
    # gplugins.vlsir has no netlist_to_vlsir(component). Use this pipeline instead:
    try:
        import gplugins.vlsir as gv
        from gplugins.klayout.get_netlist import get_netlist as get_klayout_netlist
        gds_path = "circuit_from_yaml.gds"
        component.write_gds(gds_path)
        kdb_netlist = get_klayout_netlist(gds_path)
        vlsir_pkg = gv.kdb_vlsir(kdb_netlist, domain="rf_amp")
        with open("my_circuit.txt", "w") as f:
            gv.export_netlist(vlsir_pkg, fmt="spice", dest=f)
        print("Wrote my_circuit.spice via gplugins.vlsir")
    except Exception as e:
        print(f"gplugins.vlsir SPICE export skipped: {e}")