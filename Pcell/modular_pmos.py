import math
import gdsfactory as gf
from ihp import PDK
from ihp.tech import LAYER, TECH
from gdsfactory import Component

PDK.activate()

def calculate_distributed_positions(total_dim, size=0.16, min_gap=0.18, margin=0.07):
    """Calculates Y-positions for contacts along the width of the transistor."""
    dim = max(0.3, total_dim)
    n = int((dim - (2 * margin) + min_gap) // (size + min_gap))
    n = max(1, n)
    
    positions = []
    if n == 1:
        positions.append(round((dim - size) / 2, 4))
    else:
        actual_gap = ((dim - 2 * margin) - (n * size)) / (n - 1)
        for i in range(n):
            positions.append(round(margin + i * (size + actual_gap), 4))
    return n, positions

def add_contact_column(component, x_offset, y_min, width, layers):
    """Helper to add a vertical column of contacts and the metal1 strap."""
    n, positions = calculate_distributed_positions(width)
    
    # Add Contacts
    for y_pos in positions:
        component.add_ref(gf.components.rectangle(size=(0.16, 0.16), layer=layers['cont'])).move((x_offset + 0.07, y_min + y_pos))
    
    # Add Metal 1 Strap
    m1_w, m1_h = 0.16, max(0.26, width)
    m1_y = y_min + (0.3 - m1_h)/2 if width <= 0.3 else y_min
    component.add_ref(gf.components.rectangle(size=(m1_w, m1_h), layer=layers['metal1'])).move((x_offset + 0.07, m1_y))

def generate_blocks_from_ends(total_length):
    size = 0.16
    gap = 0.18
    margin = 0.07
    pitch = size + gap # 0.34
    
    bottom_positions = []
    top_positions = []
    
    # 1. Calculate how many blocks can fit from one side to the halfway point
    # We use a while loop to ensure we don't violate the center gap requirement
    
    # Start at the margins
    current_bottom = margin
    current_top = total_length - margin - size
    
    while current_bottom <= current_top:
        # Check if the potential new blocks are at least 'gap' apart
        if (current_top - (current_bottom + size)) >= gap:
            bottom_positions.append(round(current_bottom, 4))
            # Avoid adding the same block twice if they meet perfectly in the middle
            if current_top > current_bottom:
                top_positions.append(round(current_top, 4))
        else:
            # Not enough space for more blocks with the required gap
            break
            
        current_bottom += pitch
        current_top -= pitch

    # Combine and sort all unique positions
    all_positions = sorted(list(set(bottom_positions + top_positions)))
    return all_positions

def generate_alternating_positions(total_length):
    size = 0.16
    gap = 0.18
    margin = 0.07
    pitch = size + gap # 0.34
    
    top_positions = []
    bottom_positions = []
    
    # 1. Place the first mandatory blocks at the margins
    # Top-most block
    current_top = total_length - margin - size
    # Bottom-most block
    current_bottom = margin
    
    # Check if we can even fit one block
    if current_top < margin:
        # If the space is tiny, just center one block
        return [round((total_length - size) / 2, 4)]

    # Add the first pair
    top_positions.append(current_top)
    
    # Only add the first bottom if it doesn't collide with the top we just placed
    if (current_top - (current_bottom + size)) >= gap:
        bottom_positions.append(current_bottom)
    else:
        return [round(p, 4) for p in top_positions]

    # 2. Fill the middle "Ping-Pong" style
    while True:
        # Try to add another TOP block
        next_top = current_top - pitch
        # Distance between next_top and the last added bottom block
        if (next_top - (bottom_positions[-1] + size)) >= gap:
            top_positions.append(next_top)
            current_top = next_top
        else:
            break # No more room
            
        # Try to add another BOTTOM block
        next_bottom = current_bottom + pitch
        # Distance between the top block we just added and this next bottom
        if (top_positions[-1] - (next_bottom + size)) >= gap:
            bottom_positions.append(next_bottom)
            current_bottom = next_bottom
        else:
            break # No more room, but we keep the "extra top" block just added
            
    return sorted([round(p, 4) for p in (top_positions + bottom_positions)])

@gf.cell
def pmos_new(
    width: float = 0.15,
    length: float = 0.13,
    nf: int = 1,
    m: int = 1,
    guardring: bool = False,
    guardring_dist: int = 1,
    model: str = "sg13_lv_pmos",
) -> Component:
    c = Component()

    # 1. Validation
    if (width / nf) < TECH.pmos_min_width: raise ValueError(f"Width {width} < min")
    if length < TECH.pmos_min_length: raise ValueError(f"Length {length} < min")

    # 2. Layer Mapping
    layers = {
        'activ': (1, 0), 'metal1': (8, 0), 'psd': (14, 0),
        'nwell': (31, 0), 'gatpoly': (5, 0), 'cont': (6, 0),
        'text': (63, 0), 'heattrans': (51, 0), 'substrate': (40, 0),
        'nbulay': (32, 0)
    }

    # 3. Geometry Constants
    sd_width = 0.3  # Width of source/drain diffusion regions
    gate_spacing = 0.14 # Space between SD contact edge and Gate Poly
    gate_sd_spacing = 0.07 # Space between SD Active and Gate Poly
    if nf > 1:
        width = width / nf  # Divides the total width across the fingers

    # 4. Loop to Create Fingers
    # Total active width covers all SD regions and Gates
    total_active_x = (nf * length) + ((nf + 1) * sd_width) + (nf * gate_spacing)
    active_height = width #max(0.3, width)
    
    # Main Active Area
    strip = c.add_ref(gf.components.rectangle(size=(total_active_x, active_height), layer=layers['activ']))
    if width < 0.3:
        c.insts.remove(strip)
        strip = c.add_ref(gf.components.rectangle(size=(total_active_x, active_height), layer=layers['activ']))
        strip.move((0, (0.3 - active_height) / 2))

    for i in range(nf):
        # Calculate Gate Position
        # Gate i sits after i+1 SD regions and i gates
        gate_x = (i + 1) * sd_width + i * length + ((2*i + 1) * gate_sd_spacing)
        
        # Add Gate Poly
        g_poly = c.add_ref(gf.components.rectangle(size=(length, width + 0.36), layer=layers['gatpoly']))
        g_poly.move((gate_x, strip.ymin - 0.18))
        
        # Add Heat Trans
        c.add_ref(gf.components.rectangle(size=(length, width + 0.36), layer=layers['heattrans'])).move((gate_x, strip.ymin - 0.18))

    # 5. Loop to Create Source/Drain Contacts
    # There are always nf + 1 diffusion regions
    for i in range(nf + 1):
        sd_x = i * (sd_width + length + 2*gate_sd_spacing)

        # Add Source Drain Active Boxes
        active = c.add_ref(gf.components.rectangle(size=(0.3, 0.3), layer=layers['activ']))
        active.move((sd_x, 0))

        # Add Substrate Connection
        if i == nf:
            subst = c.add_ref(gf.components.rectangle(size=(0.3, 0.3), layer=layers['substrate']))
            subst.move((sd_x, 0))

        add_contact_column(c, sd_x, 0, width, layers)

    # 6. Enclosures (PSD and NWell)
    c_center = c.center
    psub_rect = gf.components.rectangle(
        size=(c.xmax - c.xmin + 0.36, c.ymax - c.ymin + 0.24), 
        layer=layers['psd']
    )
    psub = c.add_ref(psub_rect)
    psub.center = c_center

    # NWell
    nwell_rect = gf.components.rectangle(
        size=(psub.xsize + 0.26, max(0.92, psub.ysize + 0.02)), 
        layer=layers['nwell']
    )
    nwell = c.add_ref(nwell_rect)
    nwell.center = psub.center

    """# 7. Adding PCell Text (Made the PCell XOR comparison fail so commented out)
    c_center = c.center
    t1 = gf.components.text("pmos", size=0.08, layer=layers['text'])
    text1 = c.add_ref(t1)
    text1.xmin = psub.xmin + 0.02
    text1.ymin = psub.ymin + 0.02""" 

    # 8. Add Guard Ring if Specified
    if guardring == True:
        # Add Expanded NWell
        nwell2_rect = gf.components.rectangle(
            size=(nwell.xsize + 2 * (guardring_dist + 0.35), nwell.ysize + 2 * (guardring_dist + 0.35)), 
            layer=layers['nwell']
        )
        nwell2 = c.add_ref(nwell2_rect)
        nwell2.center = psub.center

        #Add Ring
        ring_x = nwell.xsize + guardring_dist*2
        ring_y = nwell.ysize + guardring_dist*2

        c.add_ref(gf.components.rectangle(size=(ring_x, 0.3), layer=layers['activ'])).move((nwell.xmin - guardring_dist, nwell.ymin - guardring_dist))        # Bottom Rectangle
        c.add_ref(gf.components.rectangle(size=(ring_x, 0.3), layer=layers['activ'])).move((nwell.xmin - guardring_dist, nwell.ymax + guardring_dist-0.3))    # Top Rectangle
        c.add_ref(gf.components.rectangle(size=(0.3, ring_y), layer=layers['activ'])).move((nwell.xmin - guardring_dist, nwell.ymin - guardring_dist))        # Left Rectangle
        c.add_ref(gf.components.rectangle(size=(0.3, ring_y), layer=layers['activ'])).move((nwell.xmax + guardring_dist-0.3, nwell.ymin - guardring_dist))    # Right Rectangle

        c.add_ref(gf.components.rectangle(size=(ring_x, 0.3), layer=layers['metal1'])).move((nwell.xmin - guardring_dist, nwell.ymin - guardring_dist))        # Bottom Rectangle
        c.add_ref(gf.components.rectangle(size=(ring_x, 0.3), layer=layers['metal1'])).move((nwell.xmin - guardring_dist, nwell.ymax + guardring_dist-0.3))    # Top Rectangle
        c.add_ref(gf.components.rectangle(size=(0.3, ring_y), layer=layers['metal1'])).move((nwell.xmin - guardring_dist, nwell.ymin - guardring_dist))        # Left Rectangle
        c.add_ref(gf.components.rectangle(size=(0.3, ring_y), layer=layers['metal1'])).move((nwell.xmax + guardring_dist-0.3, nwell.ymin - guardring_dist))    # Right Rectangle

        c.add_ref(gf.components.rectangle(size=(nwell2.xsize, 1), layer=layers['nbulay'])).move((nwell2.xmin, nwell2.ymin))        # Bottom Rectangle
        c.add_ref(gf.components.rectangle(size=(nwell2.xsize, 1), layer=layers['nbulay'])).move((nwell2.xmin, nwell2.ymax - 1))    # Top Rectangle
        c.add_ref(gf.components.rectangle(size=(1, nwell2.ysize), layer=layers['nbulay'])).move((nwell2.xmin, nwell2.ymin))        # Left Rectangle
        c.add_ref(gf.components.rectangle(size=(1, nwell2.ysize), layer=layers['nbulay'])).move((nwell2.xmax - 1, nwell2.ymin))    # Right Rectangle

        positions_x = generate_alternating_positions(ring_x)
        positions_y = generate_alternating_positions(ring_y)

        for x_pos in positions_x:
            c.add_ref(gf.components.rectangle(size=(0.16, 0.16), layer=layers['cont'])).move((nwell.xmin - guardring_dist + x_pos, nwell.ymin - guardring_dist + 0.07))
        for y_pos in positions_y:
            c.add_ref(gf.components.rectangle(size=(0.16, 0.16), layer=layers['cont'])).move((nwell.xmin - guardring_dist + 0.07, nwell.ymin - guardring_dist + y_pos))
        for x_pos in positions_x:
            c.add_ref(gf.components.rectangle(size=(0.16, 0.16), layer=layers['cont'])).move((nwell.xmin - guardring_dist + x_pos, nwell.ymax + guardring_dist-0.3 + 0.07))
        for y_pos in positions_y:
            c.add_ref(gf.components.rectangle(size=(0.16, 0.16), layer=layers['cont'])).move((nwell.xmax + guardring_dist-0.3 + 0.07, nwell.ymin - guardring_dist + y_pos))


    # 9. Adding multiple instances based on m
    top = Component()
    for i in range(m):
        # Calculate row and column index (Set 3 columns arbritrarily)
        col = i % 3
        row = i // 3
        
        # Create the reference
        ref = top.add_ref(c)
        
        # Calculate offsets based on child size + spacing
        x_offset = col * (c.xsize + 0.2)
        y_offset = row * (c.ysize + 0.2)
        
        # Move the reference
        ref.move((x_offset, y_offset))
    top.flatten()

    # VLSIR simulation metadata
    c.info["vlsir"] = {
        "model": model,
        "spice_type": "SUBCKT",
        "spice_lib": "sg13g2_moslv_mod.lib",
        "port_order": ["d", "g", "s", "b"],
        "port_map": {"D": "d", "G": "g", "S": "s"},
        "params": {
            "w": width * 1e-6,
            "l": length * 1e-6,
            "ng": nf,
            "m": m,
        },
    }

    return top

from ihp.cells import nmos, rfnmos, npn13G2, rsil, cmim, pmos

if __name__ == "__main__":
    # Test with 2 fingers
    c = gf.Component()
    new = pmos_new(width=0.3, length=0.13, nf=2, m=1, guardring=True, guardring_dist=1.5)
    c.add_ref(new)
    # x = pmos(width=0.3, length=0.13, nf=1, m=1)
    # old = c.add_ref(x)
    # old.move((2, 1))
    c.write_gds("testing_pcell.gds")
    c.show()