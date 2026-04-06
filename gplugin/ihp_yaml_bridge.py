"""
IHP-aware routing strategy for gdsfactory YAML: tapers and via stacks between mismatched ports.

Use with ``gf.read.from_yaml(..., routing_strategies=routing_strategies_with_bridge())``
after expanding ``connections:`` into per-link ``routes`` via
:func:`gplugin.yml_spice_plugin.expand_connections_to_bridge_routes`.
"""
from __future__ import annotations

import numpy as np
import gdsfactory as gf
from gdsfactory.pdk import get_routing_strategies
from gdsfactory.typings import RoutingStrategies
from ihp.cells import via_stack


def _inverted_layer_map(layer_map):
    """(layer, datatype) -> name from a LayerMap class."""
    inverted = {}
    for name in dir(layer_map):
        if name.startswith("_"):
            continue
        try:
            val = getattr(layer_map, name)
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
    Normalize IHP layer input to a drawing layer string for ``gf.components.taper(..., layer=...)``.
    """
    pdk = gf.get_active_pdk()

    if isinstance(layer_input, (tuple, list)):
        layer_int = int(layer_input[0])
        dt_int = int(layer_input[1])
        inverted_map = _inverted_layer_map(pdk.layers)
        name = inverted_map.get((layer_int, dt_int))
        if not name:
            name = inverted_map.get((layer_int, 0), f"UNKNOWN_{layer_int}")
        layer_input = name

    return str(layer_input).replace("pin", "").replace("drawing", "")


def auto_bridge_taper(port1, port2):
    """Build a taper (same metal) or via + taper (cross-layer) between two ports."""
    c = gf.Component()

    li = port1.layer_info
    layer_tuple = (int(li.layer), 0)
    li2 = port2.layer_info
    layer_tuple2 = (int(li2.layer), 0)

    lvl1 = li.layer
    lvl2 = li2.layer

    if lvl1 <= lvl2:
        lower_port, upper_port = port1, port2
        lp_layer = resolve_ihp_layer_name(layer_tuple)
        up_layer = resolve_ihp_layer_name(layer_tuple2)
    else:
        lower_port, upper_port = port2, port1
        lp_layer = resolve_ihp_layer_name(layer_tuple2)
        up_layer = resolve_ihp_layer_name(layer_tuple)

    if lp_layer == up_layer:
        dist = float(np.linalg.norm(np.array(upper_port.center) - np.array(lower_port.center)))
        taper_ref = c << gf.components.taper(
            length=max(dist, 0.01),
            width1=lower_port.width,
            width2=upper_port.width,
            layer=lp_layer,
        )
        taper_ref.connect(
            "o1",
            lower_port,
            allow_width_mismatch=True,
            allow_layer_mismatch=True,
            allow_type_mismatch=True,
        )
        o1_center = np.array(taper_ref.ports["o1"].center)
        o2_center = np.array(taper_ref.ports["o2"].center)
        target = np.array(upper_port.center)
        angle_to_target = np.arctan2(target[1] - o1_center[1], target[0] - o1_center[0])
        angle_current = np.arctan2(o2_center[1] - o1_center[1], o2_center[0] - o1_center[0])
        taper_ref.rotate(
            np.degrees(angle_to_target - angle_current),
            center=taper_ref.ports["o1"].center,
        )
        return c

    vs = c << via_stack(
        bottom_layer=lp_layer,
        top_layer=up_layer,
        size=(lower_port.width, lower_port.width),
    )
    vs.connect("bottom", lower_port)
    via_top_port = vs.ports["top"]
    dist = float(np.linalg.norm(np.array(via_top_port.center) - np.array(upper_port.center)))
    taper_ref = c << gf.components.taper(
        length=dist,
        width1=via_top_port.width,
        width2=upper_port.width,
        layer=up_layer,
    )
    taper_ref.connect(
        "o1",
        via_top_port,
        allow_width_mismatch=True,
        allow_layer_mismatch=True,
        allow_type_mismatch=True,
    )
    return c


def bridge_strategy(component, ports1, ports2, **kwargs):
    """Custom gdsfactory routing strategy: width/layer bridge per port pair."""
    routes = []
    for p1, p2 in zip(ports1, ports2):
        taper_comp = auto_bridge_taper(p1, p2)
        ref = component.add_ref(taper_comp)
        routes.append(ref)
    return routes


def routing_strategies_with_bridge() -> RoutingStrategies:
    """Default PDK routing strategies plus ``bridge_strategy`` for IHP YAML nets."""
    return {
        **get_routing_strategies(),
        "bridge_strategy": bridge_strategy,
    }
