import numpy as np
import astropy.units as u
from astropy.constants import M_sun
from agnpy.emission_regions import Blob
from agnpy.targets import CMB, SSDisk, SphericalShellBLR, RingDustTorus
from agnpy.utils.plot import load_mpl_rc
import matplotlib.pyplot as plt
from pathlib import Path
from utils import time_function_call

# parameters of the accretion disk
M_BH = 1.2 * 1e9 * M_sun
L_disk = 2e46 * u.Unit("erg s-1")
eta = 1 / 12
R_tilde_in = 6
R_tilde_out = 200

# blob definition
spectrum_norm = 6e42 * u.erg
parameters = {
    "p1": 2.0,
    "p2": 3.5,
    "gamma_b": 1e4,
    "gamma_min": 20,
    "gamma_max": 5e7,
}
spectrum_dict = {"type": "BrokenPowerLaw", "parameters": parameters}
R_b = 1e16 * u.cm
B = 0.56 * u.G
z = 1
delta_D = 40
Gamma = 40
blob = Blob(R_b, z, delta_D, Gamma, B, spectrum_norm, spectrum_dict)

# add CMB and the photon density of the synchrotron radiation for comparison
cmb = CMB(z=blob.z)
disk = SSDisk(M_BH, L_disk, eta, R_tilde_in, R_tilde_out, R_g_units=True)
blr = SphericalShellBLR(L_disk, 0.024, "Lyalpha", 1.1e17 * u.cm)
dt = RingDustTorus(L_disk, 0.1, 1000 * u.K)

# compute the energy densities at several distances
r = np.logspace(15, 21) * u.cm

u_cmb = cmb.u(blob)
# time only the function call of densities computed over different distances
u_disk = time_function_call(disk.u, r, blob)
u_blr = time_function_call(blr.u, r, blob)
u_dt = time_function_call(dt.u, r, blob)
u_syn = blob.u_ph_synch

# plot
load_mpl_rc()
plt.rcParams["text.usetex"] = True
fig, ax = plt.subplots()
u_label = r"$u'\,/\,({\rm erg}\,{\rm cm}^{-3})$"
r_label = r"$r\,/\,{\rm cm}$"
ax.axhline(u_cmb.to_value("erg cm-3"), lw=2, color="k", label="CMB")
ax.loglog(r, u_disk, lw=2, color="crimson", label="disk")
ax.loglog(r, u_blr, lw=2, color="dodgerblue", label="broad line region")
ax.loglog(r, u_dt, lw=2, color="goldenrod", label="dust torus")
ax.axhline(
    blob.U_B.to_value("erg cm-3"),
    lw=2,
    ls="--",
    color="lightseagreen",
    label="magnetic field",
)
ax.axhline(
    blob.u_ph_synch.to_value("erg cm-3"),
    lw=2,
    ls=":",
    color="lightseagreen",
    label="synchrotron",
)
ax.legend(loc="best")
ax.set_xlabel(r_label, fontsize=12)
ax.set_ylabel(u_label, fontsize=12)
Path("figures").mkdir(exist_ok=True)
fig.savefig("figures/figure_3.png")
fig.savefig("figures/figure_3.pdf")
