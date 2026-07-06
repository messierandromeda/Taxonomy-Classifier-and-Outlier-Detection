import os
from dotenv import load_dotenv
import requests
import subprocess
import time

load_dotenv()

# Columns (explicit constants for every expected column)
# Primary fields
HERBARIUM_ID = "HerbariumID"
BILD = "Bild"
DB = "DB"
FAMILY = "Family"
FULL_NAME_CACHE = "FullNameCache"
ANMERKUNGEN = "Anmerkungen"
SAMMLERTEAM = "Sammlerteam"
SAMMELNUMMER = "Sammelnummer"
COLLECTION_DATE_BEGIN = "CollectionDateBegin"
COLLECTION_DATE_END = "CollectionDateEnd"
COUNTRY = "Country"
LOCALITY = "Locality"
TITEL_ETIKETT = "TitelEtikett"
EXPEDITIONSANGABE = "Expeditionsangabe"
SHOW_ON_MAP = "ShowOnMap"
LATITUDE = "Latitude"
LONGITUDE = "Longitude"
FUNDORT_UND_OEKO = "FundortUNdOeko"
NAME_CACHE = "NameCache"
GENUS = "Genus"
IDENTIFIER = "Identifier"
BARCODE = "Barcode"
STABLE_URI = "StableURI"

# Backwards-compatible aliases used elsewhere in the codebase
ID = HERBARIUM_ID
NAME = FULL_NAME_CACHE
DATE = COLLECTION_DATE_BEGIN

# Messages
RULE_BASED_MSG = "Check for missing columns. If set to True, many entries will be incorrectly marked as outliers due to missing columns."
UNINITIALIZED_MSG = 'Outlier detection engine is uninitialized. Please run "python -m app.train" while the Docker container is started from the project\'s root directory first.'

# LLMs
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama-service:11434/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")


# Ollama Configurations
def is_ollama_running() -> bool:
    """Return True when the configured Ollama server responds successfully."""
    try:
        response = requests.get(
            OLLAMA_URL,
            timeout=2,
        )

        return response.status_code == 200

    except requests.RequestException:
        return False


def start_ollama_if_needed() -> None:
    """Attempt to start the Ollama service if it is not already running."""
    if is_ollama_running():
        print("Ollama is already running.")
        return

    print("Starting Ollama server...")

    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )

    except FileNotFoundError:
        print("Warning: Ollama command was not found.")
        return

    for _ in range(10):
        time.sleep(1)

        if is_ollama_running():
            print("Ollama started successfully.")
            return

    print("Warning: Ollama could not be started automatically.")
