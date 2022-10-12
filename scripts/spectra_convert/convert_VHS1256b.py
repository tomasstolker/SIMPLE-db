from convert_spectra_to_spec1dfits import *
from astropy.table import Table
import astropy.units as u

logger = logging.getLogger('SIMPLE')
logger.setLevel(logging.INFO)


# Function for reading in the VHS 1256b files from Miles 2018
def nirspec_spectrum_loader(spectrum_path):
    spectrum_table = Table.read(spectrum_path, format='ascii',
                                names=['wavelength', 'flux', 'flux_uncertainty'],
                                units=[u.micron, u.watt/u.cm/u.cm/u.micron, u.watt/u.cm/u.cm/u.micron ])
    good_data = spectrum_table['wavelength'] < 4.0

    return spectrum_table[good_data]


def osiris_spectrum_loader(spectrum_path):
    spectrum_table = Table.read(spectrum_path, format='ascii',
                                names=['wavelength', 'flux', 'flux_uncertainty'],
                                units=[u.angstrom, u.watt/u.cm/u.cm/u.angstrom, u.watt/u.cm/u.cm/u.angstrom ])
    return spectrum_table


# Same for every spectrum.
dataset_info = {
    'fits_data_dir': '/Users/kelle/Dropbox (Personal)/Mac (3)/Downloads/VHS1256b/',  # Path of FITS output

    # Information about new spectra
    'vopub': 'SIMPLE Archive',  # SIMPLE Archive, if going to be served via SIMPLE
    'generated_history': 'This file generated by convert_VHS1256b.py',
    'voclass': 'Spectrum 1.0',  # corresponds to IVOA data model

    # Information that is true for all data
    'object_name': "VHS 1256-1257b",
    'RA': 194.007636,  # float, decimal degrees
    'dec': -12.957692,  # float, decimal degrees
}

# NIRSPEC spectrum
NIRSPEC_spectrum_info = {
    'loader_function': nirspec_spectrum_loader,  # Function which loads the spectrum into an Astropy Table
    'bandpass': 'nir',
    'aperture': '0.570',  # [arcseconds]
    "observatory": 'Keck',  # From https://github.com/astropy/astropy-data/blob/gh-pages/coordinates/sites.json
    'telescope': 'Keck II',
    'instrument': 'NIRSPEC',
    'file_path': "/Users/kelle/Dropbox (Personal)/Mac (3)/Downloads/vhs1256b_spectra_Figure8_Miles2018.txt",
    # "start_time":  , # MJD
    # "stop_time":
    # "exposure_time": , # in seconds
    'observation_date': '2016-06-19' ,  # YYYY-MM-DD
    'spectrum_comments': 'KL filter, 2.9-4.4 microns with R of 1300',
    # Information about the publications the data come from
    'title': 'Methane in Analogs of Young Directly Imaged Exoplanets',  # Title of Paper
    'author': 'Miles et al.',  # Authors of paper
    'bibcode': '2018ApJ...869...18M',  # Bibcode of paper
    'doi': '10.3847/1538-4357/aae6cd',  # DOI of paper
    # 'dataset_comments': None,  # Any comments about the data provenance
}

nirspec_spectrum_info_all = {**dataset_info, **NIRSPEC_spectrum_info}
convert_to_fits(nirspec_spectrum_info_all)

# Optical OSIRIS spectrum
osiris_spectrum_info = {
    'loader_function': osiris_spectrum_loader,  # Function which loads the spectrum into an Astropy Table
    'bandpass': 'opt',
    'aperture': '1.5',  # [arcseconds]
    'observatory': 'lapalma',  # From https://github.com/astropy/astropy-data/blob/gh-pages/coordinates/sites.json
    'telescope': 'GTC',
    'instrument': 'OSIRIS',
    'file_path': "/Users/kelle/Dropbox (Personal)/Mac (3)/Downloads/vhs1256b/vhs1256b_opt_Osiris.dat",
    # "start_time":  , # [MJD]
    # "stop_time": # [MJD]
    # "exposure_time": , # [seconds]
    'observation_date': '2014-06-03' ,  # YYYY-MM-DD
    'spectrum_comments': 'R300 grating, R~130'
}
osiris_spectrum_info_all = {**dataset_info, **osiris_spectrum_info}
convert_to_fits(osiris_spectrum_info_all)

# Optical OSIRIS spectrum
sofi_spectrum_info = {
    'loader_function': osiris_spectrum_loader,  # Function which loads the spectrum into an Astropy Table
    'bandpass': 'nir',
    'aperture': '1.0',  # [arcseconds]
    'observatory': 'lasilla',  # From https://github.com/astropy/astropy-data/blob/gh-pages/coordinates/sites.json
    'telescope': 'NTT',
    'instrument': 'SofI',
    'file_path': "/Users/kelle/Dropbox (Personal)/Mac (3)/Downloads/vhs1256b/vhs1256b_nir_SOFI.dat",
    # "start_time":  , # [MJD]
    # "stop_time": # [MJD]
    # "exposure_time": , # [seconds]
    'observation_date': '2014-03-12' ,  # YYYY-MM-DD
    'spectrum_comments': 'blue and red grisms, covering 950-2520 nm'
}
sofi_spectrum_info_all = {**dataset_info, **sofi_spectrum_info}
convert_to_fits(sofi_spectrum_info_all)


# Plot the newly converted files using specutils
from astropy.io import fits
from matplotlib import pyplot as plt
from specutils import Spectrum1D

files = [
    f"{osiris_spectrum_info_all['fits_data_dir']}vhs1256b_spectra_Figure8_Miles2018.fits",
    f"{osiris_spectrum_info_all['fits_data_dir']}vhs1256b_opt_Osiris.fits",
    f"{sofi_spectrum_info_all['fits_data_dir']}vhs1256b_nir_SOFI.fits",
    ]

for fits_file in files:
    spec1d = Spectrum1D.read(fits_file, format='tabular-fits')
    name = spec1d.meta['SPECTRUM']
    header = fits.getheader(fits_file)
    logger.info(f'Plotting spectrum of {name} stored in {fits_file}')

    ax = plt.subplots()[1]
    # ax.plot(spec1d.spectral_axis, spec1d.flux)
    ax.errorbar(spec1d.spectral_axis.value, spec1d.flux.value, yerr=spec1d.uncertainty.array, fmt='-')
    ax.set_xlabel(f"Dispersion ({spec1d.spectral_axis.unit})")
    ax.set_ylabel(f"Flux ({spec1d.flux.unit})")
    plt.title(name)
    plt.show()