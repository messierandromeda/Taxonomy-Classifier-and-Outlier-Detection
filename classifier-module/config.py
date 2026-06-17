import logging
import os

LAND_API_BASE = os.environ.get('LAND_TAXONOMY_API_URL', 'http://land-taxonomy-api:8000')
GBIF_CONFIDENCE_RESOLVED = 80
API_RETRIES = 10
REQUEST_DELAY = 0.3
BATCH_SIZE = 10
 
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)

logging.getLogger('httpx').setLevel(logging.WARNING)

log = logging.getLogger(__name__)