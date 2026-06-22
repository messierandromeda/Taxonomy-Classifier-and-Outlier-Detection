import logging
import os

from dotenv import load_dotenv

load_dotenv()

_HERE = os.path.dirname(os.path.abspath(__file__))

GBIF_CONFIDENCE_RESOLVED = 80
BATCH_SIZE = 10

OPENAI_API_KEY  = os.getenv('OPENAI_API_KEY')
OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://ollama:11434/v1')
OPENAI_MODEL    = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
OLLAMA_MODEL    = os.getenv('OLLAMA_MODEL', 'llama3.2')
TAXONOMY_PATH   = os.getenv('TAXONOMY_PATH', os.path.join(_HERE, 'taxonomy.csv'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)
logging.getLogger('httpx').setLevel(logging.WARNING)

log = logging.getLogger(__name__)