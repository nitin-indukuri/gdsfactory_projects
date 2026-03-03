import sax
import jax
import jax.numpy as jnp

def mosfet_3port(gm=0.01, rds=1000, cgs=10e-15, cgd=2e-15, f=1e9, z0=50.0):
    omega = 2 * jnp.pi * f
    ygs = 1j * omega * cgs
    ygd = 1j * omega * cgd
    yds = 1 / rds

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

sdicts = mosfet_3port()
print(sdicts)