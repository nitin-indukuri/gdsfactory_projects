"""
Convert gdsfactory-style YAML netlist to SPICE with correct connectivity and IHP models.
Port order is read from IHP gdsfactory cells at runtime.
"""
import yaml
import pathlib
from collections import defaultdict
from functools import lru_cache

# Fallback when IHP cell cannot be loaded (e.g. PDK not active)
_FALLBACK_PORT_ORDER = ["P1", "P2"]
# SPICE prefix by component name pattern (BJT->Q, cap->C, res->R)
_SPICE_PREFIX_BY_PATTERN = (("npn", "Q"), ("cmim", "C"), ("rsil", "R"))


# Used only when cell lookup fails or returns generic 2-pin (e.g. wrong PDK)
_KNOWN_IHP_PORT_ORDER = {
    "npn13G2": ["C", "B", "E"],
    "cmim": ["PLUS", "MINUS"],
    "rsil": ["P1", "P2"],
}


@lru_cache(maxsize=64)
def _get_port_order_from_ihp_cell(comp_name: str) -> list[str]:
    """
    Return SPICE node order by loading the IHP gdsfactory cell and reading its port names.
    Uses default settings so e.g. npn13G2 is built with Nx=1. Result is cached per comp_name.
    Falls back to known IHP port order when lookup fails or returns only generic P1/P2.
    """
    try:
        import gdsfactory as gf
        from ihp import PDK
        PDK.activate()
        c = gf.get_component(comp_name)
        # DPorts: use get_all_named() for name->port then keys (insertion order), or iterate
        if hasattr(c.ports, "get_all_named"):
            named = c.ports.get_all_named()
            names = list(named.keys()) if named else []
        else:
            names = [getattr(p, "name", None) for p in c.ports]
            names = [n for n in names if n is not None]
        if names and names != _FALLBACK_PORT_ORDER:
            return names
        # Fallback: generic 2-pin or empty → use known IHP order if we know this cell
        for key, order in _KNOWN_IHP_PORT_ORDER.items():
            if key in comp_name or comp_name in key:
                return order.copy()
    except Exception:
        for key, order in _KNOWN_IHP_PORT_ORDER.items():
            if key in comp_name or comp_name in key:
                return order.copy()
    return _FALLBACK_PORT_ORDER.copy()


@lru_cache(maxsize=64)
def _get_vlsir_from_cell(comp_name: str) -> dict | None:
    """
    Load the IHP gdsfactory cell and return its c.info["vlsir"] dict, or None if missing/failed.
    Cached per comp_name.
    """
    try:
        import gdsfactory as gf
        from ihp import PDK
        PDK.activate()
        c = gf.get_component(comp_name)
        info = getattr(c, "info", None)
        if info is None:
            return None
        vlsir = info.get("vlsir") if hasattr(info, "get") else getattr(info, "vlsir", None)
        if isinstance(vlsir, dict):
            return vlsir
    except Exception:
        pass
    return None


def _emit_ihp_models_footer(comp_names_used: set[str]) -> list[str]:
    """
    Build SPICE footer from IHP cell VLSIR metadata: .lib lines and model comments.
    comp_names_used: set of component type names that appear in the netlist.
    """
    lines = ["* IHP models from cell VLSIR metadata"]
    lib_to_models = defaultdict(list)
    for comp_name in sorted(comp_names_used):
        vlsir = _get_vlsir_from_cell(comp_name)
        if not vlsir:
            lines.append(f"* {comp_name}: (no VLSIR metadata)")
            continue
        model = vlsir.get("model") or comp_name
        spice_type = vlsir.get("spice_type", "")
        spice_lib = vlsir.get("spice_lib")
        if spice_lib:
            lib_to_models[spice_lib].append(f"{model} ({spice_type})")
        else:
            lines.append(f"* {comp_name}: model={model} spice_type={spice_type} (no .lib)")
    for lib in sorted(lib_to_models.keys()):
        models_str = ", ".join(lib_to_models[lib])
        lines.append(f".lib '{lib}'  ; {models_str}")
    lines.append(".end")
    return lines


def _build_inst_port_to_net(ports: dict, routes: dict) -> dict[str, str]:
    """
    Build mapping: "inst,port" -> net_name using ports (ext pin -> inst,port) and
    routes (links: inst1,port1: inst2,port2). External names (RFIN, GND, ...) become net names;
    internal nets get n1, n2, ...
    """
    inst_port_to_net = {}
    # Top-level ports: external pin name is the net at that inst,port
    for ext_name, inst_port in (ports or {}).items():
        if isinstance(inst_port, str) and "," in inst_port:
            inst_port_to_net[inst_port.strip()] = ext_name

    # Routes: each link connects two inst,ports to the same net
    net_counter = [0]

    def assign_net(*keys: str) -> str:
        for k in keys:
            if k in inst_port_to_net:
                return inst_port_to_net[k]
        net_counter[0] += 1
        n = f"n{net_counter[0]}"
        for k in keys:
            inst_port_to_net[k] = n
        return n

    for bundle in (routes or {}).values():
        links = bundle.get("links") or {}
        if isinstance(links, dict):
            for left, right in links.items():
                left = left.strip() if isinstance(left, str) else str(left)
                right = right.strip() if isinstance(right, str) else str(right)
                n1 = inst_port_to_net.get(left)
                n2 = inst_port_to_net.get(right)
                if n1 and n2:
                    if n1 != n2:
                        # Merge: everything that was on n2 is now on n1
                        for k in list(inst_port_to_net.keys()):
                            if inst_port_to_net[k] == n2:
                                inst_port_to_net[k] = n1
                elif n1:
                    inst_port_to_net[right] = n1
                elif n2:
                    inst_port_to_net[left] = n2
                else:
                    n = assign_net(left, right)
                    inst_port_to_net[left] = inst_port_to_net[right] = n

    return inst_port_to_net


def _get_port_order(comp_name: str) -> list[str]:
    """Return SPICE node order from IHP gdsfactory cell port names."""
    return _get_port_order_from_ihp_cell(comp_name)


def _resolve_instance_nets(
    inst_name: str,
    comp_name: str,
    ports: dict,
    routes: dict,
    inst_port_to_net: dict,
) -> list[str]:
    """Return net names in SPICE port order for this instance."""
    order = _get_port_order(comp_name)
    nets = []
    for p in order:
        key = f"{inst_name},{p}"
        net = inst_port_to_net.get(key, "0")
        nets.append(net)
    return nets


def _spice_prefix(comp_name: str) -> str:
    """Infer SPICE prefix (Q/R/C) from component name; default X for subcircuits."""
    for pattern, prefix in _SPICE_PREFIX_BY_PATTERN:
        if pattern in comp_name.lower():
            return prefix
    return "X"


def _spice_line(
    inst_name: str,
    comp_name: str,
    nets: list[str],
    settings: dict,
    model_name: str | None = None,
) -> str:
    """Format one SPICE line; model_name from VLSIR when provided, else comp_name."""
    prefix = _spice_prefix(comp_name)
    param_str = " ".join([f"{k}={v}" for k, v in (settings or {}).items()])
    node_str = " ".join(nets)
    model = model_name if model_name else comp_name
    return f"{prefix}{inst_name} {node_str} {model} {param_str}".strip()


def yaml_to_spice(yaml_path: str, output_path: str = None) -> str:
    """Converts a gdsfactory-style YAML netlist to SPICE with real connectivity and IHP models."""
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)

    netlists = data if isinstance(data, list) else [data]
    spice_lines = ["* Generated from gdsfactory YAML", ""]

    for netlist in netlists:
        name = netlist.get("name", "TOP")
        instances = netlist.get("instances", {})
        placements = netlist.get("placements", {})
        ports = netlist.get("ports", {})
        routes = netlist.get("routes", {})

        inst_port_to_net = _build_inst_port_to_net(ports, routes)

        is_top = name.upper() == "TOP"
        if not is_top:
            port_names = " ".join(ports.keys())
            spice_lines.append(f".subckt {name} {port_names}")

        for inst_name, info in instances.items():
            comp_name = info.get("component", "")
            settings = info.get("settings", {})

            nets = _resolve_instance_nets(
                inst_name, comp_name, ports, routes, inst_port_to_net
            )
            vlsir = _get_vlsir_from_cell(comp_name)
            model_name = vlsir.get("model") if vlsir else None
            line = _spice_line(inst_name, comp_name, nets, settings, model_name=model_name)

            if inst_name in placements:
                p = placements[inst_name]
                spice_lines.append(f"* sch_x={p.get('x')} sch_y={p.get('y')} sch_r={p.get('rotation')}")
            spice_lines.append(line)

        if not is_top:
            spice_lines.append(".ends")
        spice_lines.append("")

    # Collect unique component types and emit footer from their VLSIR metadata
    comp_names_used = set()
    for netlist in netlists:
        for info in (netlist.get("instances") or {}).values():
            comp = info.get("component")
            if comp:
                comp_names_used.add(comp)
    spice_lines.extend(_emit_ihp_models_footer(comp_names_used))

    full_spice = "\n".join(spice_lines)
    if output_path:
        pathlib.Path(output_path).write_text(full_spice)
        print(f"LOG: Wrote SPICE netlist to {output_path}")
    return full_spice
