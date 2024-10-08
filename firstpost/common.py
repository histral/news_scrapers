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

BASE_URL = "https://www.firstpost.com"

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
    Adjust the format string to match 'September 13, 2024,12:52:19'
    and parse in ISO format
    """
    try:
        # Check if [date_str] contains "IST" and remove it
        date_str = date_str.replace("IST", "").strip()

        date_object = datetime.strptime(date_str.strip(), "%B %d, %Y, %H:%M:%S")
        return date_object.isoformat()
    except ValueError as e:
        Logger.error(f"FATAL: Failed to parse time '{date_str}' to ISO: {e}")
        return None


def fetch_all_news_links(URL):
    """
    Fetch all news posts links from the given URL
    """
    try:
        news_links = []
        base_soup = fetch_soup(URL)

        if not base_soup:
            Logger.error(f"ERROR: Unable to find any links from - {URL}")
            return news_links

        news_anchors = base_soup.find_all("a", class_=["en-nw-list", "en-nw"])

        if (news_anchors == None) or (len(news_anchors) == 0):
            Logger.error(f"ERROR: No news links found in - {URL}")
            return news_links

        for a_tag in news_anchors:
            if a_tag and a_tag["href"]:
                news_links.append(a_tag["href"])

        Logger.info(f"TRACE: Found {len(news_links)} news links in {URL}")
        return news_links
    except Exception as e:
        Logger.error(f"ERROR: Unable to fetch news links: {e}")
        return []


def fetch_news(URL) -> NewsArticle | None:
    """
    Fetch [NewsArticle] from news link
    """
    try:
        news_soup = fetch_soup(URL)

        if not news_soup:
            return None

        # News Title
        news_title = (
            news_soup.find("h1").text if news_soup.find("h1") else "Title not found"
        )

        sub_heading_element = news_soup.find("div", class_="art-desc")
        sub_heading_p = sub_heading_element.find("p") if sub_heading_element else None

        # News SubHeading
        news_sub_heading = sub_heading_p.find("span").text if sub_heading_p else ""

        art_details_info = news_soup.find("div", class_="art-dtls-info")

        # News Date & Author
        if art_details_info:
            details_text = art_details_info.text.split("•")
            news_date = details_text[-1].strip() if len(details_text) > 1 else ""
            news_author = details_text[0].strip() if details_text[0].strip() else ""
        else:
            news_date, news_author = "", ""

        if len(news_date) == 0:
            Logger.warning(f"WARN: News Date not found for {URL}")
            return None

        # Format news date in ISO format
        news_date = parse_date_to_iso(news_date)

        if news_date == None:
            Logger.warning(f"WARN: Unable to parse News Date for {URL}")
            return None

        news_body_p_list = (
            news_soup.find("div", class_="art-content").find_all("p")
            if news_soup.find("div", class_="art-content")
            else []
        )

        # News Body
        news_body = "".join([p.text for p in news_body_p_list])

        tags_data = news_soup.find("div", class_="tag-cont-wp")

        # News Tags
        if tags_data:
            news_tags = [
                tag.strip() for tag in tags_data.text.split("\n") if tag.strip()
            ]
        else:
            news_tags = None

        # Summarize and compress news body
        body_summary = extractive_summary(news_body, percentage=0.34)
        body_summary = encode_text(body_summary)

        if news_sub_heading:
            sub_heading_summary = extractive_summary(
                news_sub_heading,
                percentage=0.8,
            )
        else:
            sub_heading_summary = ""

        news = NewsArticle(
            tags=news_tags,
            author=[news_author],
            title=news_title,
            sub_heading=sub_heading_summary,
            body=body_summary,
            timestamp=news_date,
            src=URL,
        )

        Logger.info(f"TRACE: Fetched news from {URL}")
        return news
    except Exception as e:
        Logger.error(f"ERROR: Unable to fetch news from {URL}: {e}")
        return None


def filter_news_data(DATA: list) -> list:
    filtered_list = []

    for item in DATA:
        if item is None:
            continue

        iso_time = item["timestamp"]

        try:
            date_obj = datetime.fromisoformat(iso_time)
            date_timezone = date_obj.astimezone(IST)

            if YESTERDAY_8PM <= date_timezone <= TODAY_8PM:
                filtered_list.append(item)
        except ValueError:
            Logger.warning(f"WARN: Skipping invalid date format: {iso_time}")

    Logger.info(
        f"TRACE: Found total {len(filtered_list)} news between yesterday 8PM and today 8PM"
    )

    return filtered_list
