import requests
import logging as Logger

from bs4 import BeautifulSoup


Logger.basicConfig(
    level=Logger.INFO,
    format="[%(levelname)s] (%(asctime)s) -> %(message)s",
    handlers=[
        Logger.StreamHandler(),
    ],
)


def fetch_soup(URL: str):
    """
    Fetch HTML data for given [URL]
    """
    try:
        base_page_data = requests.get(URL, timeout=30)

        # raises HTTPError for bad responses
        base_page_data.raise_for_status()

        base_soup = BeautifulSoup(base_page_data.content, "html.parser")

        return base_soup
    except requests.exceptions.RequestException as e:
        Logger.error(f"ERROR: Failed to fetch URL {URL}: {e}")
        return None
