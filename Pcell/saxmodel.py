import sax
from sax.models.rf import *
import jax
import jax.numpy as jnp
import matplotlib.pyplot as plt
import numpy as np

def mosfet_3port(gm=0.01, rds=1000, cgs=10e-15, cgd=2e-15, f=1e8, z0=50.0):
    omega = 2 * jnp.pi * f
    ygs = 1j * omega * cgs
    #ygs = admittance(f=f, y=ygs)
    ygd = 1j * omega * cgd
    #ygd = admittance(f=f, y=ygd)
    yds = 1 / rds
    #yds = admittance(f=f, y=yds)

    """ Small Signal Model of Mosfet:
    
               Cgd
        +------||-------+
        |               |
    G o1---+    +-------+-------o2 D
        |       |       |
        ---    / \      >
    Cgs ---   ( | ) gm  < Rds
        |      \ / Vgs  >
        |       |       |
        +-------+-------+
                |
              S o3
            
    """

    # Build Y-matrix from small-signal model
    Y = jnp.array([
        [ygs + ygd,      -ygd,           -ygs],
        [gm - ygd,       yds + ygd,      -(gm + yds)],
        [-(gm + ygs),    -yds,           ygs + yds + gm]
    ])

    # Standard Y to S conversion: S = (I - Z0*Y)(I + Z0*Y)^-1
    I = jnp.eye(3)
    z0_mat = I * (1/z0) # Normalizing to admittance
    # Note: Using jax.linalg.solve for numerical stability
    S = jnp.linalg.solve(I + z0 * Y, I - z0 * Y)

    # Map to SAX dictionary
    ports = ["G", "D", "S"]
    sdict = {}
    for i, p_out in enumerate(ports):
        for j, p_in in enumerate(ports):
            sdict[(p_out, p_in)] = S[i, j]
            
    return sdict


f = np.linspace(0, 1e9, 500)
# Collect S-params for each frequency
s_dg = np.array([mosfet_3port(gm=0.000131, rds=122100, cgs=213e-18, cgd=96e-18, f=fi, z0=50.0)[("D", "G")] for fi in f])
s_gd = np.array([mosfet_3port(gm=0.000131, rds=122100, cgs=213e-18, cgd=96e-18, f=fi, z0=50.0)[("G", "D")] for fi in f])
# ... same for other port pairs you need

plt.figure()
plt.plot(f / 1e9 , np.abs(s_dg), label="|S_DD| (S22)")
plt.plot(f / 1e9 , np.abs(s_gd), label="|S_GD| (S12)")
plt.legend()
plt.xlabel("Frequency (GHz)")
plt.ylabel("S-parameter") 
plt.title("Mosfet 3-port S-parameters")
# plt.show()


f = np.linspace(1e9, 10e9, 500)
s = sax.models.rf.impedance(f=f, z=50, z0=50)
plt.figure()
plt.plot(f / 1e9, np.abs(s[("o1", "o1")]), label="|S11|")
plt.plot(f / 1e9, np.abs(s[("o1", "o2")]), label="|S12|")
plt.plot(f / 1e9, np.abs(s[("o2", "o2")]), label="|S22|")
plt.title("Impedance")
plt.xlabel("Frequency [GHz]")
plt.ylabel("Magnitude")
plt.legend()
plt.show()