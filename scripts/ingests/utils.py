import sqlite3
import sys
import numpy as np
import re
import sqlalchemy.exc
import astrodbkit2
from astropy.coordinates import SkyCoord
import astropy.units as u
from astroquery.simbad import Simbad
from astropy.table import Table, vstack
import warnings
warnings.filterwarnings("ignore", module='astroquery.simbad')
from sqlalchemy import or_
import ads
import os
from contextlib import contextmanager


@contextmanager
def disable_exception_traceback():
    """
    All traceback information is suppressed and only the exception type and value are printed
    """
    default_value = getattr(sys, "tracebacklimit", 1000)  # `1000` is a Python's default value
    sys.tracebacklimit = 0
    yield
    sys.tracebacklimit = default_value  # revert changes


def sort_sources(db, ingest_names, ingest_ras, ingest_decs, verbose = False):

    verboseprint = print if verbose else lambda *a, **k: None

    existing_sources_index = []
    missing_sources_index = []
    db_names = []

    for i, name in enumerate(ingest_names):
        verboseprint("\n", i, ": searching:,", name)

        namematches = db.search_object(name)

        # if no matches, try resolving with Simbad
        if len(namematches) == 0:
            verboseprint(i,": no name matches, trying simbad search")
            try:
                namematches = db.search_object(name, resolve_simbad=True,verbose=verbose)
            except TypeError: #no Simbad match
                namematches = []

        # if still no matches, try spatial search using coordinates
        if len(namematches) == 0:
            location = SkyCoord(ingest_ras[i],ingest_decs[i],frame='icrs',unit='deg')
            radius = u.Quantity(60., unit='arcsec')
            verboseprint(i, ": no Simbad match, trying coord search around ",location.ra.hour,location.dec)
            nearby_matches = db.query_region(location, radius=radius)
            if len(nearby_matches) == 1:
                namematches = nearby_matches
            if len(nearby_matches) > 1:
                print(nearby_matches)
                raise Exception("too many nearby sources!")

        if len(namematches) == 1:
            existing_sources_index.append(i)
            source_match = namematches[0]['source']
            db_names.append(source_match)
            verboseprint(i, "match found: ",source_match)
        elif len(namematches) > 1:
            raise Exception(i,"More than one match for ", name,"/n,",namematches)
        elif len(namematches) == 0:
            verboseprint(i,": Not in database")
            missing_sources_index.append(i)
            db_names.append(ingest_names[i])
        else:
            raise Exception(i,"unexpected condition")

    verboseprint("\n ALL SOURCES SORTED")
    verboseprint("\n Existing Sources: ", ingest_names[existing_sources_index])
    verboseprint("\n Missing Sources: ", ingest_names[missing_sources_index])
    verboseprint("\n Db names: ", db_names,"\n")

    n_ingest = len(ingest_names)
    n_existing = len(existing_sources_index)
    n_missing = len(missing_sources_index)

    if n_ingest != n_existing + n_missing:
        raise Exception("Unexpected number of sources")

    print(n_existing, "sources already in database." )
    print(n_missing, "sources not found in the database")

    return(missing_sources_index, existing_sources_index, db_names)


def add_names(db,new_sources,verbose=True):

    verboseprint = print if verbose else lambda *a, **k: None
    names_data = []
    for source in new_sources:
        names_data.append({'source': source, 'other_name': source})

    db.Names.insert().execute(names_data)

    n_added = len(names_data)
    verboseprint(n_added, "names added to Names table")


def search_publication(db, name: str = None, doi: str = None, bibcode: str = None, verbose: bool = False):
    """
    Find publications in the database by matching on the publication name,  doi, or bibcode

    Parameters
    ----------
    db
        Variable referencing the database to search
    name: str
        Name of publication to search
    doi: str
        DOI of publication to search
    bibcode: str
        ADS Bibcode of publication to search

    Returns
    -------
    True, 1: if only one match
    False, 0: No matches
    False, N_matches: Mulptiple matches

    Examples
    -------
    >>> test = search_publication(db, name='Cruz')
    Found 8 matching publications for Cruz or None or None

    >>> test = search_publication(db, name='Kirk19',verbose=True)
    Found 1 matching publications for Kirk19 or None or None
     name        bibcode                 doi                                                                                description
    ------ ------------------- ------------------------ ----------------------------------------------------------------------------------------------------------------------------------------------------
    Kirk19 2019ApJS..240...19K 10.3847/1538-4365/aaf6af Preliminary Trigonometric Parallaxes of 184 Late-T and Y Dwarfs and an Analysis of the Field Substellar Mass Function into the Planetary Mass Regime

    >>> test = search_publication(db, name='Smith')
    No matching publications for Smith, Trying Smit
    No matching publications for Smit
    Use add_publication() to add it to the database.

    See Also
    --------
    add_publication: Function to add publications in the database

    """

    verboseprint = print if verbose else lambda *a, **k: None

    # Make sure a search term is provided
    if name == None and doi == None and bibcode == None:
        print("Name, Bibcode, or DOI must be provided")
        return False, 0

    not_null_pub_filters = []
    if name:
        #fuzzy_query_name = '%' + name + '%'
        not_null_pub_filters.append(db.Publications.c.name.ilike(name))
    if doi:
        not_null_pub_filters.append(db.Publications.c.doi.ilike(doi))
    if bibcode:
        not_null_pub_filters.append(db.Publications.c.bibcode.ilike(bibcode))

    if len(not_null_pub_filters) > 0:
        pub_search_table = db.query(db.Publications).filter(or_(*not_null_pub_filters)).table()

    n_pubs_found = len(pub_search_table)

    if n_pubs_found == 1:
        verboseprint(f'Found {n_pubs_found} matching publications for {name} or {doi} or {bibcode}')
        if verbose:
            pub_search_table.pprint_all()
        return True, 1

    if n_pubs_found > 1:
        verboseprint(f'Found {n_pubs_found} matching publications for {name} or {doi} or {bibcode}')
        if verbose:
            pub_search_table.pprint_all()
        return False, n_pubs_found

    # If no matches found, search using first four characters of input name
    if n_pubs_found == 0 and name:
        shorter_name = name[:4]
        verboseprint(f'No matching publications for {name}, Trying {shorter_name}')
        fuzzy_query_shorter_name = '%' + shorter_name + '%'
        pub_search_table = db.query(db.Publications).filter(db.Publications.c.name.ilike(fuzzy_query_shorter_name)).table()
        n_pubs_found_short = len(pub_search_table)
        if n_pubs_found_short == 0:
            verboseprint(f'No matching publications for {shorter_name}')
            verboseprint('Use add_publication() to add it to the database.')
            return False, 0

        if n_pubs_found_short > 0:
            print(f'Found {n_pubs_found_short} matching publications for {shorter_name}')
            if verbose:
                pub_search_table.pprint_all()
            return False, n_pubs_found_short
    else:
        return False, n_pubs_found

    return


def add_publication(db, doi: str = None, bibcode: str = None, name: str = None, description: str = None, ignore_ads: bool = False, save_db=False,
                    verbose: bool = True):
    """
    Adds publication to the database using DOI or ADS Bibcode, including metadata found with ADS.

    In order to auto-populate the fields, An $ADS_TOKEN environment variable must be set.
    See https://ui.adsabs.harvard.edu/user/settings/token

    Parameters
    ----------
    db
        Database object
    doi, bibcode: str
        The DOI or ADS Bibcode of the reference. One of these is required input.
    name: str, optional
        The publication shortname, otherwise it will be generated [optional]
        Convention is the first four letters of first authors last name and two digit year (e.g., Smit21)
        For last names which are less than four letters, use '_' or first name initial(s). (e.g, Xu__21 or LiYB21)
    description: str, optional
        Description of the paper, typically the title of the papre [optional]
    ignore_ads: bool
    save_db: bool
    verbose: bool

    See Also
    --------
    search_publication: Function to find publications in the database

    """

    verboseprint = print if verbose else lambda *a, **k: None

    if not(doi or bibcode):
       print('DOI or Bibcode is required input')
       return

    ads.config.token = os.getenv('ADS_TOKEN')

    if not ads.config.token and (not name and (not doi or not bibcode)):
        print("An ADS_TOKEN environment variable must be set in order to auto-populate the fields.\n"
              "Without an ADS_TOKEN, name and bibcode or DOI must be set explicity.")
        return
    
    if ads.config.token and not ignore_ads:
        use_ads = True 
    else:
        use_ads = False

    if 'arXiv' in bibcode:
        arxiv_id = bibcode
        bibcode = None
    else:
        arxiv_id = None

    # Search ADS uing a provided arxiv id
    if arxiv_id and use_ads:
        arxiv_matches = ads.SearchQuery(q=arxiv_id, fl=['id', 'bibcode', 'title', 'first_author', 'year', 'doi'])
        arxiv_matches_list = list(arxiv_matches)
        if len(arxiv_matches_list) != 1:
            print('should only be one matching arxiv id')
            return

        if len(arxiv_matches_list) == 1:
                verboseprint("Publication found in ADS using arxiv id: ", arxiv_id)
                article = arxiv_matches_list[0]
                verboseprint(article.first_author, article.year, article.bibcode, article.title)
                if not name:  # generate the name if it was not provided
                    name_stub = article.first_author.replace(',', '').replace(' ', '')
                    name_add = name_stub[0:4] + article.year[-2:]
                else:
                    name_add = name
                description = article.title[0]
                bibcode_add = article.bibcode
                doi_add = article.doi[0]

    elif arxiv_id:
        name_add = name
        bibcode_add = arxiv_id
        doi_add = doi

    # Search ADS using a provided DOI
    if doi and use_ads:
        doi_matches = ads.SearchQuery(doi=doi, fl=['id', 'bibcode', 'title', 'first_author','year','doi'])
        doi_matches_list = list(doi_matches)
        if len(doi_matches_list) != 1:
            print('should only be one matching DOI')
            return

        if len(doi_matches_list) == 1:
            verboseprint("Publication found in ADS using DOI: ",doi)
            article = doi_matches_list[0]
            verboseprint(article.first_author, article.year, article.bibcode, article.title)
            if not name: # generate the name if it was not provided
                name_stub = article.first_author.replace(',', '').replace(' ','')
                name_add = name_stub[0:4] + article.year[-2:]
            else:
                name_add = name
            description = article.title[0]
            bibcode_add = article.bibcode
            doi_add = article.doi[0]
    elif doi:
        name_add = name
        bibcode_add = bibcode
        doi_add = doi

    if bibcode and use_ads:
        bibcode_matches = ads.SearchQuery(bibcode=bibcode,fl=['id', 'bibcode', 'title', 'first_author','year','doi'])
        bibcode_matches_list = list(bibcode_matches)
        if len(bibcode_matches_list) == 0:
            print('not a valid bibcode:', bibcode)
            print('nothing added')
            raise

        elif len(bibcode_matches_list) > 1:
            print('should only be one matching bibcode for:', bibcode)
            print('nothing added')
            raise

        elif len(bibcode_matches_list) == 1:
            verboseprint("Publication found in ADS using bibcode: ", bibcode)
            article = bibcode_matches_list[0]
            verboseprint(article.first_author, article.year, article.bibcode, article.doi, article.title)
            if not name:  # generate the name if it was not provided
                name_stub = article.first_author.replace(',', '').replace(' ', '')
                name_add = name_stub[0:4] + article.year[-2:]
            else:
                name_add = name
            description = article.title[0]
            bibcode_add = article.bibcode
            if article.doi == None:
                doi_add = None
            else:
                doi_add = article.doi[0]
    elif bibcode:
        name_add = name
        bibcode_add = bibcode
        doi_add = doi

    new_ref = [{'name': name_add, 'bibcode': bibcode_add, 'doi': doi_add, 'description': description}]

    try:
        db.Publications.insert().execute(new_ref)
        verboseprint(f'Added {name_add} to Publications table')
    except sqlalchemy.exc.IntegrityError as err:
        print("\nSIMPLE ERROR: It's possible that a similar publication already exists in database\n"
              "SIMPLE ERROR: Use search_publication function before adding a new record\n")
        with disable_exception_traceback():
            raise

    if save_db:
        db.save_database(directory='data/')
        verboseprint("Publication added to database and saved: ", name_add)
    else:
        verboseprint("Publication added to database: ", name_add)

    return


def update_publication(db, doi: str = None, bibcode: str = None, name: str = None, description: str = None, save_db: bool = True):
    """
    Updates publications in the database, including metadata found with ADS.

    In order to auto-populate the fields, An $ADS_TOKEN environment variable must be set.
    See https://ui.adsabs.harvard.edu/user/settings/token

    Parameters
    ----------
    db
        Database object
    doi, bibcode: str
        The DOI or ADS Bibcode of the reference.
    name: str, optional
        The publication shortname, otherwise it will be generated [optional]
    description: str, optional
        Description of the paper, typically the title of the papre [optional]
    save_db: bool

    See Also
    --------
    search_publication: Function to find publications in the database
    add_publication: Function to add publications to the database

    """

    # TODO: provide an option to add missing information
    #     add_doi_bibcode = db.Publications.update().where(db.Publications.c.name == 'Manj19'). \
    #         values(bibcode='2019AJ....157..101M', doi='10.3847/1538-3881/aaf88f',
    #               description='Cloud Atlas: HST nir spectral library')
    #     db.engine.execute(add_doi_bibcode)
    return


# Make sure all source names are Simbad resolvable:
def check_names_simbad(ingest_names, ingest_ra, ingest_dec, radius='2s', verbose=False):
    verboseprint = print if verbose else lambda *a, **k: None

    resolved_names = []
    n_sources = len(ingest_names)
    n_name_matches = 0
    n_selections = 0
    n_nearby = 0
    n_notfound = 0

    for i, ingest_name in enumerate(ingest_names):
        # Query Simbad for identifiers matching the ingest source name
        identifer_result_table = Simbad.query_object(ingest_name, verbose=False)

        # Successfully resolved one matching identifier in Simbad
        if identifer_result_table is not None and len(identifer_result_table) == 1:
            # Add the Simbad resolved identifier ot the resolved_name list and deals with unicode
            if isinstance(identifer_result_table['MAIN_ID'][0], str):
                resolved_names.append(identifer_result_table['MAIN_ID'][0])
            else:
                resolved_names.append(identifer_result_table['MAIN_ID'][0].decode())
            verboseprint(resolved_names[i], "Found name match in Simbad")
            n_name_matches = n_name_matches + 1

        # If no identifier match found, search within "radius" of coords for a Simbad object
        else:
            verboseprint("searching around ", ingest_name)
            coord_result_table = Simbad.query_region(
                SkyCoord(ingest_ra[i], ingest_dec[i], unit=(u.deg, u.deg), frame='icrs'),
                radius=radius, verbose=verbose)

            # If no match is found in Simbad, use the name in the ingest table
            if coord_result_table is None:
                resolved_names.append(ingest_name)
                verboseprint("coord search failed")
                n_notfound = n_notfound + 1

            # If more than one match found within "radius", query user for selection and append to resolved_name
            elif len(coord_result_table) > 1:
                for j, name in enumerate(coord_result_table['MAIN_ID']):
                    print(f'{j}: {name}')
                selection = int(input('Choose \n'))
                if isinstance(coord_result_table['MAIN_ID'][selection], str):
                    resolved_names.append(coord_result_table['MAIN_ID'][selection])
                else:
                    resolved_names.append(coord_result_table['MAIN_ID'][selection].decode())
                verboseprint(resolved_names[i], "you selected")
                n_selections = n_selections + 1

            # If there is only one match found, accept it and append to the resolved_name list
            elif len(coord_result_table) == 1:
                if isinstance(coord_result_table['MAIN_ID'][0], str):
                    resolved_names.append(coord_result_table['MAIN_ID'][0])
                else:
                    resolved_names.append(coord_result_table['MAIN_ID'][0].decode())
                verboseprint(resolved_names[i], "only result nearby in Simbad")
                n_nearby = n_nearby + 1

    # Report how many find via which methods
    print("Names Found:", n_name_matches)
    print("Names Selected", n_selections)
    print("Names Found", n_nearby)
    print("Not found", n_notfound)

    n_found = n_notfound + n_name_matches + n_selections + n_nearby
    print('problem' if n_found != n_sources else (n_sources, 'names'))

    return resolved_names


def convert_spt_string_to_code(spectral_types, verbose=False):
    """
    normal tests: M0, M5.5, L0, L3.5, T0, T3, T4.5, Y0, Y5, Y9.
    weird TESTS: sdM4, ≥Y4, T5pec, L2:, L0blue, Lpec, >L9, >M10, >L, T, Y
    digits are needed in current implementation.
    :param spectral_types:
    :param verbose:
    :return:
    """

    verboseprint = print if verbose else lambda *a, **k: None

    spectral_type_codes = []
    for spt in spectral_types:
        verboseprint("Trying to convert:", spt)
        spt_code = np.nan

        if spt == "":
            spectral_type_codes.append(spt_code)
            verboseprint("Appended NAN")
            continue

        # identify main spectral class, loop over any prefix text to identify MLTY
        for i, item in enumerate(spt):
            if item == 'M':
                spt_code = 60
                break
            elif item == 'L':
                spt_code = 70
                break
            elif item == 'T':
                spt_code = 80
                break
            elif item == 'Y':
                spt_code = 90
                break
        # find integer or decimal subclass and add to spt_code

        spt_code += float(re.findall('\d*\.?\d+', spt[i + 1:])[0])
        spectral_type_codes.append(spt_code)
        verboseprint(spt, spt_code)
    return spectral_type_codes


def ingest_sources(db, sources, ras, decs, references, epochs = None, equinoxes = None, verbose = False, save_db = False):
    verboseprint = print if verbose else lambda *a, **k: None
    n_added = 0
    n_sources = len(sources)

    if epochs == None:
        epochs = [None] * n_sources
    if equinoxes == None:
        equinoxes = [None] * n_sources

    for i, source in enumerate(sources):

        # Construct data to be added
        source_data = [{'source': sources[i],
                        'ra': ras[i],
                        'dec':decs[i],
                        'reference':references[i],
                        'epoch':epochs[i],
                        'equinox':equinoxes[i]}]
        verboseprint(source_data)

        try:
            db.Sources.insert().execute(source_data)
            n_added += 1
        except sqlalchemy.exc.IntegrityError as err:
            print("SIMPLE ERROR: Discovery reference may not exist in the Publications table. Add it with add_publication function. ")
            with disable_exception_traceback():
                raise

    if save_db:
        db.save_database(directory='data/')
        print(n_added, "sources added to database and saved")
    else:
        print(n_added, "sources added to database")

    return


def ingest_parallaxes(db, sources, plxs, plx_errs, plx_refs, save_db=False, verbose=False):
    """

    Parameters
    ----------
    db
        Database object
    sources
        list of source names
    plx
        list of parallaxes corresponding to the sources
    plx_errs
        list of parallaxes uncertainties
    plx_ref
        list of references for the parallax data
    save_db: bool, optional
        If set to False (default), will modify the .db file, but not the JSON files
        If set to True, will save the JSON files
    verbose: bool, optional
        If true, outputs information to the screen

    Examples
    ----------
    > ingest_parallaxes(db, my_sources, my_plx, my_plx_unc, my_plx_refs, verbose = True)

    """

    verboseprint = print if verbose else lambda *a, **k: None

    n_added = 0

    for i, source in enumerate(sources):
        db_name = db.search_object(source, output_table='Sources')[0]['source']

        # Search for existing parallax data.
        # If no previous measurement exists, set the new one to the Adopted measurement
        # TODO: figure out adopted in cases of multiple measurements.
        adopted = None
        source_plx_data = db.query(db.Parallaxes).filter(db.Parallaxes.c.source == db_name).table()
        if source_plx_data is None or len(source_plx_data) == 0:
            adopted = True
        else:
            print("\nOTHER PARALLAX EXISTS, adopted = None")
            print(source_plx_data)

        # Construct data to be added
        parallax_data = [{'source': db_name,
                          'parallax': str(plxs[i]),
                          'parallax_error': str(plx_errs[i]),
                          'reference': plx_refs[i],
                          'adopted': adopted}]
        verboseprint(parallax_data)

        try:
            db.Parallaxes.insert().execute(parallax_data)
            n_added += 1
        except sqlalchemy.exc.IntegrityError as err:
            print("SIMPLE ERROR: The source may not exist in Sources table.")
            print("SIMPLE ERROR: The parallax reference may not exist in Publications table. Add it with add_publication function. ")
            print("SIMPLE ERROR: The parallax measurement may be a duplicate.")
            with disable_exception_traceback():
                raise

    if save_db:
        db.save_database(directory='data/')
        print("Parallaxes added to database and saved: ", n_added)
    else:
        print("Parallaxes added to database: ", n_added)

    return


def ingest_proper_motions(db, sources, pm_ras, pm_ra_errs, pm_decs, pm_dec_errs, pm_references, save_db=False,verbose=False):
    """

    Parameters
    ----------
    db
        Database object
    sources
        list of source names
    pm_ras
        list of proper motions in right ascension (RA)
    pm_ra_errs
        list of uncertanties in proper motion RA
    pm_decs
        list of proper motions in declination (dec)
    pm_dec_errs
        list of uncertanties in proper motion dec
    pm_reference
        list of references for the proper motion measurements
    save_db: bool, optional
        If set to False (default), will modify the .db file, but not the JSON files
        If set to True, will save the JSON files
    verbose: bool, optional
        If true, outputs information to the screen

    Examples
    ----------
    > ingest_proper_motions(db, my_sources, my_pm_ra, my_pm_ra_unc, my_pm_dec, my_pm_dec_unc, my_pm_refs, verbose = True)

    """

    verboseprint = print if verbose else lambda *a, **k: None

    n_added = 0

    for i, source in enumerate(sources):
        db_name = db.search_object(source, output_table='Sources')[0]['source']

        # Search for existing proper motion data and determine if this is the best
        # If no previous measurement exists, set the new one to the Adopted measurement
        # TODO: figure out adopted in cases of multiple measurements.
        adopted = None
        source_pm_data = db.query(db.ProperMotions).filter(db.ProperMotions.c.source == db_name).table()
        if source_pm_data is None or len(source_pm_data) == 0:
            adopted = True
        else:
            print("\nOTHER PROPER MOTION EXISTS, adopted = None")
            print(source_pm_data)

        # Construct data to be added
        pm_data = [{'source': db_name,
                          'mu_ra': pm_ras[i],
                          'mu_ra_error' : pm_ra_errs[i],
                          'mu_dec': pm_decs[i],
                          'mu_dec_error': pm_dec_errs[i],
                          'adopted': adopted,
                          'reference': pm_references[i]}]
        verboseprint('Proper motion data: ',pm_data)

        try:
            db.ProperMotions.insert().execute(pm_data)
            n_added += 1
        except sqlalchemy.exc.IntegrityError as err:
            print("SIMPLE ERROR: The source may not exist in Sources table.")
            print("SIMPLE ERROR: The proper motion reference may not exist in Publications table. Add it with add_publication function. ")
            print("SIMPLE ERROR: The proper motion measurement may be a duplicate.")
            with disable_exception_traceback():
                raise

    if save_db:
        db.save_database(directory='data/')
        print("Proper motions added to database and saved: ", n_added)
    else:
        print("Proper motions added to database: ", n_added)

    return


def ingest_photometry(db, sources, bands, magnitudes, magnitude_errors, reference, ucds = None,
                      telescope = None, instrument = None, epoch = None, comments = None, save_db=False, verbose=False):

    verboseprint = print if verbose else lambda *a, **k: None
    n_added = 0

    for i, source in enumerate(sources):
        db_name = db.search_object(source, output_table='Sources')[0]['source']

        # Construct data to be added
        photometry_data = [{'source': db_name,
                          'band': bands[i],
                          'ucd' : ucds[i],
                          'magnitude' : magnitudes[i],
                          'magnitude_error' : magnitude_errors[i],
                          'telescope': telescope[i],
                          'instrument': instrument[i],
                          'epoch': epoch,
                          'comments': comments,
                          'reference': reference[i]}]
        verboseprint('Photometry data: ',photometry_data)

        try:
            db.Photometry.insert().execute(photometry_data)
            n_added += 1
        except sqlalchemy.exc.IntegrityError as err:
            print("SIMPLE ERROR: The source may not exist in Sources table.")
            print("SIMPLE ERROR: The reference may not exist in the Publications table. Add it with add_publication function. ")
            print("SIMPLE ERROR: The measurement may be a duplicate.")
            with disable_exception_traceback():
                raise

        if save_db:
            db.save_database(directory='data/')
            print("Photometry measurements added to database and saved: ", n_added)
        else:
            print("Photometry measurements added to database: ", n_added)

    return
