import os
from dotenv import load_dotenv

load_dotenv()

UNINITIALIZED_MSG = "Outlier detection engine is uninitialized. Please run \"python -m app.train\" while the Docker container is started from the project's root directory first."

OPENAI_API_KEY  = os.getenv('OPENAI_API_KEY')
OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://ollama-service:11434/v1')
OPENAI_MODEL    = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
OLLAMA_MODEL    = os.getenv('OLLAMA_MODEL', 'llama3.2:3b')