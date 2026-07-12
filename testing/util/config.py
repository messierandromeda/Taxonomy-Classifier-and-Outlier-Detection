import os
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))

WORKING_DATA = Path(__file__).resolve().parent.parent / 'data' / 'working20.csv'
WORKING_DATA2 = Path(__file__).resolve().parent.parent / 'data' / 'working5.csv'
WORKING_DATA3 = Path(__file__).resolve().parent.parent / 'data' / 'working1.csv'
WORKING_DATA100 = Path(__file__).resolve().parent.parent / 'data' / 'working100.csv'
HELDOUT_DATA100 = Path(__file__).resolve().parent.parent / 'data' / 'heldout100.csv'
RESULT_PATH = Path(__file__).resolve().parent.parent / 'results'
DATA_PATH = Path(__file__).resolve().parent.parent / 'data'

# Columns
ID_TEST = 'row_id'
ID = 'HerbariumID'
NAME = 'FullNameCache'
NAME_S = 'NameCache'
GENUS = 'Genus'
FAMILY = 'Family'
LAT = 'Latitude'
LON = 'Longitude'
CULTIVATED_FIELD = 'Anmerkungen'

LOCALITY_LABELS = {
    'FundortUNdOeko': 'Habitat and ecology',   # primary
    'Locality':       'Locality',              # secondary
}

FIELD_LABELS = {
    'FundortUNdOeko':  'Habitat and ecology',
    'Locality':        'Locality',
    'NameCache':       'Collected species',
    'Genus':           'Genus',
    'Family':          'Family',
}