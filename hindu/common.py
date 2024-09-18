import pytz
import logging as Logger

from datetime import datetime, timedelta
from histral_core.types import NewsArticle
from histral_core.scraper import fetch_soup
from histral_core.encode import encode_text
from histral_core.summery import extractive_summary


# --------------------- Logging Setup ---------------------


Logger.basicConfig(
    level=Logger.INFO,
    format="[%(levelname)s] (%(asctime)s) -> %(message)s",
    handlers=[
        Logger.StreamHandler(),
    ],
)


# --------------------- Constants ---------------------


IST = pytz.timezone("Asia/Kolkata")

CURRENT_TIME_IST = datetime.now(IST)
TODAY_8PM = CURRENT_TIME_IST.replace(
    hour=20,
    minute=0,
    second=0,
    microsecond=0,
)
YESTERDAY_8PM = CURRENT_TIME_IST.replace(
    hour=20,
    minute=0,
    second=0,
    microsecond=0,
) - timedelta(days=1)


# --------------------- Common Functions ---------------------


def parse_date_to_iso(date_str: str) -> str:
    """
    Adjust the format string and parse in ISO format
    """
    try:
        date_str = date_str.replace("IST", "").strip()
        date_object = datetime.strptime(date_str, "%B %d, %Y %I:%M %p")
        date_with_timezone = IST.localize(date_object)
        return date_with_timezone.isoformat()
    except ValueError as e:
        Logger.error(f"ERROR: Failed to parse time '{date_str}' to ISO: {e}")
        return None


def fetch_all_links(BASE_URL: str) -> list:
    try:
        base_soup = fetch_soup(BASE_URL)
        if base_soup is None:
            Logger.error(f"ERROR: No date found in {BASE_URL}")
            raise

        links = []

        divs = base_soup.find_all(
            "div",
            class_=lambda c: c
            in ["element row-element", "element row-element no-border"],
        )

        if len(divs) == 0:
            Logger.error(f"ERROR: No links found in {BASE_URL}")
            raise

        for div in divs:
            a_tag = div.find("a", href=True)

            if a_tag:
                links.append(a_tag["href"])

        Logger.info(f"TRACE: Found total {len(links)} news links.")

        return links
    except Exception as e:
        Logger.error(f"ERROR: Unable to fetch news links: {e}")
        raise


def fetch_news_from_link(NEWS_URL) -> NewsArticle:
    """
    Fetch [NewsArticle] from the news link, return **None** if
    no data found or if any error occurred
    """

    try:
        news_soup = fetch_soup(NEWS_URL)
        if news_soup is None:
            Logger.warning(f"WARN: Skipping link due to fetch failure: {NEWS_URL}")
            return None

        p_time = news_soup.find("p", class_="publish-time-new")

        if not p_time or "-" not in p_time.text:
            Logger.warning(
                f"WARN: Publish time not found or invalid format for link: {NEWS_URL}"
            )
            return None

        time_published = p_time.text.split("-")[
            -2 if len(p_time.text.split("-")) >= 3 else -1
        ]

        news_time_iso = parse_date_to_iso(time_published)

        if not news_time_iso:
            Logger.warning(f"WARN: No News time found in: {NEWS_URL}")
            return None

        news_time = datetime.fromisoformat(news_time_iso)

        date_timezone = news_time.astimezone(IST)

        if (date_timezone < YESTERDAY_8PM) or (date_timezone > TODAY_8PM):
            Logger.warning(f"WARN: Skipping invalid date format: {news_time}")
            return None

        heading = (
            news_soup.find("h1", class_="title").text
            if news_soup.find("h1", class_="title")
            else "Title Not Found"
        )
        subHeading = (
            news_soup.find("h2", class_="sub-title").text
            if news_soup.find("h2", class_="sub-title")
            else ""
        )

        author = news_soup.find("div", class_="author").text.strip()
        content_div = news_soup.find("div", class_="articlebodycontent")
        content = [
            p_tag.text for p_tag in content_div.find_all("p") if not p_tag.get("class")
        ]

        body = " ".join(content)
        summarized_body = extractive_summary(body, percentage=0.34)
        summarized_body = encode_text(summarized_body)
        summarized_subHeading = (
            extractive_summary(subHeading, percentage=0.8) if subHeading else ""
        )

        news = NewsArticle(
            title=heading,
            sub_heading=summarized_subHeading,
            body=summarized_body,
            tags=[],
            src=NEWS_URL,
            author=[author],
            timestamp=news_time,
        )

        return news
    except Exception as e:
        Logger.error(
            f"Error: Unable to process link {NEWS_URL}: {e}",
        )
