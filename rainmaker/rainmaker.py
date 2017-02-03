"""/usr/bin/env python"""

'''
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
    $ python rainmaker.py [-f data_table.txt -n "Name of cluster" -p show_plots]

Example:
    $ python rainmaker.py
    This will run the full sequence using Abell 2597 as an example.

    $ python rainmaker.py -f accept_main_table.txt -n "Centaurus"
    $ python rainmaker.py -n "Abell 2151"
    $ python rainmaker.py -p False # don't show plots
'''

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


__author__ = "Dr. Grant R. Tremblay"
__license__ = "MIT"
__version__ = "0.1.0"
__maintainer__ = "Grant Tremblay"
__email__ = "grant.tremblay@yale.edu"
__status__ = "Development"


def parse_arguments():
    '''Set up and parse command line arguments.'''

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
    '''Check to ensure existence of the file.'''
    if not os.path.isfile(arg):
        parser.error("Cannot find that data table: {}".format(arg))
    else:
        print("\nTable found    |  {}".format(arg))
        return open(arg, 'r')      # return an open file handle


def parse_data_table(filename, cluster_name):
    '''Match input cluster name to that in table, return that object's data'''
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
    '''Takes input astropy TABLE object'''

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

    # I could probably do this in a more intelligent manner,
    # but I want to assign units in a clear way!

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

    # Yes, I know I could do this in a for loop. But I want to
    # enable granular control over what columns are ultimately
    # written into the final "Science-ready" data table.

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
    '''
    Fits a DEG-order polynomial in x, y space.
    A 3rd order polynomial is a cubic function

    poly.polyfit() returns coefficients, from 0th
    order first to N-th order last (note that this is
    *opposite* from how np.polyfit behaves!).
    '''
    r, ln_r, r_fine, log10_r_fine, ln_r_fine = extrapolate_radius(data)

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

    return fit, r, fit_fine, r_fine, coeffs


def extrapolate_radius(data):
    '''
    The ACCEPT radii are finite. Fix that.
    '''

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

    return r, ln_r, r_fine, log10_r_fine, ln_r_fine


def logTemp_fit(data):
    '''
    Fit the logarithmic electron density profile ln(n_e) (in cm^-3)
    to a polynomial in log r (in Mpc) of degree 'deg'. Plot it.
    '''
    whatIsFit = "log temperature profile"

    deg = 3

    ln_t = np.log(data['Tx'].value)
    ln_terr = np.log(data['Txerr'] / data['Tx'])

    upperbound = data['Tx'] + data['Txerr']
    lowerbound = data['Tx'] - data['Txerr']

    temp_fit, r, temp_fit_fine, r_fine, temp_coeffs = fit_polynomial(
        data, ln_t, deg, whatIsFit)

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
            ylog=True,
            xlim=(1, 100),  # Example: (1, 100)
            ylim=None,
            xlabel="Cluster-centric Radius (kpc)",
            ylabel="Projected X-ray Temperature (keV)",
            title="Temperature Fit",
            file="temperature.pdf",
            save=False
            )

    return temp_coeffs, temp_fit, temp_fit_fine, ln_terr


def logPressure_fit(data):
    '''
    Fit the logarithmic electron density profile ln(n_e) (in cm^-3)
    to a polynomial in log r (in Mpc) of degree 'deg'. Plot it.
    '''
    whatIsFit = "log pressure profile"
    whatIsPlot = "Projected X-ray Pressure"

    plot_save_file = "pressure.pdf"

    deg = 3

    ln_p = np.log(data['Pitpl'].value)
    ln_perr = np.log(data['Perr'] / data['Pitpl'])

    upperbound = data['Pitpl'] + data['Perr']
    lowerbound = data['Pitpl'] - data['Perr']

    pressure_fit, r, pressure_fit_fine, r_fine, pressure_coeffs = fit_polynomial(data,
                                                                                 ln_p,
                                                                                 deg,
                                                                                 whatIsFit)
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
            ylabel="Projected X-ray Pressure",
            title="Pressure Fit",
            file="pressure.pdf",
            save=False
            )

    return pressure_coeffs, pressure_fit, pressure_fit_fine, ln_perr


def grav_accel(data):
    '''Analytic differentiation of the log pressure profile'''

    temp_coeffs, temp_fit, temp_fit_fine, ln_terr = logTemp_fit(data)
    pressure_coeffs, pressure_fit, pressure_fit_fine, ln_perr = logPressure_fit(
        data)

    r, ln_r, r_fine, log10_r_fine, ln_r_fine = extrapolate_radius(data)

    # Assign the dlnp_dlnr array with same length as radius array
    dlnp_dlnr = np.zeros(np.shape(ln_r))
    for i in np.arange(1, 4):
        dlnp_dlnr = dlnp_dlnr + \
            float(i) * pressure_coeffs[i] * ln_r**(float(i - 1))

    #logpressure_clip = -1.0e-10
    #dlnp_dlnr = np.clip(dlnp_dlnr, a_min=logpressure_clip, a_max=np.max(dlnp_dlnr))

    dlnp_dlnr_fine = np.zeros(np.shape(ln_r_fine))
    for i in np.arange(1, 4):
        dlnp_dlnr_fine = dlnp_dlnr_fine + \
            float(i) * pressure_coeffs[i] * ln_r_fine**(float(i - 1))

    #dlnp_dlnr_fine = np.clip(dlnp_dlnr_fine, a_min=logpressure_clip, a_max=np.max(dlnp_dlnr_fine))

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
            ylog=True,
            xlim=(1.0, 100.),
            ylim=(1.0e13, 1.2e16),
            xlabel="Cluster-centric radius",
            ylabel="rg in cgs",
            title="Gravitational acceleration",
            file="pressure.pdf",
            save=False)


# plotter(x, y, x_fine, fit, fit_fine, lowerbound, upperbound,
#            xlog=True, ylog=True, xlim=None, ylim=None,
#            xlabel="Set your X-label!", ylabel="Set your y label!",
#            title="Set your title!", file="temp.pdf", save=False)


#dlnp_dlnr =  0.0 * ln_rMpc
# for i = 1,degp do dlnp_dlnr = dlnp_dlnr $
#                           + float(i)*pcoeffs(i)*ln_rMpc^float(i-1)
# dlnp_dlnr = dlnp_dlnr < (-1.0E-10)
# print,dlnp_dlnr

# dlnp_dlnr_fine =  0.0 * ln_rMpc_fine
# for i = 1,degp do dlnp_dlnr_fine = dlnp_dlnr_fine $
#                           + float(i)*pcoeffs(i)*ln_rMpc_fine^float(i-1)
# dlnp_dlnr_fine = dlnp_dlnr_fine < (-1.0E-10)

# mu_mp = 0.6 * 1.67D-24
# rg = - kt_erg / mu_mp * dlnp_dlnr
# rg_fine = - kt_erg_fine / mu_mp * dlnp_dlnr_fine
# plot_oi,rMpc,rg,xtitle='r (Mpc)',ytitle = 'rg (cgs)'
# oplot,rMpc_fine,rg_fine,line=3

# relerr = sqrt(2.*exp(logperr)^2. + exp(logterr)^2.)
# rgerr = kt_erg / mu_mp * relerr
# oplot,rMpc,rg+rgerr,line=1
# oplot,rMpc,rg-rgerr,line=1


def plotter(x, y, x_fine, fit, fit_fine, lowerbound, upperbound,
            xlog=True, ylog=True, xlim=None, ylim=None,
            xlabel="Set your X-label!", ylabel="Set your y label!",
            title="Set your title!", file="temp.pdf", save=False):
    '''Plots should be pretty'''
    style.use('ggplot')

    plt.rcParams['font.size'] = 12
    plt.rcParams['axes.labelsize'] = 12
    plt.rcParams['xtick.labelsize'] = 12
    plt.rcParams['ytick.labelsize'] = 12

    plt.figure()

    # Plot data and fits

    # Only plot actual data points if I give you data points
    if y is not None:
        plt.plot(x, y, marker='o', markersize=10, linestyle='None')

    # Plot a nice error shadow
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


def coolingFunction(kT):
    '''
    Implement the Tozzi & Norman (2001) cooling function,
    which is an analytic fit to Sutherland & Dopita (1993).

    This is shown in Equation 16 of Parrish, Quataert,
    & Sharma (2009), as well as Guo & Oh (2014).

    See here: arXiv:0706.1274. The equation is:

    $\Lambda(T) = [C_1 \left( \frac{k_B T}{\mathrm{keV}} \right)^{-1.7}
                  + C_2\left( \frac{k_B T}{\mathrm{keV}} \right)^{0.5}
                  + C_3] \times 10^{-22}$
    '''

    keV = u.eV * 1000.0

    # For a metallicity of Z = 0.3 Z_solar,
    C1 = 8.6e-3 * u.erg / (u.cm**3 * u.s)
    C2 = 5.8e-3 * u.erg / (u.cm**3 * u.s)
    C3 = 6.3e-2 * u.erg / (u.cm**3 * u.s)

    alpha = -1.7
    beta = 0.5

    coolingFunction = (
        (C1 * (kT / keV)**alpha) +
        (C2 * (kT / keV)**beta) +
        (C3)
    ) * 1e-22

    return coolingFunction


def make_number_ordinal(number):
    '''Take number, turn into ordinal. E.g., "2" --> "2nd" '''

    suffixes = {1: 'st', 2: 'nd', 3: 'rd'}

    if 10 <= number % 100 <= 20:
        suffix = 'th'
    else:
        # the second parameter is a default.
        suffix = suffixes.get(number % 10, 'th')
    return str(number) + suffix


def rainmaker_notebook_init(filename, cluster_name):
    '''Run this in a Jupyter Notebook for exploration'''

    data = parse_data_table(filename, cluster_name.replace(" ", "_").upper())

    return data


def main():
    '''The main program runs the whole sequence.'''

    # Parse command line arguments. Iterate with user if cluster not found.
    filename, cluster_name, show_plots = parse_arguments()

    # DATA is an astropy TABLE object,
    # filtered to show all properties of a given cluster
    # Can be split by e.g. data['Rin'], data['Mgrav'], etc.
    data = parse_data_table(filename, cluster_name)

    grav_accel(data)


if __name__ == '__main__':
    start_time = time.time()
    main()
    runtime = round((time.time() - start_time), 3)
    print("Finished in    |  {} seconds".format(runtime))

    print("Showing plots  |")

    plt.show()
