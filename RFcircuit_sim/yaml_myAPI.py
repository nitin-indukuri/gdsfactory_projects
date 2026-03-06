"""
Convert a gdsfactory-style YAML netlist (instances, connections, ports) into a SPICE netlist
using the gplugin.spice_gen API (SpiceNetlist, xsubckt, lib, etc.).
"""
import os
import sys

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

import yaml
from gplugin.spice_gen import SpiceNetlist, xsubckt, lib


# Default port order for common component types (used when building node list for X elements)
COMPONENT_PORTS = {
    "bend_circular": ["o1", "o2"],
    "mmi1x2": ["o1", "o2", "o3"],
    "mmi2x2": ["o1", "o2", "o3", "o4"],
    "straight": ["o1", "o2"],
    "rsil": ["P1", "P2"],
    "cmim": ["PLUS", "MINUS"],
    "npn13G2": ["B", "C", "E"],
}


def _parse_connection(s):
    """Parse 'inst,port' -> (inst, port)."""
    parts = s.strip().split(",", 1)
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else (s.strip(), "")


def _collect_link_pairs(connections, routes):
    """
    Collect all (left, right) link pairs from both connections and routes.
    connections: dict of conn_str -> target (str or list)
    routes: dict of route_name -> { links: { conn_str: target } or links: [ ... ] }
    Yields (left_pair, right_pair) for each connection.
    """
    # From connections section
    for conn_str, target in (connections or {}).items():
        left = _parse_connection(conn_str)
        if isinstance(target, str):
            yield left, _parse_connection(target)
        elif isinstance(target, list):
            for t in target:
                if isinstance(t, str):
                    yield left, _parse_connection(t)
    # From routes section (each route has links)
    for route_data in (routes or {}).values():
        if not isinstance(route_data, dict):
            continue
        links = route_data.get("links")
        if links is None:
            continue
        if isinstance(links, dict):
            for conn_str, target in links.items():
                left = _parse_connection(conn_str)
                if isinstance(target, str):
                    yield left, _parse_connection(target)
                elif isinstance(target, list):
                    for t in target:
                        if isinstance(t, str):
                            yield left, _parse_connection(t)
        elif isinstance(links, list):
            for item in links:
                if isinstance(item, str) and ":" in item:
                    a, b = item.split(":", 1)
                    yield _parse_connection(a), _parse_connection(b)
                elif isinstance(item, dict) and "links" in item:
                    for conn_str, target in item.get("links", {}).items():
                        left = _parse_connection(conn_str)
                        if isinstance(target, str):
                            yield left, _parse_connection(target)


def _build_nets(connections, routes, ports):
    """
    Build mapping (inst, port) -> net_name from connections, routes, and ports.
    Uses both connections and routes (each route's links) to merge (inst,port) pairs onto the same net.
    Circuit ports get their port name as net.
    """
    parent = {}

    def get_root(key):
        if key not in parent:
            parent[key] = key
        if parent[key] != key:
            parent[key] = get_root(parent[key])
        return parent[key]

    def merge(a, b):
        ra, rb = get_root(a), get_root(b)
        if ra != rb:
            parent[ra] = rb

    for left, right in _collect_link_pairs(connections, routes):
        merge(left, right)

    for port_name, loc in (ports or {}).items():
        pair = _parse_connection(loc)
        parent[pair] = pair
        root = get_root(pair)
        parent[root] = ("port", port_name)

    net_id_to_name = {}
    name_counter = [0]

    def net_name_for(key):
        root = get_root(key)
        if isinstance(root, tuple) and root[0] == "port":
            return root[1]
        if root not in net_id_to_name:
            name_counter[0] += 1
            net_id_to_name[root] = f"n{name_counter[0]}"
        return net_id_to_name[root]

    all_pairs = set()
    for left, right in _collect_link_pairs(connections, routes):
        all_pairs.add(left)
        all_pairs.add(right)
    for loc in (ports or {}).values():
        all_pairs.add(_parse_connection(loc))

    return {p: net_name_for(p) for p in all_pairs}


def yaml_to_spice_netlist(
    yaml_path_or_data,
    out_path="yamlnetlist.cir",
    title=None,
    lib_paths=None,
    component_ports=None,
):
    """
    Convert a gdsfactory YAML to a SPICE netlist using spice_gen.

    Args:
        yaml_path_or_data: Path to .yaml file or a dict (loaded YAML).
        out_path: Output .cir path.
        title: Circuit title (default from YAML 'name').
        lib_paths: Optional list of (file_path, section) to add .lib and register subckts.
        component_ports: Optional dict component_type -> [port1, port2, ...].

    Returns:
        SpiceNetlist instance (saved to out_path).
    """
    if isinstance(yaml_path_or_data, str) and os.path.isfile(yaml_path_or_data):
        with open(yaml_path_or_data, "r") as f:
            data = yaml.safe_load(f)
    elif isinstance(yaml_path_or_data, dict):
        data = yaml_path_or_data
    else:
        raise ValueError("yaml_path_or_data must be a file path or a dict")

    instances = data.get("instances", {})
    connections = data.get("connections", {})
    routes = data.get("routes", {})
    ports = data.get("ports", {})

    inst_port_to_net = _build_nets(connections, routes, ports)
    port_map = (component_ports or {}).copy()
    port_map.update(COMPONENT_PORTS)

    circuit = SpiceNetlist(out_path)
    circuit.write_text(title or data.get("name", "netlist"))
    circuit.write_text(".options TEMP=25")

    if lib_paths:
        for fp, section in lib_paths:
            circuit.add_spice(lib, fp, section)

    for inst_name, inst_data in instances.items():
        comp = inst_data.get("component", "")
        settings = inst_data.get("settings") or {}
        port_list = port_map.get(comp)
        if not port_list:
            port_list = ["o1", "o2"] if "bend" in comp or "straight" in comp else ["o1", "o2", "o3"]
        node_list = []
        for p in port_list:
            key = (inst_name, p)
            node_list.append(inst_port_to_net.get(key, f"n_{inst_name}_{p}"))
        circuit.add_spice(xsubckt, inst_name, comp, *node_list, **settings)

    circuit.write_text(".run")
    circuit.write_text(".END")
    circuit.save()
    return circuit


if __name__ == "__main__":
    # Example: convert the connections_demo YAML (inline)
    demo_yaml = """
name: connections_demo
instances:
  b:
    component: bend_circular
  mmi_long:
    component: mmi1x2
    settings:
      width_mmi: 4.5
      length_mmi: 10
  mmi_short:
    component: mmi1x2
    settings:
      width_mmi: 4.5
      length_mmi: 5
placements:
  mmi_short:
    port: o1
    x: 10
    y: 20
connections:
  b,o1: mmi_short,o2
  mmi_long,o1: b,o2
ports:
  o1: mmi_short,o1
  o2: mmi_long,o2
  o3: mmi_long,o3
"""
    with open("circuit.yaml", "r") as f:
        data = yaml.safe_load(f)

    # data = yaml.safe_load(circuit.yaml)
    circ = yaml_to_spice_netlist(data, out_path="connections_demo.cir")
    circ.print_netlist()
