# This module provides functions to generate Ngspice SPICE code for various circuit analysis commands.
# It includes functions for .op, .tran, .ac, .dc, .sp, and .vsrc_port.

import os
import re
import subprocess
import sys
from pathlib import Path

# The function is designed for easy conversion into spice suffixes.

def to_spice_unit(value, _context=None):
    """
    Converts a Python number or string to a valid Ngspice string.
    Raises ValueError if input is not a number or valid string.
    _context: optional, ignored (for compatibility with vsource/isource callers).
    """
    if isinstance(value, str):
        return value.lower()
    
    if not isinstance(value, (int, float)):
        raise TypeError(f"Expected number or string, got {type(value).__name__}: {value}")

    # Map for Spice suffixes
    units = [
        (1e12, 't'), (1e9, 'g'), (1e6, 'meg'), (1e3, 'k'),
        (1, ''), (1e-3, 'm'), (1e-6, 'u'), (1e-9, 'n'),
        (1e-12, 'p'), (1e-15, 'f')
    ]

    abs_val = abs(value)
    if abs_val == 0:
        return "0"

    for factor, suffix in units:
        if abs_val >= factor:
            scaled_val = value / factor
            if scaled_val == int(scaled_val):
                scaled_val = int(scaled_val)
            return f"{scaled_val}{suffix}"
    
    return str(value)

## --- Analysis Functions with Error Checking ---

# ==============================================================================
#      _   _   _    _     __    ___   ________________  
#     / \ | \ | |  / \    |  |   \ \ / / ___|_ _/ ___| 
#    / _ \|  \| | / _ \   |  |    \ V /\___ \ | |___ \ 
#   / ___ \ |\  |/ ___ \  |  |___ | |  ___) | | |___) |
#  /_/   \_\_| \_/_/   \_\|_____| |_| |____/___|____/ 
# ==============================================================================

def op():
    """Generates the Operating Point analysis line."""
    return ".op"

def tran(tstep, tstop, tstart=0, tmax=None, uic=False):
    """Generates .tran line with validation."""
    # Logic Check: Stop time must be greater than step time
    try:
        if float(eval(str(tstop).replace('n','e-9').replace('u','e-6').replace('m','e-3'))) <= 0:
            raise ValueError("tstop must be greater than 0.")
    except: pass # Skip complex string evaluation for simplicity

    line = f".tran {to_spice_unit(tstep)} {to_spice_unit(tstop)}"
    if tstart != 0 or tmax is not None:
        line += f" {to_spice_unit(tstart)}"
    if tmax is not None:
        line += f" {to_spice_unit(tmax)}"
    if uic:
        line += " uic"
    return line

def ac(variation, np, fstart, fstop):
    """Generates .ac line. Validates variation type."""
    v = variation.lower()
    if v not in ['dec', 'oct', 'lin']:
        raise ValueError(f"Invalid AC variation '{variation}'. Must be 'dec', 'oct', or 'lin'.")
    
    if int(np) <= 0:
        raise ValueError("Number of points (np) must be a positive integer.")

    return f".ac {v} {int(np)} {to_spice_unit(fstart)} {to_spice_unit(fstop)}"

def dc(srcnam, vstart, vstop, vincr, src2=None, start2=None, stop2=None, incr2=None):
    """
    .dc srcnam vstart vstop vincr [src2 start2 stop2 incr2]
    Validates that if a second source is started, all 4 second-source params must exist.
    """
    # Validate primary sweep
    if not isinstance(srcnam, str):
        raise ValueError("Primary source name (srcnam) must be a string.")
    
    line = f".dc {srcnam} {to_spice_unit(vstart)} {to_spice_unit(vstop)} {to_spice_unit(vincr)}"

    # Validate secondary sweep (optional)
    secondary_params = [src2, start2, stop2, incr2]
    active_secondary = [p for p in secondary_params if p is not None]

    if len(active_secondary) > 0:
        if len(active_secondary) < 4:
            raise ValueError("For a dual DC sweep, you must provide all four: src2, start2, stop2, and incr2.")
        
        if not isinstance(src2, str):
            raise ValueError("Secondary source name (src2) must be a string.")
            
        line += f" {src2} {to_spice_unit(start2)} {to_spice_unit(stop2)} {to_spice_unit(incr2)}"
    
    return line

def sp(freq_type, np, fstart, fstop, noise=0):
    """
    .sp freq_type np fstart fstop [noise=0/1]
    Note: Port names are NOT listed here; Ngspice uses all 
    defined 'port' components in the netlist.
    """
    # 1. Validate Frequency Type
    ft = str(freq_type).lower()
    if ft not in ['dec', 'oct', 'lin']:
        raise ValueError(f"SP freq_type must be 'dec', 'oct', or 'lin'. Received: '{freq_type}'")

    # 2. Validate Noise parameter
    if noise not in [0, 1]:
        raise ValueError("The 'noise' parameter must be 0 (off) or 1 (on).")

    # 3. Construct the Command
    noise_str = f"{noise}" if noise == 1 else ""
    
    # Filter out empty strings if noise is 0
    parts = [".sp", ft, str(int(np)), to_spice_unit(fstart), to_spice_unit(fstop)]
    if noise_str:
        parts.append(noise_str)
        
    return " ".join(parts)



# ==============================================================================
#      ____   ___  _   _ ____   ____ _____ ____  
#     / ___| / _ \| | | |  _ \ / ___| ____/ ___| 
#     \___ \| | | | | | | |_) | |   |  _| \___ \ 
#      ___) | |_| | |_| |  _ <| |___| |___ ___) |
#     |____/ \___/ \___/|_| \_\\____|_____|____/ 
# ==============================================================================


def vsource(name, n_plus, n_minus, dc=0, ac=None, transient=None):
    """
    Standard Independent Voltage Source.
    Syntax: Vname n+ n- [dc val] [ac val] [transient_spec]
    
    transient: Expects a string from one of the other functions 
               (e.g., pulse(), sine(), etc.)
    """
    # Ensure name starts with V
    ref = f"V{name}" if not str(name).upper().startswith('V') else name
    
    line = f"{ref} {n_plus} {n_minus}"
    
    if dc is not None:
        line += f" dc {to_spice_unit(dc, 'dc')}"
    
    if ac is not None:
        line += f" ac {to_spice_unit(ac, 'ac')}"
        
    if transient:
        # If the user passed a full source line, extract just the function part
        if "(" in transient:
            func_part = transient.split(")", 1)[0].split(" ", 3)[-1] + ")"
            line += f" {func_part}"
        else:
            line += f" {transient}"
            
    return line



def isource(name, n_plus, n_minus, dc=0, ac=None, transient=None):
    """
    Standard Independent Current Source.
    Syntax: Iname n+ n- [dc val] [ac val] [transient_spec]
    Note: Current flows from n+ to n- inside the source.
    """
    # Ensure name starts with I
    ref = f"I{name}" if not str(name).upper().startswith('I') else name
    
    line = f"{ref} {n_plus} {n_minus}"
    
    if dc is not None:
        line += f" dc {to_spice_unit(dc, 'dc')}"
    
    if ac is not None:
        line += f" ac {to_spice_unit(ac, 'ac')}"
        
    if transient:
        if "(" in transient:
            func_part = transient.split(")", 1)[0].split(" ", 3)[-1] + ")"
            line += f" {func_part}"
        else:
            line += f" {transient}"
            
    return line


def vsrc_port(name, n_plus, n_minus, portnum, z0=50, dc=0, ac=1):
    """
    Defines a Voltage Source as an RF Port.
    Syntax: Vname n+ n- dc <val> ac <val> portnum <n1> z0 <z>
    """
    if not isinstance(portnum, int) or portnum < 1:
        raise ValueError(f"portnum must be a positive integer (n1). Got: {portnum}")
    
    return (f"{name} {n_plus} {n_minus} "
            f"dc {to_spice_unit(dc)} "
            f"ac {to_spice_unit(ac)} "
            f"portnum {portnum} "
            f"z0 {to_spice_unit(z0)}")


def pulse(name, n_plus, n_minus, v1, v2, td, tr, tf, pw, per, np=None, prefix="V"):
    """
    PULSE(V1 V2 TD TR TF PW PER)
    V1 Initial value - V, A
    V2 Pulsed value - V, A
    TD Delay time 0.0 sec
    TR Rise time TSTEP sec
    TF Fall time TSTEP sec
    PW Pulse width TSTOP sec
    PER Period TSTOP sec
    NP Number of Pulses * unlimited
    """
    if np is not None and (not isinstance(np, int) or np < 1):
        raise ValueError(f"Error: NP must be a positive integer or None. Got: {np}")
    
    # Validation
    for val, label in [(td, "delay"), (tr, "rise"), (tf, "fall"), (pw, "width"), (per, "period")]:
        _check_pos(val, label)
    
    # Logic check: Period must be >= sum of active times
    if isinstance(per, (int, float)) and isinstance(pw, (int, float)):
        if per < (pw + tr + tf):
            raise ValueError(f"Error: Period ({per}) must be >= Rise + Fall + Pulse Width ({tr+tf+pw})")

    params = [v1, v2, td, tr, tf, pw, per, np]
    p_str = " ".join([to_spice_unit(p) for p in params])
    return f"{prefix.upper()}{name} {n_plus} {n_minus} pulse({p_str})"


def _check_pos(val, name):
    """Internal helper to ensure time/freq values are non-negative."""
    if isinstance(val, (int, float)) and val < 0:
        raise ValueError(f"Error: {name} cannot be negative. Got {val}")

def sine(name, n_plus, n_minus, vo, va, freq, td=0, theta=0, prefix="V"):
    """
    SINE(VO VA FREQ TD THETA)
    VO Offset voltage - V
    VA Amplitude voltage - V
    FREQ Frequency 1/T STOP Hz
    TD Delay time 0.0 sec
    THETA Damping factor 0.0 1/sec
    """
    _check_pos(freq, "frequency")
    _check_pos(td, "delay")
    
    if isinstance(freq, (int, float)) and freq == 0:
        raise ValueError("Error: Sine frequency cannot be zero.")

    params = [vo, va, freq, td, theta]
    p_str = " ".join([to_spice_unit(p) for p in params])
    return f"{prefix.upper()}{name} {n_plus} {n_minus} sin({p_str})"

def exp_source(name, n_plus, n_minus, v1, v2, td1, tau1, td2, tau2, prefix="V"):
    """
    EXP(V1 V2 TD1 TAU1 TD2 TAU2)
    V1 Initial value - V, A
    V2 pulsed value - V, A
    TD1 rise delay time 0.0 sec
    TAU1 rise time constant TSTEP sec
    TD2 fall delay time TD1+TSTEP sec
    TAU2 fall time constant TSTEP sec
    """
    for val, label in [(td1, "td1"), (tau1, "tau1"), (td2, "td2"), (tau2, "tau2")]:
        _check_pos(val, label)

    params = [v1, v2, td1, tau1, td2, tau2]
    p_str = " ".join([to_spice_unit(p) for p in params])
    return f"{prefix.upper()}{name} {n_plus} {n_minus} exp({p_str})"

def pwl(name, n_plus, n_minus, points, prefix="V"):
    """
    PWL(T1 V1 T2 V2 ...)
    points: List of tuples [(0, 0), (1n, 5), ...]
    """
    if not points or not isinstance(points, list):
        raise ValueError("Error: PWL requires a list of (time, value) tuples.")
    
    last_t = -1
    formatted_points = []
    for i, (t, v) in enumerate(points):
        if isinstance(t, (int, float)):
            if t < last_t:
                raise ValueError(f"Error: PWL time points must be non-decreasing. Point {i} has t={t} which is less than {last_t}")
            last_t = t
        formatted_points.append(f"{to_spice_unit(t)} {to_spice_unit(v)}")
    
    return f"{prefix.upper()}{name} {n_plus} {n_minus} pwl({' '.join(formatted_points)})"



# ==============================================================================
#      __  __ ___ ____   ____ _____ _     _        _      _   _ _____ ___  _   _ ____  
#     |  \/  |_ _/ ___| / ___| ____| |   | |      / \    | \ | | ____/ _ \| | | / ___| 
#     | |\/| || |\___ \| |   |  _| | |   | |     / _ \   |  \| |  _|| | | | | | \___ \ 
#     | |  | || | ___) | |___| |___| |___| |___ / ___ \  | |\  | |__| |_| | |_| |___) |
#     |_|  |_|___|____/ \____|_____|_____|_____/_/   \_\_|_| \_|_____\___/ \___/|____/ 
# ==============================================================================

def include(file_path):
    """
    Includes an external spice file or model library.
    Syntax: .include /path/to/file.lib
    """
    if not isinstance(file_path, str):
        raise ValueError("File path must be a string.")
    return f".include {file_path}"

def param(name, value):
    """
    Defines a global parameter for the netlist.
    Syntax: .param my_res=1k
    """
    return f".param {name}={to_spice_unit(value)}"

def model(name, type, parameters):
    """
    Defines a model card for devices (Diodes, BJTs, MOSFETs).
    Example: model("1N4148", "D", "IS=2.68n N=1.83")
    """
    return f".model {name} {type.upper()}({parameters})"

def _parse_lib_subckts(file_path, section_name=None):
    """
    Parse a .lib file for .SUBCKT definitions; return dict suitable for SUBCKT_MODELS.
    If section_name is given, only parse subckts in that section (lines after * section_name or .section section_name).
    """
    import re
    from pathlib import Path
    out = {}
    path = Path(file_path)
    if not path.exists():
        return out
    try:
        text = path.read_text(errors="replace")
    except Exception:
        return out
    lines = text.splitlines()
    in_section = section_name is None
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        # Section marker: * section_name or .section section_name
        if section_name:
            if re.match(r"^\*\s+" + re.escape(section_name) + r"\s*$", stripped, re.I) or re.match(
                r"^\.section\s+" + re.escape(section_name) + r"\s*$", stripped, re.I
            ):
                in_section = True
                i += 1
                continue
            if in_section and stripped.startswith("*") and not stripped.upper().startswith(".SUBCKT"):
                in_section = False
                i += 1
                continue
        if not in_section:
            i += 1
            continue
        if not re.match(r"^\.subckt\s", stripped, re.I):
            i += 1
            continue
        # Collect full .subckt line (with + continuations)
        subckt_line = stripped
        j = i + 1
        while j < len(lines) and lines[j].strip().startswith("+"):
            subckt_line += " " + lines[j].strip()[1:].strip()
            j += 1
        i = j
        # Parse: .SUBCKT name n1 n2 ... [p1=val1 p2=val2 ...]
        parts = subckt_line.split()
        if len(parts) < 2:
            continue
        # First word after .subckt is name (skip directive)
        name = parts[1]
        nodes = []
        defaults = {}
        for t in parts[2:]:
            if "=" in t:
                k, v = t.split("=", 1)
                defaults[k.strip()] = v.strip()
            else:
                nodes.append(t)
        out[name] = {"nodes": nodes, "defaults": defaults}
    return out


def register_lib(file_path, section_name=None):
    """
    Parse a .lib file and register all .SUBCKT model names into SUBCKT_MODELS.
    Call this (or use lib() which does it automatically) so xsubckt() can use model-driven args.
    """
    parsed = _parse_lib_subckts(file_path, section_name)
    for name, config in parsed.items():
        SUBCKT_MODELS[name] = config
    return len(parsed)


def lib(file_path, section_name):
    """
    Includes a specific section of a library file and registers all .SUBCKT
    definitions from it so xsubckt(name, model, **kwargs) works for every subcircuit in the file.
    Syntax: .lib path/to/models.lib tt_corner
    """
    register_lib(file_path, section_name)
    return f".lib {file_path} {section_name}"

def options(opt_list):
    """
    Sets simulation options like reltol, temp, or method.
    Example: options(["reltol=1m", "temp=25"])
    """
    if not isinstance(opt_list, list):
        raise ValueError("Options must be provided as a list of strings.")
    return f".options {' '.join(opt_list)}"

# ==============================================================================
#      ____  _____ ____ ___ ____ _____ ___  ____  ____  
#     |  _ \| ____/ ___|_ _/ ___|_   _/ _ \|  _ \/ ___| 
#     | |_) |  _| \___ \| | \___ \ | || | | | |_) \___ \ 
#     |  _ <| |___ ___) | |  ___) || || |_| |  _ < ___) |
#     |_| \_\_____|____/___|____/ |_| \___/|_| \_\____/ 
# ==============================================================================

def resistor(name, n1, n2, value):
    """
    Standard Resistor.
    Syntax: Rname n1 n2 value
    """
    ref = f"R{name}" if not str(name).upper().startswith('R') else name
    return f"{ref} {n1} {n2} {to_spice_unit(value)}"

def capacitor(name, n1, n2, value, ic=None):
    """
    Standard Capacitor.
    ic: Initial condition (voltage) for transient analysis.
    """
    ref = f"C{name}" if not str(name).upper().startswith('C') else name
    line = f"{ref} {n1} {n2} {to_spice_unit(value)}"
    if ic is not None:
        line += f" ic={to_spice_unit(ic)}"
    return line

def inductor(name, n1, n2, value, ic=None):
    """
    Standard Inductor.
    ic: Initial condition (current).
    """
    ref = f"L{name}" if not str(name).upper().startswith('L') else name
    line = f"{ref} {n1} {n2} {to_spice_unit(value)}"
    if ic is not None:
        line += f" ic={to_spice_unit(ic)}"
    return line


# Registry: model_name -> {"nodes": [ordered node keys], "defaults": {param: val, ...}}
# Node keys are the keyword names expected when calling xsubckt(name, model, **kwargs).
SUBCKT_MODELS = {

}


def xsubckt(name, subckt_name_or_nodes, *args, **kwargs):
    """
    Subcircuit instance (X-element).
    Syntax: Xname n1 n2 ... subckt_name param1=val1 param2=val2 ...

    Positional nodes (e.g. from .lib): xsubckt("R1", "rsil", "in", "out", 0) or with params:
        xsubckt("R1", "rsil", "in", "out", 0, l=1u w=1u). Uses SUBCKT_MODELS defaults if model was registered by lib().

    Named nodes (model-driven): xsubckt("M1", "sg13_lv_nmos", d="out", g="gate", s="0", b="0", w=0.15e-6)

    Legacy: xsubckt("M1", (n1, n2, n3, n4), "sg13_lv_nmos", w=0.15e-6) with nodes as second arg.
    Unknown model: xsubckt("M1", "my_sub", nodes=("n1", "n2"), p1=1).
    """
    ref = f"X{name}" if not str(name).upper().startswith("X") else name
    # Legacy: second arg is nodes (list/tuple), first extra positional is subckt_name
    if isinstance(subckt_name_or_nodes, (list, tuple)) and len(subckt_name_or_nodes) > 0:
        nodes_list = list(subckt_name_or_nodes)
        subckt_name = args[0] if args else None
        if subckt_name is None or not isinstance(subckt_name, str):
            raise ValueError("xsubckt: when nodes is second arg, subckt_name must be the third (positional) arg.")
        params = dict(kwargs)
        node_str = " ".join(str(n) for n in nodes_list)
        part_str = f"{ref} {node_str} {subckt_name}"
        if params:
            part_str += " " + " ".join(f"{k}={to_spice_unit(v)}" for k, v in params.items())
        return part_str
    subckt_name = subckt_name_or_nodes
    # Positional nodes: xsubckt("R1", "rsil", "in", "out", 0, l=1u)
    if args and isinstance(subckt_name, str):
        node_list = [str(n) for n in args]
        if subckt_name in SUBCKT_MODELS:
            defaults = dict(SUBCKT_MODELS[subckt_name].get("defaults", {}))
            params = {**defaults, **kwargs}
        else:
            params = kwargs
        node_str = " ".join(node_list)
        part_str = f"{ref} {node_str} {subckt_name}"
        if params:
            param_str = " ".join(f"{k}={to_spice_unit(v)}" for k, v in params.items())
            part_str += " " + param_str
        return part_str
    # Named nodes (model-driven) or nodes= kwarg
    nodes = args[0] if len(args) == 1 else None
    if nodes is None and "nodes" in kwargs:
        nodes = kwargs.pop("nodes")
    if subckt_name in SUBCKT_MODELS:
        config = SUBCKT_MODELS[subckt_name]
        node_order = config["nodes"]
        defaults = dict(config.get("defaults", {}))
        node_list = []
        for k in node_order:
            if k not in kwargs:
                raise ValueError(f"xsubckt '{subckt_name}': missing node '{k}'. Required nodes: {node_order}")
            node_list.append(kwargs.pop(k))
        params = {**defaults, **kwargs}
    else:
        if nodes is None or (isinstance(nodes, (list, tuple)) and len(nodes) == 0):
            raise ValueError("xsubckt: for unknown subckt_name, pass nodes as extra positionals or nodes=(...). Known models: " + ", ".join(SUBCKT_MODELS.keys()))
        node_list = list(nodes)
        params = kwargs
    node_str = " ".join(str(n) for n in node_list)
    part_str = f"{ref} {node_str} {subckt_name}"
    if params:
        param_str = " ".join(f"{k}={to_spice_unit(v)}" for k, v in params.items())
        part_str += " " + param_str
    return part_str


def mosfet(name, d, g, s, b, mname, m=None, l=None, w=None, ad=None, as_=None,
           pd=None, ps=None, nrd=None, nrs=None, off=False, ic=None, temp=None, **params):
    """
    Standard MOSFET (M-element).
    Syntax: Mname nd ng ns nb mname <m=val> <l=val> <w=val> <ad=val> <as=val>
            <pd=val> <ps=val> <nrd=val> <nrs=val> <off> <ic=vds,vgs,vbs> <temp=t>

    Nodes: d=drain, g=gate, s=source, b=bulk/body.
    mname: model name (from .model or .lib). Use mosfet_subckt() for X (subcircuit) style.
    """
    if not isinstance(mname, str) or not mname.strip():
        raise ValueError("mosfet: mname (model name) must be a non-empty string.")
    ref = f"X{name}" if not str(name).upper().startswith('X') else name
    line = f"{ref} {d} {g} {s} {b} {mname}"
    opts = []
    if m is not None:
        opts.append(f"m={to_spice_unit(m)}")
    if l is not None:
        opts.append(f"l={to_spice_unit(l)}")
    if w is not None:
        opts.append(f"w={to_spice_unit(w)}")
    if ad is not None:
        opts.append(f"ad={to_spice_unit(ad)}")
    if as_ is not None:
        opts.append(f"as={to_spice_unit(as_)}")
    if pd is not None:
        opts.append(f"pd={to_spice_unit(pd)}")
    if ps is not None:
        opts.append(f"ps={to_spice_unit(ps)}")
    if nrd is not None:
        opts.append(f"nrd={to_spice_unit(nrd)}")
    if nrs is not None:
        opts.append(f"nrs={to_spice_unit(nrs)}")
    if off:
        opts.append("off")
    if ic is not None:
        if isinstance(ic, (list, tuple)) and len(ic) >= 3:
            ic_str = ",".join(to_spice_unit(v) for v in ic[:3])
        else:
            ic_str = to_spice_unit(ic)
        opts.append(f"ic={ic_str}")
    if temp is not None:
        opts.append(f"temp={to_spice_unit(temp)}")
    for k, v in params.items():
        opts.append(f"{k}={to_spice_unit(v)}")
    if opts:
        line += " " + " ".join(opts)
    return line


def hbt(name, c, b, e, bn, mname, nx=1, dtemp=0, ny=1, le=0.96e-6, we=0.12e-6,
        el=None, selft=1, sw_nqs=0, **params):
    """
    HBT subcircuit instance (X-element), e.g. IHP SG13G2 four-terminal NPN.

    Nodes: c=collector, b=base, e=emitter, bn=base nodule (substrate tie).
    mname: subcircuit name from the PDK (.subckt), e.g. npn13G2 — change mname for
    other HBT cells; extra instance parameters go through **params.

    Default geometry matches typical npn13G2 (.param Nx Ny le we selft sw_nqs dtemp).
    Pass el as a number or a string expression (e.g. \"le*1e6\") for El=.
    """
    if not isinstance(mname, str) or not mname.strip():
        raise ValueError("hbt: mname (subcircuit model name) must be a non-empty string.")
    ref = f"X{name}" if not str(name).upper().startswith("X") else name
    line = f"{ref} {c} {b} {e} {bn} {mname}"
    opts = []
    if nx is not None:
        opts.append(f"Nx={to_spice_unit(nx)}")
    if dtemp is not None:
        opts.append(f"dtemp={to_spice_unit(dtemp)}")
    if ny is not None:
        opts.append(f"Ny={to_spice_unit(ny)}")
    if le is not None:
        opts.append(f"le={to_spice_unit(le)}")
    if we is not None:
        opts.append(f"we={to_spice_unit(we)}")
    if el is not None:
        if isinstance(el, str):
            opts.append(f"El={el}")
        else:
            opts.append(f"El={to_spice_unit(el)}")
    if selft is not None:
        opts.append(f"selft={to_spice_unit(selft)}")
    if sw_nqs is not None:
        opts.append(f"sw_nqs={to_spice_unit(sw_nqs)}")
    for k, v in params.items():
        opts.append(f"{k}={to_spice_unit(v)}")
    if opts:
        line += " " + " ".join(opts)
    return line


def _plot_qword(label):
    """Quote a plot title/label for ngspice if it contains whitespace."""
    if label is None:
        return None
    s = str(label)
    if any(c in s for c in " \t\n"):
        return f'"{s.replace(chr(34), chr(92) + chr(34))}"'
    return s


def plot_command(
    *expressions,
    plot_mode=None,
    ylimit=None,
    xlimit=None,
    xindices=None,
    xcompress=None,
    xdelta=None,
    ydelta=None,
    vs=None,
    xlabel=None,
    ylabel=None,
    title=None,
    xlog=False,
    ylog=False,
    loglog=False,
    nogrid=False,
    linplot=False,
    combplot=False,
    pointplot=False,
    nointerp=False,
    noretraceplot=False,
    samep=False,
    linear=False,
    polar=False,
    smith=False,
    smithgrid=False,
):
    """
    Build an ngspice interactive ``plot`` command line (for use inside ``.control``).

    General form (ngspice manual): plot exprs [ylimit ...] [xlimit ...] [vs ...]
    [xlog] [ylog] [loglog] [xlabel ...] [ylabel ...] [title ...] [polar] [smith] ...

    Parameters
    ----------
    *expressions : str
        One or more vector names or expressions, e.g. ``"db(v(out))"``, ``"ph(v(out))"``.
        For names with special characters, pass a quoted string, e.g. ``'"/vout"'``.
    plot_mode : str, optional
        Instead of expressions, use a bulk mode: ``"all"``, ``"ally"``, ``"alli"``, or ``"allv"``.
    ylimit, xlimit : tuple of (low, high), optional
        Axis limits; numeric values are passed through ``to_spice_unit``.
    xindices : tuple (i_lo, i_hi), optional
        1-based index range of points to plot.
    xcompress : int, optional
        Plot one of every *xcompress* points.
    xdelta, ydelta : optional
        Grid line spacing (numbers or strings).
    vs : str, optional
        X-axis scale expression (e.g. ``"frequency"`` for AC).
    xlabel, ylabel, title : str, optional
        Axis/window labels; quoted automatically if they contain spaces.
    xlog, ylog, loglog : bool
        Logarithmic axes.
    nogrid, linplot, combplot, pointplot, nointerp, noretraceplot, samep, linear : bool
        Style and behavior flags (see ngspice ``plot`` documentation).
    polar, smith, smithgrid : bool
        Polar / Smith chart modes (mutually exclusive usage per ngspice rules).
    """
    valid_modes = {"all", "ally", "alli", "allv"}
    if plot_mode is not None:
        pm = str(plot_mode).lower()
        if pm not in valid_modes:
            raise ValueError(f"plot_mode must be one of {sorted(valid_modes)}, got {plot_mode!r}")
        if expressions:
            raise ValueError("Do not pass both plot_mode and expressions.")
        parts = ["plot", pm]
    else:
        if not expressions:
            raise ValueError("plot_command: pass at least one expression, or use plot_mode=.")
        parts = ["plot"] + [str(e) for e in expressions]

    def add_limit(name, lim):
        if lim is None:
            return
        if not (isinstance(lim, (list, tuple)) and len(lim) == 2):
            raise ValueError(f"{name} must be a (low, high) pair")
        lo, hi = lim
        parts.extend(
            [
                name,
                to_spice_unit(lo) if not isinstance(lo, str) else lo,
                to_spice_unit(hi) if not isinstance(hi, str) else hi,
            ]
        )

    add_limit("ylimit", ylimit)
    add_limit("xlimit", xlimit)

    if xindices is not None:
        if not (isinstance(xindices, (list, tuple)) and len(xindices) == 2):
            raise ValueError("xindices must be (i_lo, i_hi)")
        i0, i1 = xindices
        parts.extend(["xindices", str(int(i0)), str(int(i1))])

    if xcompress is not None:
        parts.extend(["xcompress", str(int(xcompress))])

    if xdelta is not None:
        parts.extend(
            [
                "xdelta",
                to_spice_unit(xdelta) if not isinstance(xdelta, str) else xdelta,
            ]
        )
    if ydelta is not None:
        parts.extend(
            [
                "ydelta",
                to_spice_unit(ydelta) if not isinstance(ydelta, str) else ydelta,
            ]
        )

    _plot_flags = (
        ("xlog", xlog),
        ("ylog", ylog),
        ("loglog", loglog),
        ("nogrid", nogrid),
        ("linplot", linplot),
        ("combplot", combplot),
        ("pointplot", pointplot),
        ("nointerp", nointerp),
        ("noretraceplot", noretraceplot),
        ("samep", samep),
        ("linear", linear),
        ("polar", polar),
        ("smith", smith),
        ("smithgrid", smithgrid),
    )
    for name, on in _plot_flags:
        if on:
            parts.append(name)

    if vs is not None:
        parts.extend(["vs", str(vs)])

    if xlabel is not None:
        qw = _plot_qword(xlabel)
        parts.extend(["xlabel", qw])
    if ylabel is not None:
        parts.extend(["ylabel", _plot_qword(ylabel)])
    if title is not None:
        parts.extend(["title", _plot_qword(title)])

    return " ".join(parts)


_AMPLIFIER_WRITE_VECTORS = (
    "S_1_1 Y_1_1 Z_1_1 Cy_1_1 S_1_2 Y_1_2 Z_1_2 Cy_1_2 "
    "S_2_1 Y_2_1 Z_2_1 Cy_2_1 S_2_2 Y_2_2 Z_2_2 Cy_2_2 Rn NF SOpt NFmin num den Gmax Fmax "
    "s11_db s12_db s21_db s22_db s11_mag s11_conj s12_mag s12_conj s21_mag s21_conj s22_mag "
    "s22_conj delta delta_mag kf mu muprime"
)

_AMPLIFIER_LET_LINES = (
    "let num = (1/4)*(abs(v(y_2_1)-v(y_1_2))*abs(v(y_2_1)-v(y_1_2)))",
    "let den = real(v(y_1_1))*real(v(y_2_2))-real(v(y_2_1))*real(v(y_1_2))",
    "let Gmax = num/den",
    "let Fmax = sqrt(mag(Gmax))*frequency",
    "let s11_db = db(v(s_1_1))",
    "let s12_db = db(v(s_1_2))",
    "let s21_db = db(v(s_2_1))",
    "let s22_db = db(v(s_2_2))",
    "let s11_mag = mag(v(s_1_1))",
    "let s11_conj = conj(v(s_1_1))",
    "let s12_mag = mag(v(s_1_2))",
    "let s12_conj = conj(v(s_1_2))",
    "let s21_mag = mag(v(s_2_1))",
    "let s21_conj = conj(v(s_2_1))",
    "let s22_mag = mag(v(s_2_2))",
    "let s22_conj = conj(v(s_2_2))",
    "let delta = v(s_1_1)*v(s_2_2)-v(s_1_2)*v(s_2_1)",
    "let delta_mag = mag(delta)",
    "let kf = (1-s11_mag*s11_mag-s22_mag*s22_mag+delta_mag*delta_mag)/(2*mag(v(s_1_2)*v(s_2_1)))",
    "let mu = (1-s11_mag*s11_mag)/(mag(v(s_2_2)-delta*s11_conj)+mag(v(s_1_2)*v(s_2_1)))",
    "let muprime = (1-s22_mag*s22_mag)/(mag(v(s_1_1)-delta*s22_conj)+mag(v(s_1_2)*v(s_2_1)))",
)


def amplifier_plots(
    netlist,
    *,
    write_raw: str = "spice4qucs.sp1.plot",
    sp_points: int = 401,
    sp_fstart=0.1e9,
    sp_fstop=100e9,
    sp_noise: int = 1,
    add_default_plot: bool = True,
    plot_expressions=("s11_db", "s22_db", "s21_db"),
    plot_ylimit=(-40, 20),
    plot_extra=None,
):
    """
    Append RF two-port style ``.control`` content: ``SP LIN`` sweep, stability / NF / S lets,
    ``write`` of the usual vector set, and optionally a default ``plot`` of S-parameters in dB.

    Call **after** ``netlist.write_text(".control")`` (and optional blank line). You still add
    ``exit`` / ``.endc`` / ``.END`` yourself.

    Parameters
    ----------
    write_raw
        Filename passed to ngspice ``write`` (raw plot file).
    sp_points, sp_fstart, sp_fstop, sp_noise
        ``SP LIN <np> <fstart> <fstop> <noise>`` (noise 0 or 1).
    add_default_plot
        If True, append ``plot`` for ``plot_expressions`` with ``plot_ylimit`` and ``plot_extra``.
    plot_expressions
        Traces for the default ``plot`` command.
    plot_ylimit
        Passed to :func:`plot_command` as ``ylimit=`` (ignored if ``add_default_plot`` is False).
    plot_extra
        Optional dict of extra kwargs for :func:`plot_command` (e.g. ``xlog=True``).
    """
    netlist.write_text(
        f"SP LIN {int(sp_points)} {to_spice_unit(sp_fstart)} "
        f"{to_spice_unit(sp_fstop)} {int(sp_noise)}"
    )
    for line in _AMPLIFIER_LET_LINES:
        netlist.write_text(line)
    netlist.write_text(f"write {write_raw} {_AMPLIFIER_WRITE_VECTORS}")
    if add_default_plot:
        pk = {"ylimit": plot_ylimit}
        if plot_extra:
            pk.update(plot_extra)
        netlist.add_plot_command(*plot_expressions, **pk)


# ==============================================================================

class SpiceNetlist:
    def __init__(self, filename="circuit.cir"):
        self.filename = filename
        self.contents = []

    def add_spice(self, function, *args, **kwargs):
        """Calls a subfunction and appends its output to the netlist."""
        result = function(*args, **kwargs)
        if result:
            self.contents.append(result)

    def write_text(self, text):
        """Manually add a raw string or comment."""
        self.contents.append(text)

    def add_plot_command(self, *expressions, **kwargs):
        """
        Append one ngspice ``plot`` command (see :func:`plot_command`).

        Example::

            circuit.write_text(".control")
            circuit.add_plot_command(
                "db(v(s_2_1))", "db(v(s_1_1))",
                vs="frequency",
                xlog=True,
                ylimit=(-40, 5),
                xlabel="Hz",
                ylabel="dB",
            )
            circuit.write_text(".endc")
        """
        line = plot_command(*expressions, **kwargs)
        if line:
            self.contents.append(line)

    def add_amplifier_plots(self, **kwargs):
        """Append :func:`amplifier_plots` lines to this netlist (inside ``.control``)."""
        amplifier_plots(self, **kwargs)

    def print_netlist(self):
        """Print the netlist contents to stdout."""
        print("\n".join(self.contents))

    def save(self):
        """Writes everything to the physical .cir file."""
        with open(self.filename, "w") as f:
            f.write("\n".join(self.contents))
        print(f"Netlist saved to {self.filename}")

    def has_ngspice_plot_command(self) -> bool:
        """True if this netlist includes a ``plot`` line in ``.control`` (see :func:`netlist_has_ngspice_plot_command`)."""
        return netlist_has_ngspice_plot_command(self.contents)


_PLOT_CMD_LINE = re.compile(r"^plot(\s|$)", re.IGNORECASE)


def netlist_has_ngspice_plot_command(netlist: str | list[str]) -> bool:
    """
    True if the netlist contains an interactive ``plot`` command inside ``.control`` … ``.endc``.

    Skips comment lines (leading ``*``). Matches ``plot ...`` / ``plot all`` etc., not ``hardcopy``.
    """
    if isinstance(netlist, list):
        text = "\n".join(netlist)
    else:
        text = netlist
    in_control = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("*"):
            continue
        low = line.lower()
        if low.startswith(".control"):
            in_control = True
            continue
        if low.startswith(".endc"):
            in_control = False
            continue
        if in_control and _PLOT_CMD_LINE.match(line):
            return True
    return False


def run_sim(filename, quiet=None, cwd=None):
    """Run ngspice on the netlist file.

    quiet: If True, suppress ngspice stdout/stderr. If False, show them. If None (default),
    use quiet=False when the netlist contains a ``plot`` command (interactive graphics), else True.

    When ``plot`` is used and quiet is False, ngspice is run as ``ngspice -i <file>`` (interactive),
    ``DISPLAY`` defaults to ``:0`` on Linux if unset (WSLg), and the child inherits stdio without
    closing all fds so X11/Wayland can open plot windows from Python/IDE launches.

    cwd: optional working directory for ngspice (affects relative ``write`` / include paths)."""
    path = Path(filename).resolve()
    path_str = str(path)
    if quiet is None:
        try:
            text = path.read_text(errors="replace")
            quiet = not netlist_has_ngspice_plot_command(text)
        except OSError:
            quiet = True
    cmd = ["ngspice", path_str]
    if not quiet:
        cmd.insert(1, "-i")
    kwargs: dict = {}
    if quiet:
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    if cwd is not None:
        kwargs["cwd"] = str(Path(cwd).resolve())
    if not quiet:
        env = os.environ.copy()
        if sys.platform == "linux" and not (env.get("DISPLAY") or "").strip():
            env["DISPLAY"] = ":0"
        env.pop("MPLBACKEND", None)
        kwargs["env"] = env
        kwargs["close_fds"] = False
    subprocess.run(cmd, **kwargs)