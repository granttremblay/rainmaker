#!/usr/bin/env python

"""
Map precipitation thresholds in Chandra X-ray observations of galaxy clusters.

Rainmaker maps the cooling-to-freefall time ratio as a function
of radius in Chandra X-ray observations of hot galaxy
cluster atmospheres. This first iteration uses the main data table
from the  ACCEPT sample: http://www.pa.msu.edu/astro/MC2/accept/

Projected radial X-ray temperature and pressure profiles
are fit in log space with 3rd-order polynomials. The logarithmic
pressure profile is then analytically differentiated to determine
the gravitational acceleration, from which rainmaker then derives
the freefall time. The cooling time is also computed from the
temperature profile.

Usage:
    $ python rainmaker.py [-f data_tab.txt -n "Name of cluster" -p show_plots]

Example:
    $ python rainmaker.py
    This will run the full sequence using Abell 2597 as an example.

    $ python rainmaker.py -f accept_main_table.txt -n "Centaurus"
    $ python rainmaker.py -n "Abell 2151"
    $ python rainmaker.py -p False # don't show plots
"""

import os
import time
import argparse

import numpy as np
import numpy.polynomial.polynomial as poly

from astropy.io import ascii
from astropy.table import QTable
import astropy.units as u
import astropy.constants as const

import matplotlib.pyplot as plt
import matplotlib.style as style

# Ignore sqrt warnings to keep interpreter clean
np.seterr(divide='ignore', invalid='ignore')

__author__ = "Dr. Grant R. Tremblay"
__license__ = "MIT"
__version__ = "0.1.0"
__maintainer__ = "Grant Tremblay"
__email__ = "grant.tremblay@yale.edu"
__status__ = "Development"


def parse_arguments():
    """Set up and parse command line arguments."""
    parser = argparse.ArgumentParser(description="Rainmaker fits ACCEPT profiles to quantify \
                                     parameters relevant to precipitation",
                                     usage="rainmaker.py -f table.txt -n name")

    parser.add_argument("-f", "--filename",
                        dest="filename",
                        required=False,
                        default="accept_main_table.txt",
                        help="input data table",
                        metavar="FILE",
                        type=lambda x: is_valid_file(parser, x))

    parser.add_argument("-n", "--name_of_cluster",
                        dest="name_of_cluster",
                        required=False,
                        default="Abell 2597",
                        help="Name of the cluster (default: Abell 2597)")

    parser.add_argument("-p", "--show_plots",
                        dest="show_plots",
                        required=False,
                        default=True,
                        help="Show plots upon running script?")

    args = parser.parse_args()
    filename = args.filename.name
    show_plots = args.show_plots

    # Be flexible with the cluster name.
    # If they entered a space, replace it with a '_',
    # then convert to UPPERCASE (to match ACCEPT table)

    cluster_name = args.name_of_cluster.replace(" ", "_").upper()

    return filename, cluster_name, show_plots


def is_valid_file(parser, arg):
    """Check to ensure existence of the file."""
    if not os.path.isfile(arg):
        parser.error("Cannot find that data table: {}".format(arg))
    else:
        print("\nTable found    |  {}".format(arg))
        return open(arg, 'r')      # return an open file handle


def parse_data_table(filename, cluster_name):
    """Match input cluster name to that in table, return that object's data."""
    data = ascii.read(filename)     # This creates a flexible Astropy TABLE

    # 'tcool5/2' is a bad column name. Change it if there.
    if 'tcool5/2' in data.columns:
        data.rename_column('tcool5/2', 'tcool52')

    # 'tcool3/2' is also a bad column name. Change it if there.
    if 'tcool3/2' in data.columns:
        data.rename_column('tcool3/2', 'tcool32')

    data = filter_by_cluster(data, cluster_name)

    data = assign_units(data)

    return data


def filter_by_cluster(data, cluster_name):
    """Take input astropy TABLE object."""
    obs_by_name = data.group_by('Name')
    clusters_in_table = obs_by_name.groups.keys

    cluster_found = cluster_name in clusters_in_table['Name']

    while not cluster_found:
        new_cluster_name = input("Cluster (" + cluster_name +
                                 ") not found, try again: ")

        messyname = (new_cluster_name.startswith('"') and
                     new_cluster_name.endswith('"'))

        # If the user entered quotation marks, strip them
        if messyname:
            cluster_name = new_cluster_name[1:-1].replace(' ', '_').upper()
        else:
            cluster_name = new_cluster_name.replace(' ', '_').upper()
        cluster_found = cluster_name in clusters_in_table['Name']

    if cluster_found:
        print("Cluster found  |  " + cluster_name)
        mask = data['Name'] == cluster_name
        masked_data = data[mask]
        return masked_data


def assign_units(data):
    """I need to write a docstring for this."""
    Name = data['Name']
    Rin = data['Rin'] * u.Mpc
    Rout = data['Rout'] * u.Mpc
    nelec = data['nelec'] * u.cm**(-3)
    neerr = data['neerr'] * u.cm**(-3)
    Kitpl = data['Kitpl'] * u.keV * u.cm**2
    Kflat = data['Kflat'] * u.keV * u.cm**2
    Kerr = data['Kerr'] * u.keV * u.cm**2
    Pitpl = data['Pitpl'] * u.dyne * u.cm**(-2)
    Perr = data['Perr'] * u.dyne * u.cm**(-2)
    Mgrav = data['Mgrav'] * u.M_sun
    Merr = data['Merr'] * u.M_sun
    Tx = data['Tx'] * u.keV
    Txerr = data['Txerr'] * u.keV
    Lambda = data['Lambda'] * u.erg * u.cm**3 / u.s
    tcool52 = data['tcool52'] * u.Gyr
    tcool52err = data['t52err'] * u.Gyr
    tcool32 = data['tcool32'] * u.Gyr
    tcool32err = data['t32err'] * u.Gyr

    names = ('Name', 'Rin', 'Rout', 'nelec', 'neerr', 'Kitpl',
             'Kflat', 'Kerr', 'Pitpl', 'Perr', 'Mgrav', 'Merr',
             'Tx', 'Txerr', 'Lambda', 'tcool52', 't52err',
             'tcool32', 't32err'
             )

    # Note, this is an astropy QTable instead of a Table, so
    # that I can preserve units. Read more here:
    # http://docs.astropy.org/en/stable/table/mixin_columns.html#quantity-and-qtable
    data = QTable(
        [Name, Rin, Rout, nelec, neerr, Kitpl,
         Kflat, Kerr, Pitpl, Perr, Mgrav, Merr,
         Tx, Txerr, Lambda, tcool52, tcool52err,
         tcool32, tcool32err], names=names
    )

    return data


def fit_polynomial(data, ln_xray_property, deg, whatIsFit):
    """Fit a DEG-order polynomial in x, y space.

    numpy.polynomial.polinomial.polyfit() returns coefficients,
    from 0th order first to N-th order last (note that this is
    *opposite* from how np.polyfit behaves!).
    """
    radiuspackage = extrapolate_radius(data)

    r = radiuspackage[0]
    ln_r = radiuspackage[1]
    r_fine = radiuspackage[2]
    ln_r_fine = radiuspackage[4]

    print("Now fitting    |" + "  " + make_number_ordinal(deg) +
          " order polynomial to " + whatIsFit)

    coeffs = poly.polyfit(ln_r, ln_xray_property, deg)

    # polyval() is used to assemble cubic fit:
    # $p(x) = c_0 + c_1 x + c_2 x^2 + c3 x^3$
    # where c_n are the coeffs returned by polyfit()
    ln_fit = poly.polyval(ln_r, coeffs)
    fit = np.exp(ln_fit)

    # Now use these coefficients to extrapolate fit
    # across larger radius

    ln_fit_fine = poly.polyval(ln_r_fine, coeffs)
    fit_fine = np.exp(ln_fit_fine)

    fitpackage = (fit, r, fit_fine, r_fine, coeffs)

    return fitpackage


def extrapolate_radius(data):
    """The ACCEPT radii are finite. Fix that."""
    r = (data['Rin'] + data['Rout']) * 0.5
    ln_r = np.log(r.value)
    # this is the NATURAL logarithm, ln

    # Generate the radii you wish to extrapolate
    # across in log10 space
    log10_r_fine = np.arange(300.) / 100. - 3.

    # Now un-log10 it, give it a unit
    r_fine = (10**log10_r_fine) * u.Mpc

    # Also give its unitless natural log, used for fitting
    # with polyval() and fit_polynomial()'s coefficients
    ln_r_fine = np.log(r_fine.value)

    radiuspackage = (r, ln_r, r_fine, log10_r_fine, ln_r_fine)

    return radiuspackage


def logTemp_fit(data):
    """Fit the Temperature profile in log space.

    Fit the logarithmic electron density profile ln(n_e) (in cm^-3)
    to a polynomial in log r (in Mpc) of degree 'deg'. Plot it.
    """
    whatIsFit = "log temperature profile"

    # I think the temperature fit should be 2nd order, as a 3rd order.
    # This is a change from Mark's code, which fits a 3rd order polynomial
    # (that then rises sharply at small radii).
    deg = 2

    ln_t = np.log(data['Tx'].value)
    ln_terr = np.log(data['Txerr'] / data['Tx'])

    upperbound = data['Tx'] + data['Txerr']
    lowerbound = data['Tx'] - data['Txerr']

    fitpackage = fit_polynomial(data, ln_t, deg, whatIsFit)

    temp_fit = fitpackage[0]
    r = fitpackage[1]
    temp_fit_fine = fitpackage[2]
    r_fine = fitpackage[3]
    temp_coeffs = fitpackage[4]

    temp_fit = temp_fit * u.keV
    temp_fit_fine = temp_fit_fine * u.keV

    plotter(r.to(u.kpc),
            data['Tx'],
            r_fine.to(u.kpc),
            temp_fit,
            temp_fit_fine,
            lowerbound,
            upperbound,
            xlog=True,
            ylog=False,
            xlim=(1, 100),  # Example: (1, 100)
            ylim=(1, 5),
            xlabel="Cluster-centric Radius (kpc)",
            ylabel="Projected X-ray Temperature (keV)",
            title="Temperature Fit",
            file="temperature.pdf",
            save=False
            )

    temppackage = {'temp_coeffs': temp_coeffs,
                   'temp_fit': temp_fit,
                   'temp_fit_fine': temp_fit_fine,
                   'ln_terr': ln_terr}

    return temppackage


def logPressure_fit(data):
    """Fit the logarithmic electron density profile.

    Fit the logarithmic electron density profile ln(n_e) (in cm^-3)
    to a polynomial in log r (in Mpc) of degree 'deg'. Plot it.
    """
    whatIsFit = "log pressure profile"

    # plot_save_file = "pressure.pdf"

    deg = 3

    ln_p = np.log(data['Pitpl'].value)
    ln_perr = np.log(data['Perr'] / data['Pitpl'])

    upperbound = data['Pitpl'] + data['Perr']
    lowerbound = data['Pitpl'] - data['Perr']

    fitpackage = fit_polynomial(data, ln_p, deg, whatIsFit)

    pressure_fit = fitpackage[0]
    r = fitpackage[1]
    pressure_fit_fine = fitpackage[2]
    r_fine = fitpackage[3]
    pressure_coeffs = fitpackage[4]

    pressure_fit = pressure_fit * u.dyne * u.cm**(-2)
    pressure_fit_fine = pressure_fit_fine * u.dyne * u.cm**(-2)

    plotter(r.to(u.kpc),
            data['Pitpl'],
            r_fine.to(u.kpc),
            pressure_fit,
            pressure_fit_fine,
            lowerbound,
            upperbound,
            xlog=True,
            ylog=True,
            xlim=None,
            ylim=None,
            xlabel="Cluster-centric Radius (kpc)",
            ylabel=r'Projected X-ray Pressure (erg cm$^{-3}$)',
            title="Pressure Fit",
            file="pressure.pdf",
            save=False
            )

    pressurepackage = {'pressure_coeffs': pressure_coeffs,
                       'pressure_fit': pressure_fit,
                       'pressure_fit_fine': pressure_fit_fine,
                       'ln_perr': ln_perr
                       }

    return pressurepackage


def grav_accel(data):
    """Compute the gravitational acceleration from the T and P profiles."""
    temppackage = logTemp_fit(data)
    pressurepackage = logPressure_fit(data)
    radiuspackage = extrapolate_radius(data)

    temp_fit = temppackage['temp_fit']
    temp_fit_fine = temppackage['temp_fit_fine']
    ln_terr = temppackage['ln_terr']

    pressure_coeffs = pressurepackage['pressure_coeffs']
    ln_perr = pressurepackage['ln_perr']

    r = radiuspackage[0]
    ln_r = radiuspackage[1]
    r_fine = radiuspackage[2]
    log10_r_fine = radiuspackage[3]
    ln_r_fine = radiuspackage[4]

    # Assign the dlnp_dlnr array with same length as radius array
    dlnp_dlnr = np.zeros(np.shape(ln_r))
    for i in np.arange(1, 4):
        dlnp_dlnr = dlnp_dlnr + \
            float(i) * pressure_coeffs[i] * ln_r**(float(i - 1))

    dlnp_dlnr_fine = np.zeros(np.shape(ln_r_fine))
    for i in np.arange(1, 4):
        dlnp_dlnr_fine = dlnp_dlnr_fine + \
            float(i) * pressure_coeffs[i] * ln_r_fine**(float(i - 1))

    mu_mp = const.m_p.to(u.g)  # Proton mass 1.67e-24 g

    rg = - temp_fit.to(u.erg) / mu_mp * dlnp_dlnr
    rg_fine = -temp_fit_fine.to(u.erg) / mu_mp * dlnp_dlnr_fine

    relerr = np.sqrt(2. * np.exp(ln_perr)**2 + np.exp(ln_terr)**2)
    rgerr = (temp_fit.to(u.erg) / mu_mp) * relerr

    lowerbound = rg - rgerr
    upperbound = rg + rgerr

    plotter(r.to(u.kpc),
            None,
            r_fine.to(u.kpc),
            rg,
            rg_fine,
            lowerbound,
            upperbound,
            xlog=True,
            ylog=False,
            xlim=(1.0, 100.),
            ylim=(1.0e13, 1.2e16),
            xlabel="Cluster-centric radius",
            ylabel=r'$rg$ (cm$^2$ s$^{-2}$)',
            title="Gravitational acceleration",
            file="pressure.pdf",
            save=False)

    # Return everything you need for the rest of the code
    rgpackage = {'r': r, 'ln_r': ln_r, 'r_fine': r_fine,
                 'log10_r_fine': log10_r_fine, 'ln_r_fine': ln_r_fine,
                 'rg': rg, 'rg_fine': rg_fine, 'rgerr': rgerr
                 }

    return rgpackage, temppackage, pressurepackage, radiuspackage


def coolingFunction(kT):
    r"""
    Implement the Tozzi & Norman (2001) cooling function.

    This is an analytic fit to Sutherland & Dopita (1993), shown
    in Equation 16 of Parrish, Quataert, & Sharma (2009),
    as well as Guo & Oh (2014).

    See here: arXiv:0706.1274. The equation is:

    $\Lambda(T) = [C_1 \left( \frac{k_B T}{\mathrm{keV}} \right)^{-1.7}
                  + C_2\left( \frac{k_B T}{\mathrm{keV}} \right)^{0.5}
                  + C_3] \times 10^{-22}$
    """
    # For a metallicity of Z = 0.3 Z_solar,
    C1 = 8.6e-3
    C2 = 5.8e-2
    C3 = 6.3e-2

    alpha = -1.7
    beta = 0.5

    # kT.value is supposed to be unitless,
    # the kT in the real equation is divided by keV. I'm not cheating!
    coolingFunction = (C1 * kT.value**alpha
                       + C2 * kT.value**beta
                       + C3
                       ) * 1.0e-22 * (u.erg * u.cm**3 / u.s)

    return coolingFunction


def timescales(data):
    """
    Compute the cooling and freefall timescales.

    Do this from the log temperature and pressure profiles,
    as well as the Tozzi & Norman cooling function.
    """
    rgpackage, temppackage, pressurepackage, radiuspackage = grav_accel(data)

    # Compute the freefall time
    tff = np.sqrt(2.0 / rgpackage['rg']) * rgpackage['r']
    tff_fine = np.sqrt(2.0 / rgpackage['rg_fine']) * rgpackage['r_fine']

    # Compute the cooling time

    # Electron number density in units of cm**-3
    nelec = pressurepackage['pressure_fit'] / (temppackage['temp_fit'])
    nelec_fine = pressurepackage[
        'pressure_fit_fine'] / (temppackage['temp_fit_fine'])
    # See eqn 4 here: https://arxiv.org/pdf/astro-ph/0608423.pdf

    # Then the cooling time (via Cavagnolo+08) is
    # tcool = (3/2 nkT)/(ne np Lambda(T,Z))
    capital_lambda = coolingFunction(temppackage['temp_fit'])
    capital_lambda_fine = coolingFunction(temppackage['temp_fit_fine'])

    # What is all of this?! See Eqn. 35 here: See here: arXiv:0706.1274.
    tcool = ((3 / 2) *
             (1.89 * pressurepackage['pressure_fit']) / (nelec**2 / 1.07) /
             capital_lambda
             )
    tcool_fine = ((3 / 2) *
                  (1.89 * pressurepackage['pressure_fit_fine']) /
                  (nelec_fine**2 / 1.07) / capital_lambda_fine
                  )

    precip_ratio_fine = tcool_fine.to(u.yr) / tff_fine.to(u.yr)

    plt.figure()

    # Plot the freefall time
    plt.plot(rgpackage['r'].to(u.kpc), tff.to(u.yr), label='Freefall Time',
             color=plt.rcParams['axes.prop_cycle'].by_key()['color'][0])
    plt.plot(rgpackage['r_fine'].to(u.kpc), tff_fine.to(u.yr), linestyle='--',
             color=plt.rcParams['axes.prop_cycle'].by_key()['color'][0])

    # Plot the (various) coooling times
    plt.plot(rgpackage['r'].to(u.kpc),
             (tcool.to(u.yr)),
             label='Cooling Time',
             color=plt.rcParams['axes.prop_cycle'].by_key()['color'][1]
             )

    plt.plot(rgpackage['r_fine'].to(u.kpc),
             (tcool_fine.to(u.yr)),
             linestyle='--',
             color=plt.rcParams['axes.prop_cycle'].by_key()['color'][1]
             )

    plt.fill_between(rgpackage['r'].to(u.kpc).value,
                     data['tcool52'].to(u.yr).value,
                     data['tcool32'].to(u.yr).value,
                     facecolor='gray', alpha=0.5,
                     label='Enthalpy / Energy difference'
                     )

    ax = plt.gca()
    ax.set_yscale('log')
    ax.set_xscale('log')
    plt.xlabel("Radius")
    plt.ylabel("yr")
    plt.title("Freefall & Cooling Time")
    plt.legend()

    plt.draw()

    plt.figure()

    # Plot the freefall time
    plt.plot(rgpackage['r_fine'].to(u.kpc), precip_ratio_fine,
             label=r't$_{\mathrm{cool}}$ / t$_{\mathrm{freefall}}$')
    ax = plt.gca()
    ax.set_yscale('log')
    ax.set_xscale('log')
    plt.xlabel("Radius")
    plt.ylabel(r'T')
    plt.title("Freefall & Cooling Time")
    plt.legend()


def plotter(x, y, x_fine, fit, fit_fine, lowerbound, upperbound,
            xlog=True, ylog=True, xlim=None, ylim=None,
            xlabel="Set your X-label!", ylabel="Set your y label!",
            title="Set your title!", file="temp.pdf", save=False):
    """Make plots pretty."""
    style.use('ggplot')

    plt.rcParams['font.size'] = 12
    plt.rcParams['axes.labelsize'] = 12
    plt.rcParams['xtick.labelsize'] = 12
    plt.rcParams['ytick.labelsize'] = 12

    plt.figure()

    # Only plot datapoints if I gave you datapoints
    if y is not None:
        plt.plot(x, y, marker='o', markersize=10, linestyle='None')

    # Plot a nice error shadow
    if lowerbound is not None:
        plt.fill_between(x.value, lowerbound.value, upperbound.value,
                         facecolor='gray', alpha=0.5)

    plt.plot(x, fit)
    plt.plot(x_fine, fit_fine, linestyle='--')

    # Fiddle with axes, etc.
    ax = plt.gca()

    if xlog:
        ax.set_xscale('log')
    if ylog:
        ax.set_yscale('log')

    if xlim is not None:
        ax.set_xlim(xlim)
    if ylim is not None:
        ax.set_ylim(ylim)

    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title)

    # Show and save plots
    plt.draw()


def make_number_ordinal(number):
    """Take number, turn into ordinal. E.g., '2' --> '2nd'."""
    suffixes = {1: 'st', 2: 'nd', 3: 'rd'}

    if 10 <= number % 100 <= 20:
        suffix = 'th'
    else:
        # the second parameter is a default.
        suffix = suffixes.get(number % 10, 'th')
    return str(number) + suffix


def rainmaker_notebook_init(filename, cluster_name):
    """Run this in a Jupyter Notebook for exploration."""
    data = parse_data_table(filename, cluster_name.replace(" ", "_").upper())

    return data


def main():
    """The main program runs the whole sequence."""
    # Parse command line arguments. Iterate with user if cluster not found.
    filename, cluster_name, show_plots = parse_arguments()

    # DATA is an astropy TABLE object,
    # filtered to show all properties of a given cluster
    # Can be split by e.g. data['Rin'], data['Mgrav'], etc.
    data = parse_data_table(filename, cluster_name)

    # grav_accel(data)
    timescales(data)


if __name__ == '__main__':
    start_time = time.time()
    main()
    runtime = round((time.time() - start_time), 3)
    print("Finished in    |  {} seconds".format(runtime))

    print("Showing plots  |")

    plt.show()
