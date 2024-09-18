from datetime import datetime, timedelta
import logging as Logger
import pytz
from histral_core.scraper import fetch_soup
from histral_core.firebase import post_news_list, Category, OutletCode
from histral_core.summery import extractive_summary
from histral_core.encode import encode_text
from histral_core.types import NewsArticle


# --------------------- Logging Setup ---------------------


Logger.basicConfig(
    level=Logger.INFO,
    format="[%(levelname)s] (%(asctime)s) -> %(message)s",
    handlers=[
        Logger.StreamHandler(),
    ],
)

# --------------------- Constants ---------------------


NEWS_URLS = [
    "https://indianstartupnews.com/isn-in-depth",
    "https://indianstartupnews.com/funding",
    "https://indianstartupnews.com/government-policy",
    "https://indianstartupnews.com/news",
    "https://indianstartupnews.com/reports",
    "https://indianstartupnews.com/stories",
    "https://indianstartupnews.com/nextwave-startup-tech-innovation",
]
BASE_URL = "https://indianstartupnews.com"

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
    Adjust the format string to match '15 Sep 2024 23:59'
    """
    try:
        # Check if [date_str] contains "IST" and remove it
        date_str = date_str.replace("IST", "").strip()

        date_object = datetime.strptime(date_str, "%d %b %Y %H:%M")

        date_with_timezone = IST.localize(date_object)

        return date_with_timezone.isoformat()
    except Exception as e:
        Logger.error(f"ERROR: Unable to parse time '{date_str}': {e}")
        return None


# --------------------- Main Execution ---------------------

try:
    news_objects = []

    for URL in NEWS_URLS:
        count = 0
        base_soup = fetch_soup(URL)

        if base_soup == None:
            Logger.critical(f"Error: Unable to scrape for {URL}")
            continue

        main_div = base_soup.find("div", class_="main")

        if main_div == None:
            Logger.critical(f"Error: Main div not found for {URL}")
            continue

        news_divs = main_div.find_all("section", class_="page")

        if news_divs == None or len(news_divs) == 0:
            Logger.critical(f"Error: No news found on {URL}")
            continue

        featured_article = main_div.find("div", class_="article-box")

        news_links = []

        if featured_article and featured_article.find("a"):
            link = featured_article.find("a")["href"]
            news_links.append(BASE_URL + link)

        for div in news_divs:
            link = div.find("a")["href"]
            news_links.append(BASE_URL + link)

        Logger.info(f"TRACE: Found total {len(news_links)} links in {URL}")

        for link in news_links:
            news_soup = fetch_soup(link)

            time_div = news_soup.find("time", class_="date")

            news_time_iso = parse_date_to_iso(time_div.text)
            news_time = datetime.fromisoformat(news_time_iso)

            date_timezone = news_time.astimezone(IST)

            # if news time in smaller then yesterday 8PM or is after today 8PM
            # then skip this news, otherwise scrape it and store it
            if (date_timezone < YESTERDAY_8PM) or (date_timezone > TODAY_8PM):
                continue

            # News Title
            heading = (
                news_soup.find("h1").text if news_soup.find("h1") else "Title not found"
            )

            author_div = news_soup.find("div", class_="author")

            # News Authors
            if author_div:
                author = author_div.text.split("\n")[1]
            else:
                author = None

            body = news_soup.find("div", class_="article")
            body_content = []
            tags = []

            tags_divs = news_soup.find_all("div", class_="tags-category")
            tags_div = tags_divs[-1] if len(tags_divs) > 1 else None

            # News Tags
            if tags_div is None:
                tags = []
            else:
                for a_tag in tags_div.find_all("a"):
                    if a_tag and len(a_tag.text.strip()) > 0:
                        tags.append(a_tag.text)

            for tag in body.find_all(["p", "h2"]):
                body_content.append(tag.text)

            # News Body
            content = " ".join(body_content)
            news_body = extractive_summary(content, percentage=0.6)
            encoded_news_body = encode_text(news_body)

            news = NewsArticle(
                tags=tags,
                author=[author],
                title=heading,
                sub_heading="",
                body=encoded_news_body,
                timestamp=news_time_iso,
                src=link,
            )

            Logger.info(f"TRACE: Fetched news w/ title ({news.title}) from {link}")
            news_objects.append(news.to_dict())
            count += 1

        Logger.info(f"INFO: Fetched *{count} news* from {URL}")

    Logger.info(f"INFO: Fetched *{len(news_objects)} news* articles from ISN")

    post_news_list(
        DATA=news_objects,
        current_date=CURRENT_TIME_IST.date(),
        category=Category.BUSINESS,
        outlet_code=OutletCode.ISN,
    )
except Exception as e:
    Logger.critical(f"FATAL: Critical failure during main execution: {e}")
