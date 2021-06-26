# general modules
import logging
import pkg_resources
from pathlib import Path
import numpy as np
import astropy.units as u
from astropy.constants import c
from astropy.table import Table
from astropy.coordinates import Distance
import matplotlib.pyplot as plt
from utils import time_function_call

# import agnpy classes
from agnpy.emission_regions import Blob
from agnpy.spectra import BrokenPowerLaw
from agnpy.synchrotron import Synchrotron
from agnpy.compton import SynchrotronSelfCompton
from agnpy.utils.plot import load_mpl_rc, sed_x_label, sed_y_label

# import sherpa classes
from sherpa.models import model
from sherpa import data
from sherpa.fit import Fit
from sherpa.stats import Chi2
from sherpa.optmethods import LevMar
from sherpa.estmethods import Confidence
from sherpa.plot import IntervalProjection


class AgnpySSC(model.RegriddableModel1D):
    """Wrapper of agnpy's synchrotron and SSC classes. 
    A broken power law is assumed for the electron spectrum.
    To limit the span of the parameters space, we fit the log10 of the parameters 
    whose range is expected to cover several orders of magnitudes (normalisation, 
    gammas, size and magnetic field of the blob). 
    """

    def __init__(self, name="ssc"):

        # EED parameters
        self.log10_k_e = model.Parameter(name, "log10_k_e", -2.0, min=-20.0, max=10.0)
        self.p1 = model.Parameter(name, "p1", 2.1, min=-2.0, max=5.0)
        self.p2 = model.Parameter(name, "p2", 3.1, min=-2.0, max=5.0)
        self.log10_gamma_b = model.Parameter(name, "log10_gamma_b", 3, min=1, max=6)
        self.log10_gamma_min = model.Parameter(name, "log10_gamma_min", 1, min=0, max=4)
        self.log10_gamma_max = model.Parameter(name, "log10_gamma_max", 5, min=4, max=8)
        # source general parameters
        self.z = model.Parameter(name, "z", 0.1, min=0.01, max=1)
        self.d_L = model.Parameter(name, "d_L", 1e27, min=1e25, max=1e33, units="cm")
        # emission region parameters
        self.delta_D = model.Parameter(name, "delta_D", 10, min=0, max=40)
        self.log10_B = model.Parameter(name, "log10_B", -2, min=-4, max=2)
        self.t_var = model.Parameter(
            name, "t_var", 600, min=10, max=np.pi * 1e7, units="s"
        )

        model.RegriddableModel1D.__init__(
            self,
            name,
            (
                self.log10_k_e,
                self.p1,
                self.p2,
                self.log10_gamma_b,
                self.log10_gamma_min,
                self.log10_gamma_max,
                self.z,
                self.d_L,
                self.delta_D,
                self.log10_B,
                self.t_var,
            ),
        )

    def calc(self, pars, x):
        """evaluate the model calling the agnpy functions"""
        (
            log10_k_e,
            p1,
            p2,
            log10_gamma_b,
            log10_gamma_min,
            log10_gamma_max,
            z,
            d_L,
            delta_D,
            log10_B,
            t_var,
        ) = pars
        # add units, scale quantities
        x *= u.Hz
        k_e = 10 ** log10_k_e * u.Unit("cm-3")
        gamma_b = 10 ** log10_gamma_b
        gamma_min = 10 ** log10_gamma_min
        gamma_max = 10 ** log10_gamma_max
        B = 10 ** log10_B * u.G
        d_L *= u.cm
        R_b = c.to_value("cm s-1") * t_var * delta_D / (1 + z) * u.cm
        sed_synch = Synchrotron.evaluate_sed_flux(
            x,
            z,
            d_L,
            delta_D,
            B,
            R_b,
            BrokenPowerLaw,
            k_e,
            p1,
            p2,
            gamma_b,
            gamma_min,
            gamma_max,
        )
        sed_ssc = SynchrotronSelfCompton.evaluate_sed_flux(
            x,
            z,
            d_L,
            delta_D,
            B,
            R_b,
            BrokenPowerLaw,
            k_e,
            p1,
            p2,
            gamma_b,
            gamma_min,
            gamma_max,
        )
        return sed_synch + sed_ssc


logging.info("reading Mrk421 SED from agnpy datas")
sed_path = pkg_resources.resource_filename("agnpy", "data/mwl_seds/Mrk421_2011.ecsv")
sed_table = Table.read(sed_path)
x = sed_table["nu"]
y = sed_table["nuFnu"]
y_err_stat = sed_table["nuFnu_err"]
# array of systematic errors, will just be summed in quadrature to the statistical error
# we assume
# - 15% on gamma-ray instruments
# - 10% on lower waveband instruments
y_err_syst = np.zeros(len(x))
gamma = x > (0.1 * u.GeV).to("Hz", equivalencies=u.spectral())
y_err_syst[gamma] = 0.15
y_err_syst[~gamma] = 0.10
y_err_syst = y * y_err_syst
# remove the points with orders of magnitude smaller error, they are upper limits
UL = y_err_stat < (y * 1e-3)
x = x[~UL]
y = y[~UL]
y_err_stat = y_err_stat[~UL]
y_err_syst = y_err_syst[~UL]
# define the data1D object containing it
sed = data.Data1D("sed", x, y, staterror=y_err_stat, syserror=y_err_syst)

# declare a model
agnpy_ssc = AgnpySSC()
# initialise parameters
# parameters from Table 4 and Figure 11 of Abdo 2011
R_b = 5.2 * 1e16 * u.cm
z = 0.0308
d_L = Distance(z=z).to("cm")
# - AGN parameters
agnpy_ssc.z = z
agnpy_ssc.z.freeze()
agnpy_ssc.d_L = d_L.cgs.value
agnpy_ssc.d_L.freeze()
# - blob parameters
agnpy_ssc.delta_D = 18
agnpy_ssc.delta_D.freeze()
agnpy_ssc.log10_B = -1.3
agnpy_ssc.log10_B.freeze()
agnpy_ssc.t_var = (1 * u.d).to_value("s")
agnpy_ssc.t_var.freeze()
# - EED
agnpy_ssc.log10_k_e = -7.9
agnpy_ssc.p1 = 2.02
agnpy_ssc.p2 = 3.43
agnpy_ssc.log10_gamma_b = 5
agnpy_ssc.log10_gamma_min = np.log10(500)
agnpy_ssc.log10_gamma_min.freeze()
agnpy_ssc.log10_gamma_max = np.log10(1e6)
agnpy_ssc.log10_gamma_max.freeze()


logging.info("performing the fit and estimating the error on the parameters")
# directory to store the checks performed on the fit
fit_check_dir = "figures/figure_6_checks_sherpa_fit"
Path(fit_check_dir).mkdir(parents=True, exist_ok=True)
# fit using the Levenberg-Marquardt optimiser
fitter = Fit(sed, agnpy_ssc, stat=Chi2(), method=LevMar())
# use confidence to estimate the errors
fitter.estmethod = Confidence()
fitter.estmethod.parallel = True
min_x = 1e11 * u.Hz
max_x = 1e30 * u.Hz
sed.notice(min_x, max_x)

logging.info("first fit iteration with only EED parameters thawed")
results_1 = time_function_call(fitter.fit)
print("fit succesful?", results_1.succeeded)
print(results_1.format())

logging.info("second fit iteration with EED and blob parameters thawed")
agnpy_ssc.delta_D.thaw()
agnpy_ssc.log10_B.thaw()
results_2 = time_function_call(fitter.fit)
print("fit succesful?", results_2.succeeded)
print(results_2.format())
# plot final model without components
nu = np.logspace(10, 30, 300)
plt.errorbar(sed.x, sed.y, yerr=sed.get_error(), marker=".", ls="")
plt.loglog(nu, agnpy_ssc(nu))
plt.xlabel(sed_x_label)
plt.ylabel(sed_y_label)
plt.savefig(f"{fit_check_dir}/best_fit.png")
plt.close()

logging.info(f"computing statistics profiles")
final_stat = fitter.calc_stat()
for par in agnpy_ssc.pars:
    if par.frozen == False:
        logging.info(f"computing statistics profile for {par.name}")
        proj = IntervalProjection()
        time_function_call(proj.calc, fitter, par)
        plt.plot(proj.x, proj.y - final_stat)
        plt.axhline(1, ls="--", color="orange")
        plt.xlabel(par.name)
        plt.ylabel(r"$\Delta\chi^2$")
        plt.savefig(f"{fit_check_dir}/chi2_profile_parameter_{par.name}.png")
        plt.close()

logging.info(f"estimating errors with confidence intervals")
errors_2 = time_function_call(fitter.est_errors())
print(errors_2.format())

logging.info("plot the final model with the individual components")
k_e = 10 ** agnpy_ssc.log10_k_e.val * u.Unit("cm-3")
p1 = agnpy_ssc.p1.val
p2 = agnpy_ssc.p2.val
gamma_b = 10 ** agnpy_ssc.log10_gamma_b.val
gamma_min = 10 ** agnpy_ssc.log10_gamma_min.val
gamma_max = 10 ** agnpy_ssc.log10_gamma_max.val
B = 10 ** agnpy_ssc.log10_B.val * u.G
delta_D = agnpy_ssc.delta_D.val
R_b = c.to_value("cm s-1") * agnpy_ssc.t_var.val * delta_D / (1 + z) * u.cm
parameters = {
    "p1": p1,
    "p2": p2,
    "gamma_b": gamma_b,
    "gamma_min": gamma_min,
    "gamma_max": gamma_max,
}
spectrum_dict = {"type": "BrokenPowerLaw", "parameters": parameters}
blob = Blob(
    R_b, z, delta_D, delta_D, B, k_e, spectrum_dict, spectrum_norm_type="differential"
)
print("jet power in particles", blob.P_jet_e)
print("jet power in B", blob.P_jet_B)

# compute the obtained emission region
synch = Synchrotron(blob)
ssc = SynchrotronSelfCompton(blob)
# make a finer grid to compute the SED
nu = np.logspace(10, 30, 300) * u.Hz
synch_sed = synch.sed_flux(nu)
ssc_sed = ssc.sed_flux(nu)

load_mpl_rc()
plt.rcParams["text.usetex"] = True
fig, ax = plt.subplots()
ax.loglog(
    nu / (1 + z),
    synch_sed + ssc_sed,
    ls="-",
    lw=2.1,
    color="crimson",
    label="agnpy, total",
)
ax.loglog(
    nu / (1 + z),
    synch_sed,
    ls="--",
    lw=1.3,
    color="goldenrod",
    label="agnpy, synchrotron",
)
ax.loglog(
    nu / (1 + z), ssc_sed, ls="--", lw=1.3, color="dodgerblue", label="agnpy, SSC"
)
# systematics error in gray
ax.errorbar(
    sed.x, sed.y, yerr=sed.get_syserror(), marker=",", ls="", color="gray",
)
# statistics error in gray
ax.errorbar(
    sed.x,
    sed.y,
    yerr=sed.get_staterror(),
    marker=".",
    ls="",
    color="k",
    label="Mrk 421, Abdo et al. (2011)",
)
ax.set_xlabel(sed_x_label)
ax.set_ylabel(sed_y_label)
ax.set_xlim([1e9, 1e29])
ax.set_ylim([1e-14, 1e-9])
ax.legend(loc="best")
plt.show()
fig.savefig("figures/figure_6_sherpa_fit.png")
fig.savefig("figures/figure_6_sherpa_fit.pdf")
