import requests
from core.logging.config import logger

SHORTENER_SERVICE_URL = "https://tinyurl.com/api-create.php"

def shorten_url(long_url):
    """Shortens a given URL using the TinyURL API service."""
    try:
        response = requests.get(f"{SHORTENER_SERVICE_URL}?url={long_url}", timeout=10)
        response.raise_for_status()
        
        shortened = response.text.strip()

        if shortened.startswith("Error") or shortened == long_url:
            logger.warning(f"TinyURL API returned an error or original URL for '{long_url}': {shortened}")
            return None
        return shortened

    except requests.exceptions.RequestException as e:
        logger.error(f"Error shortening URL '{long_url}' with TinyURL: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred while shortening URL '{long_url}': {e}")
        return None
