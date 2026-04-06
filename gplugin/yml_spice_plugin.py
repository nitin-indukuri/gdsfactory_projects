"""
Convert gdsfactory-style YAML netlist to SPICE with correct connectivity and IHP models.
Port order is read from IHP gdsfactory cells at runtime.
"""
from __future__ import annotations

import copy
import os
import pathlib
import re
import yaml
from collections import defaultdict
from functools import lru_cache

# Fallback when IHP cell cannot be loaded (e.g. PDK not active)
_FALLBACK_PORT_ORDER = ["P1", "P2"]
# SPICE prefix by component name pattern (BJT->Q, cap->C, res->R)
_SPICE_PREFIX_BY_PATTERN = (
    ("npn", "Q"),
    ("cmim", "C"),
    ("rsil", "R"),
    ("inductor", "X"),
)


# Used only when cell lookup fails or returns generic 2-pin (e.g. wrong PDK)
_KNOWN_IHP_PORT_ORDER = {
    "npn13G2": ["C", "B", "E"],
    "cmim": ["PLUS", "MINUS"],
    "rsil": ["P1", "P2"],
    "inductor2": ["P1", "P2"],
    # IHP RF ``straight`` (electrical); generic gdsfactory straight uses o1/o2
    "straight": ["e1", "e2"],
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
        # YAML + IHP RF use electrical e1/e2; ``gf.get_component("straight")`` may report o1/o2
        if comp_name == "straight":
            return list(_KNOWN_IHP_PORT_ORDER["straight"])
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


def expand_connections_to_bridge_routes(data: dict) -> dict:
    """
    Copy *data* and turn each ``connections:`` entry into its own ``routes:`` bundle that uses
    ``routing_strategy: bridge_strategy`` (see :mod:`gplugin.ihp_yaml_bridge`).

    This avoids gdsfactory default routing ``width mismatch between ports`` errors when linking
    IHP devices (npn13G2, rsil, cmim, …) to ``straight`` or other waveguides.

    Existing ``routes:`` entries are preserved. The ``connections`` key is removed from the copy.
    """
    out = copy.deepcopy(data)
    conns = out.pop("connections", None) or {}
    routes = dict(out.get("routes") or {})
    idx = 0
    for left, targets in conns.items():
        if isinstance(targets, str):
            targets = [targets]
        elif not isinstance(targets, list):
            targets = [str(targets)]
        for right in targets:
            if not isinstance(right, str):
                right = str(right)
            name = f"conn_bridge_{idx}"
            idx += 1
            routes[name] = {
                "routing_strategy": "bridge_strategy",
                "links": {left.strip(): right.strip()},
            }
    out["routes"] = routes
    return out


def _inst_port_to_net_from_yaml_netlist(netlist: dict) -> dict[str, str]:
    """
    Single mapping ``"inst,PORT" -> net_name`` from ``ports``, ``routes``, and/or ``connections``.

    When ``connections`` is present, uses :func:`gplugin.yaml_myAPI._build_nets` (union-find over
    the same graph as :func:`yaml_to_spice_netlist`). Otherwise uses route *links* only.
    """
    ports = netlist.get("ports") or {}
    routes = netlist.get("routes") or {}
    connections = netlist.get("connections") or {}
    if connections:
        from gplugin.yaml_myAPI import _build_nets

        m = _build_nets(connections, routes, ports)
        return {f"{i},{p}": n for (i, p), n in m.items()}
    return _build_inst_port_to_net(ports, routes)


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
        net = inst_port_to_net.get(key)
        if net is None and comp_name and "straight" in comp_name.lower():
            # YAML uses e1/e2; some PDK/cell introspection still reports o1/o2
            alt = {"o1": "e1", "o2": "e2"}.get(str(p))
            if alt:
                net = inst_port_to_net.get(f"{inst_name},{alt}")
        if net is None:
            net = "0"
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
        inst_port_to_net = _inst_port_to_net_from_yaml_netlist(netlist)

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


def _pdk_model_lib_paths():
    """Same layout as ``40G_Amp.py`` / ``RFamp_gen.cir`` (env ``PDK_ROOT``, ``PDK``)."""
    root = os.environ.get("PDK_ROOT", "/home/nindukuri/IHP-Open-PDK")
    pdk = os.environ.get("PDK", "ihp-sg13g2")
    base = os.path.join(root, pdk, "libs.tech", "ngspice", "models")
    return {
        "hbt": (os.path.join(base, "cornerHBT.lib"), "hbt_typ"),
        "res": (os.path.join(base, "cornerRES.lib"), "res_wcs"),
        "cap": (os.path.join(base, "cornerCAP.lib"), "cap_typ"),
        "mos": (os.path.join(base, "cornerMOSlv.lib"), "mos_tt"),
    }


# Targets aligned with ``RFcircuit_sim/RFamp_gen.cir`` / ``40G_Amp.py`` (40G_amp.yaml header comments).
# Override per instance via YAML ``settings: { resistance: Ω }`` or ``capacitance: F``.
_IDEAL_RSIL_OHMS = {
    "r1": 881.5,
}
_IDEAL_CMIM_F = {
    "c2": 32e-15,
    "c3": 9.103e-15,
    "c4": 34.427e-15,
    "c5": 116.569e-15,
}


def _spice_id_drop_prefix(inst_name: str, letter: str) -> str:
    """``r1`` → ``1`` for ``R1``; ``l2`` → ``2`` for ``L2``."""
    if inst_name[:1].lower() == letter.lower() and len(inst_name) > 1:
        return inst_name[1:]
    return inst_name


def _ideal_resistance_ohms(inst_name: str, settings: dict) -> float:
    s = settings or {}
    for k in ("resistance", "r"):
        if k in s and s[k] is not None:
            return float(s[k])
    key = inst_name.lower()
    if key in _IDEAL_RSIL_OHMS:
        return _IDEAL_RSIL_OHMS[key]
    raise ValueError(
        f"ideal rsil '{inst_name}': set settings.resistance (Ω) or add to _IDEAL_RSIL_OHMS"
    )


def _ideal_capacitance_f(inst_name: str, settings: dict) -> float:
    s = settings or {}
    for k in ("capacitance", "c"):
        if k in s and s[k] is not None:
            return float(s[k])
    key = inst_name.lower()
    if key in _IDEAL_CMIM_F:
        return _IDEAL_CMIM_F[key]
    raise ValueError(
        f"ideal cmim '{inst_name}': set settings.capacitance (F) or add to _IDEAL_CMIM_F"
    )


def _ngspice_line_for_instance(
    inst_name: str,
    comp_name: str,
    nets: list[str],
    settings: dict,
    *,
    cap_subckt: str = "cap_cmim",
    ideal_passives: bool = False,
) -> str:
    """
    Map gdsfactory YAML ``component`` names to ngspice lines compatible with IHP ``.lib`` decks
    (same style as :mod:`gplugin.spice_gen` usage in ``40G_Amp.py``).

    With ``ideal_passives=True``, ``rsil`` / ``cmim`` / ``inductor2`` become :func:`~gplugin.spice_gen.resistor`,
    :func:`~gplugin.spice_gen.capacitor`, :func:`~gplugin.spice_gen.inductor` with values from YAML
    ``inductance`` or the built-in RFamp lookup tables / optional ``resistance`` / ``capacitance``.
    """
    from gplugin.spice_gen import capacitor, hbt, inductor, resistor, vsource, xsubckt

    s = dict(settings or {})
    if comp_name == "npn13G2":
        c, b, e = nets[0], nets[1], nets[2]
        nx = s.pop("Nx", s.pop("nx", None))
        kw = {**s}
        if nx is not None:
            kw["nx"] = nx
        return hbt(inst_name, c, b, e, 0, "npn13G2", **kw)
    if comp_name == "rsil":
        if ideal_passives:
            ro = _ideal_resistance_ohms(inst_name, s)
            rid = _spice_id_drop_prefix(inst_name, "r")
            return resistor(rid, nets[0], nets[1], ro)
        return xsubckt(inst_name, "rsil", nets[0], nets[1], 0, **s)
    if comp_name == "cmim":
        p, m = nets[0], nets[1]
        if ideal_passives:
            c_f = _ideal_capacitance_f(inst_name, s)
            cid = _spice_id_drop_prefix(inst_name, "c")
            return capacitor(cid, p, m, c_f)
        kw = {}
        for k, v in s.items():
            if k in ("l", "w") and v is not None:
                kw[k] = float(v) * 1e-6
            else:
                kw[k] = v
        # IHP ``cap_cmim`` is two-terminal (PLUS MINUS); do not pass a third bulk node.
        return xsubckt(inst_name, cap_subckt, p, m, **kw)
    if comp_name == "inductor2":
        l_h = s.get("inductance", 1e-9)
        if ideal_passives:
            lid = _spice_id_drop_prefix(inst_name, "l")
            return inductor(lid, nets[0], nets[1], l_h)
        # spice_gen.inductor() treats names whose .upper() starts with 'L' as already prefixed
        # (e.g. inst ``l2`` → ``L2``), which drops the ``L`` — use a safe stem.
        ind_id = f"i{inst_name}" if str(inst_name).upper().startswith("L") else inst_name
        return inductor(ind_id, nets[0], nets[1], l_h)
    if comp_name == "straight":
        return vsource(inst_name, nets[0], nets[1], dc=0)
    return _spice_line(inst_name, comp_name, nets, s, model_name=None)


def _subst_gnd_for_0(text: str) -> str:
    return re.sub(r"\bGND\b", "0", text)


def _ports_have_rf_key(ports: dict) -> bool:
    """True if any YAML port name contains ``RF_`` (case-insensitive)."""
    return any("RF_" in str(k).upper() for k in (ports or {}))


def _vdd_voltage_from_port_name(port_name: str) -> float | None:
    """
    Map ``VDD_<digits>`` to volts: suffix is hundredths (``VDD_165`` → 1.65 V, ``VDD_097`` → 0.97 V).
    Returns None if the name does not match or has no digits.
    """
    u = port_name.upper()
    if not u.startswith("VDD_"):
        return None
    suf = port_name.split("_", 1)[1] if "_" in port_name else ""
    digits = "".join(c for c in suf if c.isdigit())
    if not digits:
        return None
    return int(digits, 10) / 100.0


# Default Qucs-style RF excitations when multiple ``RF_*`` ports exist (index 0, 1, …).
_RF_PORT_DEFAULT_EXCITATIONS = (
    (0.158866, 0.158866, 3e9),
    (0.632456, 0.632456, 1e6),
)


def _append_stimulus_from_port_names(
    lines: list[str],
    ports: dict,
    *,
    z0: float = 50.0,
) -> None:
    """
    Add sources from YAML ``ports`` keys only (no extra YAML fields):

    - Names containing ``RF_`` (case-insensitive): RF port voltage source, ``dc 0``, ``ac`` + ``SIN``,
      ``portnum`` (1-based order sorted by port name), ``z0``.
    - Names starting with ``VDD_`` (case-insensitive): DC voltage to 0; voltage = integer suffix / 100
      (e.g. ``VDD_165`` → 1.65 V).
    - ``GND``: no source (reference is node ``0``; nets named GND are substituted elsewhere).
    """
    from gplugin.spice_gen import to_spice_unit

    if not ports:
        return

    lines.append("* --- stimulus from YAML port names (RF_* / VDD_*) ---")

    rf_list = [(k, v) for k, v in ports.items() if "RF_" in k.upper()]
    rf_list.sort(key=lambda kv: kv[0].upper())
    for idx, (pname, _spec) in enumerate(rf_list, start=1):
        net = _subst_gnd_for_0(str(pname))
        if idx <= len(_RF_PORT_DEFAULT_EXCITATIONS):
            ac, va, freq = _RF_PORT_DEFAULT_EXCITATIONS[idx - 1]
        else:
            ac, va, freq = 0.1, 0.1, 1e6
        vref = f"Vsrc_{pname}".replace(" ", "_")
        lines.append(
            f"{vref} {net} 0 dc 0 ac {to_spice_unit(ac)} "
            f"SIN({to_spice_unit(0)} {to_spice_unit(va)} {to_spice_unit(freq)} 0 0) "
            f"portnum {idx} z0 {to_spice_unit(z0)}"
        )

    for pname in sorted(ports.keys(), key=str.upper):
        u = pname.upper()
        if u == "GND" or "RF_" in u:
            continue
        vdc = _vdd_voltage_from_port_name(pname)
        if vdc is None:
            continue
        net = _subst_gnd_for_0(str(pname))
        vref = f"Vsrc_{pname}".replace(" ", "_")
        lines.append(f"{vref} {net} 0 dc {to_spice_unit(vdc)}")


def _append_control_amplifier_plots(lines: list[str]) -> None:
    from gplugin.spice_gen import SpiceNetlist, amplifier_plots

    sn = SpiceNetlist("__yaml_ngspice__")
    sn.write_text("")
    sn.write_text(".control")
    sn.write_text("")
    amplifier_plots(sn)
    sn.write_text("")
    sn.write_text(".endc")
    sn.write_text(".END")
    lines.extend(sn.contents)


def yaml_to_ngspice_deck(
    yaml_path: str,
    output_path: str | None = None,
    *,
    title: str | None = None,
    port_stimulus: bool | None = None,
    amplifier_control: bool | None = None,
    cap_subckt: str = "cap_cmim",
    rf_amp_stimulus: bool | None = None,
    ideal_passives: bool | None = None,
) -> str:
    """
    Build a **flat** ngspice deck from YAML: IHP ``.lib`` lines, PDK-native instances (``hbt``,
    ``xsubckt`` rsil / cap_cmim, ``L`` for inductor2, ``V`` shorts for layout ``straight``).

    With ``ideal_passives=True``, ``rsil``, ``cmim``, and ``inductor2`` are emitted as ideal ``R``/``C``/``L``
    lines via :mod:`gplugin.spice_gen` (values from RFamp reference tables for the 40G amp netlist names,
    ``settings.inductance`` for inductors, optional ``settings.resistance`` / ``settings.capacitance``).
    Corner ``.lib`` lines for RES/CAP are omitted in that mode (HBT/MOS libs remain).

    **Port-based stimulus** (no extra YAML keys required): from ``ports``,

    - Keys whose name contains ``RF_`` → Qucs-style RF sources (``portnum``, ``z0``, ``ac`` + ``SIN``).
    - Keys ``VDD_<digits>`` → DC source to ground; voltage = integer part / 100 (e.g. ``165`` → 1.65 V).
    - Net names ``GND`` are emitted as node ``0``.

    If kwargs are omitted, ``port_stimulus`` follows YAML ``ngspice.port_stimulus`` or
    ``ngspice.rf_amp_stimulus``, else **True**.

    When ``port_stimulus`` is on and any port name contains ``RF_``, the deck includes a ``.control``
    block with an S-parameter sweep (**``SP LIN …``**, same as :func:`gplugin.spice_gen.amplifier_plots`)
    plus the usual ``let`` / ``write`` / ``plot`` lines from ``amplifier_plots``. Pass
    ``amplifier_control=False`` explicitly (e.g. CLI ``--batch``) to skip that and use ``.op`` only.

    If ``amplifier_control`` is ``None`` and there are no ``RF_`` ports, it follows YAML
    ``ngspice.amplifier_control``, else **False**. An optional YAML ``ngspice:`` map can also set
    ``cap_subckt``.

    Deprecated: ``rf_amp_stimulus`` — if passed, treated as alias for ``port_stimulus``.
    """
    with open(yaml_path, "r") as f:
        raw = yaml.safe_load(f)

    netlists = raw if isinstance(raw, list) else [raw]
    if len(netlists) != 1:
        raise ValueError("yaml_to_ngspice_deck expects a single netlist dict (not a list).")
    netlist = netlists[0]
    ng = netlist.get("ngspice") or {}
    if rf_amp_stimulus is not None and port_stimulus is None:
        port_stimulus = rf_amp_stimulus
    if port_stimulus is None:
        port_stimulus = bool(ng.get("port_stimulus", ng.get("rf_amp_stimulus", True)))
    ports_map = netlist.get("ports") or {}
    if amplifier_control is None:
        if port_stimulus and _ports_have_rf_key(ports_map):
            # S-parameter analysis + amplifier_plots (SP LIN, lets, write, plot) — see RFamp_gen.cir.
            amplifier_control = True
        else:
            amplifier_control = bool(ng.get("amplifier_control", False))
    cap_subckt = str(ng.get("cap_subckt", cap_subckt))
    if ideal_passives is None:
        ideal_passives = bool(ng.get("ideal_passives", False))

    from gplugin.spice_gen import lib

    inst_port_to_net = _inst_port_to_net_from_yaml_netlist(netlist)
    instances = netlist.get("instances", {})
    placements = netlist.get("placements", {})

    lines: list[str] = []
    lines.append(f"* {title or 'ngspice deck from YAML'}")
    lines.append(f"* source yaml: {yaml_path}")
    if ideal_passives:
        lines.append("* passives: ideal R/C/L (spice_gen resistor/capacitor/inductor), no rsil/cmim subckts")
    lines.append("")
    lib_keys = ("hbt", "mos") if ideal_passives else ("hbt", "res", "cap", "mos")
    for key in lib_keys:
        fp, sec = _pdk_model_lib_paths()[key]
        lines.append(lib(fp, sec))
    lines.append("")

    for inst_name, info in instances.items():
        comp_name = info.get("component", "")
        settings = info.get("settings", {})
        nets = _resolve_instance_nets(
            inst_name, comp_name, ports_map, netlist.get("routes", {}), inst_port_to_net
        )
        if inst_name in placements:
            p = placements[inst_name]
            lines.append(f"* sch_x={p.get('x')} sch_y={p.get('y')} sch_r={p.get('rotation')}")
        lines.append(
            _subst_gnd_for_0(
                _ngspice_line_for_instance(
                    inst_name,
                    comp_name,
                    nets,
                    settings,
                    cap_subckt=cap_subckt,
                    ideal_passives=ideal_passives,
                )
            )
        )

    if port_stimulus:
        lines.append("")
        _append_stimulus_from_port_names(lines, ports_map)

    if amplifier_control:
        lines.append("")
        if _ports_have_rf_key(ports_map):
            lines.append(
                "* .control: S-parameter sweep (SP LIN) + amplifier_plots (lets, write, plot)"
            )
        ctrl = []
        _append_control_amplifier_plots(ctrl)
        lines.extend(_subst_gnd_for_0(x) for x in ctrl)
    else:
        # Batch-friendly: no ``.control`` block (SP + plot need interactive mode).
        lines.append("")
        lines.append("* batch: operating point only")
        lines.append(".op")
        lines.append(".END")

    text = "\n".join(lines)
    if output_path:
        pathlib.Path(output_path).write_text(text)
        print(f"LOG: Wrote ngspice deck to {output_path}")
    return text
