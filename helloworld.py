import gdsfactory as gf
from ihp import PDK
from ihp.cells import nmos, rfnmos, npn13G2, rsil, cmim
from ihp.tech import LAYER

PDK.activate()


# Create a new component
c = gf.Component()

# Add a rectangle
r = gf.components.rectangle(size=(10, 10), layer=(1, 0))
rect = c.add_ref(r)

# Add text elements
t1 = gf.components.text("Hello", size=10, layer=(2, 0))
t2 = gf.components.text("Nitin Indukuri", size=10, layer=(2, 0))

text1 = c.add_ref(t1)
text2 = c.add_ref(t2)

# Position elements
text1.xmin = rect.xmax + 35
text2.xmin = rect.xmax + 5
text2.ymax = text1.ymin - 5
text2.rotate(0)

# Show the result
c.show()