import os
import requests
import subprocess
import time

# --------------------------------------------------
# Ollama configuration
# --------------------------------------------------


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

# --------------------------------------------------
# Ollama health check
# --------------------------------------------------


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


# --------------------------------------------------
# Start Ollama automatically if needed
# --------------------------------------------------


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
