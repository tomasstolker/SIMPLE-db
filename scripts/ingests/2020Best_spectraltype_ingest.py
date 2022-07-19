import logging
# from astroquery.simbad import conf
from scripts.ingests.ingest_utils import *
from scripts.ingests.utils import *

SAVE_DB = False  # save the data files in addition to modifying the .db file
RECREATE_DB = True  # recreates the .db file from the data files

logger.setLevel(logging.DEBUG)

db = load_simpledb('SIMPLE.db', recreatedb=RECREATE_DB)

# Read in CSV file as Astropy table
# file = 'Manja19_spectra9.csv'
file = 'UltracoolSheet-Main.csv'
data = Table.read('scripts/ingests/' + file)
# Ingest Optical Spectral Types First
# use the hashtag to comment it out

# Optical Spectral Types
filter_opt_data = data[data['spt_opt'] != 'null']
opt_names = filter_opt_data['name']
n_sources_opt = len(opt_names)
opt_regime = ['optical'] * n_sources_opt
spt_refs_opt = filter_opt_data['ref_spt_opt']
spectral_types_opt = filter_opt_data['spt_opt']
# IR Spectral Types
filter_ir_data = data[data['spt_ir'] != 'null']
ir_names = filter_ir_data['name']
n_sources_ir = len(ir_names)
ir_regime = ['nir_UCD'] * n_sources_ir
spt_refs_ir = filter_ir_data['ref_spt_ir']
spectral_types_ir = filter_ir_data['spt_ir']


def ingest_source_pub():
    ingest_sources(db, 'BRI 0021-0214', 'Irwi91')
    ingest_sources(db, 'LHS 1070', 'McCa64c')
    ingest_sources(db, 'WISE J003110.04+574936.3', 'Thom13')
    ingest_sources(db, 'DENIS-P J0041353-562112', 'Phan01')
    ingest_sources(db, 'DENIS J020529.0-115925', 'Delf97')
    ingest_sources(db, 'LP 261-75B', 'Kirk00')
    ingest_sources(db, 'LHS 292', 'Dahn86')


ingest_source_pub()

# Source names in database Names table
db_opt_names = []
db_ir_names = []
for name in opt_names:
    db_opt_name = db.search_object(name, output_table='Sources', table_names={'Names': ['other_name']})[0]
    db_opt_names.append(db_opt_name['source'])

for name in ir_names:
    db_ir_name = db.search_object(name, output_table='Sources', table_names={'Names': ['other_name']})[0]
    db_ir_names.append(db_ir_name['source'])

# # Convert SpT string to code
spectral_type_codes_opt = convert_spt_string_to_code(spectral_types_opt)
spectral_type_codes_ir = convert_spt_string_to_code(spectral_types_ir)

# Adding References for Optical
ref_list_opt = spt_refs_opt.tolist()
included_ref_opt = db.query(db.Publications.c.publication).filter(db.Publications.c.publication.in_(ref_list_opt)).all()
included_ref_opt = [s[0] for s in included_ref_opt]
new_ref_opt = list(set(ref_list_opt) - set(included_ref_opt))
new_ref_opt = [{'publication': s} for s in new_ref_opt]
if len(new_ref_opt) > 0:
    db.Publications.insert().execute(new_ref_opt)

# Adding References for Infrared
ref_list_ir = spt_refs_ir.tolist()
included_ref_ir = db.query(db.Publications.c.publication).filter(db.Publications.c.publication.in_(ref_list_ir)).all()
included_ref_ir = [s[0] for s in included_ref_ir]
new_ref_ir = list(set(ref_list_ir) - set(included_ref_ir))
new_ref_ir = [{'publication': s} for s in new_ref_ir]
if len(new_ref_ir) > 0:
    db.Publications.insert().execute(new_ref_ir)

# # Make astropy table with all relevant columns and add to SpectralTypes Table
SpT_Opt_table = Table([db_opt_names, spectral_types_opt, spectral_type_codes_opt, opt_regime, spt_refs_opt],
                      names=('source', 'spectral_type_string', 'spectral_type_code', 'regime', 'reference'))

input_values = [ir_names, ir_regime, spt_refs_ir, spectral_types_ir]
for i, input_value in enumerate(input_values):
    if isinstance(input_value, str):
        print, input_value
        input_values[i] = [input_value] * n_sources_ir
    elif isinstance(input_value, type(None)):
        print, input_value
        input_values[i] = [None] * n_sources_ir
ir_names, ir_regime, spt_refs_ir, spectral_types_ir = input_values

for i, source in enumerate(db_ir_names):
    SptT_Ir_data = [{'source': db_ir_names[i],
                     'spectral_type_string': spectral_types_ir[i],
                     'spectral_type_code': spectral_type_codes_ir[i],
                     'regime': ir_regime[i],
                     'reference': spt_refs_ir[i]}]
    try:
        db.SpectralTypes.insert().execute(SptT_Ir_data)
    except sqlalchemy.exc.IntegrityError as e:
        continue

db.add_table_data(SpT_Opt_table, table='SpectralTypes', fmt='astropy')

# # WRITE THE JSON FILES
# if SAVE_DB:
#     db.save_database(directory='data/')
