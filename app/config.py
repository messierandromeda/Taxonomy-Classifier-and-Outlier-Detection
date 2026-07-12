import logging
import os

from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

_HERE = os.path.dirname(os.path.abspath(__file__))

GBIF_CONFIDENCE_RESOLVED = 80
BATCH_SIZE = 10

OPENAI_API_KEY  = os.getenv('OPENAI_API_KEY')
OLLAMA_BASE_URL = 'http://ollama:11434/v1'
OPENAI_MODEL    = 'gpt-5.4-nano'
OLLAMA_MODEL    = 'llama3.2'
TAXONOMY_PATH = os.path.join(_HERE, 'taxonomy.csv')

DEFAULT_MODEL = OPENAI_MODEL
GEE_PROJECT = 'clc-code'
WORKING_DATA = Path(__file__).resolve().parent.parent / 'testing' / 'data' / 'working20.csv'
RESULT_PATH = Path(__file__).resolve().parent.parent / 'testing' / 'results'

PRICES = {
    'gpt-5.4-mini': {'input': 0.75, 'output': 4.5},
    'gpt-5.4-nano': {'input': 0.20, 'output': 1.25},
    'gpt-5-nano': {'input': 0.05, 'output': 0.4},
    'gpt-4.1-nano': {'input': 0.1, 'output': 0.4},
    'gpt-5.6-terra': {'input': 2.5, 'output': 15},
}


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)
logging.getLogger('httpx').setLevel(logging.WARNING)

log = logging.getLogger(__name__)

# Columns
ID = 'HerbariumID'
LOCALITY_FIELDS = ['FundortUNdOeko', 'Locality'] # sorted from most to least important
NAME = 'FullNameCache'
GENUS = 'Genus'
FAMILY = 'Family'
LAT = 'Latitude'
LON = 'Longitude'