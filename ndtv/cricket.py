from datetime import datetime, timedelta
import logging as Logger
import pytz
from core.scrapper import fetch_soup
from core.firebase import post_news, Category, OutletCode
from core.summery import extractive_summary
from core.encode import compress_string
from core.types import NewsArticle


# --------------------- Logging Setup ---------------------


Logger.basicConfig(
    level=Logger.INFO,
    format="[%(levelname)s] (%(asctime)s) -> %(message)s",
    handlers=[
        Logger.StreamHandler(),
    ],
)


# --------------------- Constants ---------------------


CRICKET_URL = "https://sports.ndtv.com/cricket/news"
BASE_URL = "https://sports.ndtv.com"
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


def parse_date_to_iso(date_str):
    """
    Convert date to ISO format
    """
    try:
        date_object = datetime.strptime(date_str, "%b %d, %Y")
        return date_object.isoformat()
    except ValueError as e:
        Logger.error(f"ERROR: Unable to parse date {date_str}: {e}")
        return None


# --------------------- Fetch All News Links ---------------------


try:
    base_data = fetch_soup(CRICKET_URL)

    if base_data == None:
        Logger.error(f"ERROR: No data found in {CRICKET_URL}")
        raise

    news_divs = base_data.find_all("div", class_="lst-pg-a")

    if len(news_divs) == 0:
        Logger.error(f"ERROR: No data found in {CRICKET_URL}")
        raise

    news_links = []

    for div in news_divs:
        link = div.find("a", class_="lst-pg_ttl")

        if link and link.get("href"):
            news_links.append(link["href"])

    Logger.info(f"INFO: Fetched {len(news_links)} news links")

    # --------------------- Fetch all news links one by one ---------------------

    news_objects = []

    for link in news_links:
        news_link = f"{BASE_URL}{link}"
        news_soup = fetch_soup(news_link)

        if news_soup == None:
            Logger.warning(f"WARN: No data found in {link}")
            continue

        main_div = news_soup.find("article", class_="vjl-lg-9")

        if main_div == None:
            Logger.warning(f"WARN: No data found in {link}")
            continue

        heading = main_div.find("h1").text if main_div.find("h1") else "Title Not Found"
        subHeading = main_div.find("h2").text if main_div.find("h2") else ""

        nav_div = main_div.find("nav", class_="pst-by")

        timestamp = nav_div.find("meta", {"itemprop": "datePublished"})["content"]
        author = nav_div.find("span", {"itemprop": "name"}).text

        body_content = []

        for p_tag in main_div.find_all("p"):
            if p_tag.find():
                Logger.warning(f"WARN: No data found in {link}")
                continue

            body_content.append(p_tag.text)

        body_text = " ".join(body_content)

        summarized_body = extractive_summary(body_text, percentage=0.34)
        summarized_body = compress_string(summarized_body)
        summarized_sub_heading = extractive_summary(subHeading, percentage=0.8)

        news = NewsArticle(
            tags=[],
            src=news_link,
            body=summarized_body,
            sub_heading=summarized_sub_heading,
            title=heading,
            timestamp=timestamp,
            author=[author],
        )

        news_objects.append(news.to_dict())

    Logger.info(f"INFO: Fetched total {len(news_objects)} news article")

    # --------------------- Save Data ---------------------

    post_news(
        DATA=news_objects,
        current_date=CURRENT_TIME_IST.date(),
        category=Category.CRICKET,
        outlet_code=OutletCode.NDTV,
    )

except Exception as e:
    Logger.critical(f"FATAL: Critical failure during main execution: {e}")
