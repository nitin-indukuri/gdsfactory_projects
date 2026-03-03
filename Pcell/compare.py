"""import gdstk

# Load the two libraries
lib1 = gdstk.read_gds("singlemos.gds")
lib2 = gdstk.read_gds("testing_singlemos.gds")

# Get the top cells
top1 = lib1.top_level()[0]
top2 = lib2.top_level()[0]

# Perform a boolean XOR operation to find differences
# This creates a new cell containing only the parts that don't match
diff_polygons = gdstk.boolean(top1.polygons, top2.polygons, "xor")

# Save the differences to a new file
diff_lib = gdstk.Library()
diff_cell = diff_lib.new_cell("DIFF")
diff_cell.add(*diff_polygons)
diff_lib.write_gds("difference.gds")"""


import os
import pya

# Directory where this script lives (look for GDS files here)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def normalize_and_xor(file1, file2, output_file):
    path1 = os.path.join(_SCRIPT_DIR, file1) if not os.path.isabs(file1) else file1
    path2 = os.path.join(_SCRIPT_DIR, file2) if not os.path.isabs(file2) else file2
    out_path = os.path.join(_SCRIPT_DIR, output_file) if not os.path.isabs(output_file) else output_file
    layout = pya.Layout()
    layout.read(path1)
    layout.read(path2) 

    res_layout = pya.Layout()
    res_layout.dbu = layout.dbu
    res_top = res_layout.create_cell("XOR_NORMALIZED")

    cell1 = layout.cell(0)
    cell2 = layout.cell(1)

    # 1. Normalization Shift
    center1 = cell1.bbox().center()
    center2 = cell2.bbox().center()
    t1 = pya.Trans(pya.Vector(-center1.x, -center1.y))
    t2 = pya.Trans(pya.Vector(-center2.x, -center2.y))

    # --- TRACKER FLAG ---
    diff_found = False

    # 2. Layer Loop
    for layer_info in layout.layer_infos():
        l_idx = layout.layer(layer_info)
        
        reg1 = pya.Region(cell1.begin_shapes_rec(l_idx))
        reg2 = pya.Region(cell2.begin_shapes_rec(l_idx))

        reg1.transform(t1)
        reg2.transform(t2)

        xor_region = reg1 ^ reg2
        
        if not xor_region.is_empty():
            diff_found = True # We found a discrepancy!
            new_layer = res_layout.layer(layer_info)
            res_top.shapes(new_layer).insert(xor_region)
            print(f"Difference detected on Layer: {layer_info}")

    # --- FINAL CHECK ---
    if not diff_found:
        print("########################################")
        print("SUCCESS: Perfect match found (normalized)!")
        print("########################################")
    else:
        res_layout.write(out_path)
        print(f"XOR results written to {out_path}")

normalize_and_xor("singlemos.gds", "testing_singlemos.gds", "diff_result.gds")
normalize_and_xor("multimos.gds", "multimos2.gds", "diff2_result.gds")