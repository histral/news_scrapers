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


BASE_URL = "https://www.ndtv.com/india"
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
    Adjust the format string to match 'Monday September 16 2024'
    """
    try:
        date_object = datetime.strptime(date_str.strip(), "%A %B %d %Y")
        return date_object.isoformat()
    except ValueError as e:
        Logger.error(f"ERROR: Unable to parse date {date_str}: {e}")
        return None


try:

    # --------------------- Fetch All News Links ---------------------

    page = 1
    news_links = []
    should_break = False

    while True:
        if page > 1:
            page_link = f"page-{page}"
        else:
            page_link = ""

        base_data = fetch_soup(f"{BASE_URL}/{page_link}")

        if not base_data:
            Logger.error(f"ERROR: Failed to fetch page {page_link}. Exiting loop.")
            break

        news_divs = base_data.find_all("div", class_=["news_Itm"])

        if len(news_divs) == 0:
            Logger.info("TRACE: No more news divs found, stopping pagination.")
            break

        for news in news_divs:
            posted_by = news.find("span", class_=["posted-by"])

            if posted_by is None:
                Logger.warning("WARN: Date not found for. Skipping the news.")
                continue  # Skip is no date is found

            try:
                date_str = " ".join(posted_by.text.split("|")[-1].split(",")[0:2])
            except Exception as e:
                Logger.warning("WARN: Date not found for. Error - {e}")
                continue  # Skip if no date is found

            news_date = parse_date_to_iso(date_str)

            if not news_date:
                Logger.warning("WARN: Date not found")
                continue  # Skip if date parsing failed

            try:
                date_obj = datetime.fromisoformat(news_date)
                date_timezone = date_obj.astimezone(IST)

                if YESTERDAY_8PM <= date_timezone <= TODAY_8PM:
                    link = news.find("a")["href"]
                    news_links.append(link)
                else:
                    should_break = True
                    break
            except ValueError:
                Logger.error(f"ERROR: Skipping invalid date format: {news_date}")

        if should_break:
            break

        page += 1

    Logger.info(f"INFO: Fetched total {len(news_links)} news links")

    # --------------------- Fetch all news links one by one ---------------------

    news_objects = []

    for link in news_links:
        news_soup = fetch_soup(link)
        if not news_soup:
            Logger.error(f"Failed to fetch article from {link}")
            continue

        try:
            content_div = news_soup.find("div", class_="content")

            h2 = content_div.find("h2")
            nav_div = content_div.find("nav", class_="pst-by")
            authors_span = nav_div.find("span", {"itemprop": "author"})

            # News Title
            news_title = (
                content_div.find("h1").text
                if content_div.find("h1")
                else "Title not found"
            )

            # News SubHeading
            news_subHeading = (
                content_div.find("h2").text if content_div.find("h2") else ""
            )

            try:
                timestamp = nav_div.find("span", {"itemprop": "dateModified"})[
                    "content"
                ]
                datetime.fromisoformat(timestamp)
            except Exception as e:
                Logger.error(f"ERROR: Timestamp is invalid; URL -> {link}, Error - {e}")
                continue

            if authors_span.find("span", {"itemprop": "name"}):
                author = authors_span.find("span", {"itemprop": "name"}).text
            else:
                author = None

            body_div = content_div.find("div", {"itemprop": "articleBody"})
            body_content = []

            if body_div == None:
                Logger.warning(f"WARN: No content found in -> {link}")
                continue

            for p_tag in body_div.find_all("p"):
                if p_tag.find():
                    continue
                body_content.append(p_tag.text)

            body_text = " ".join(body_content)

            summarized_body = extractive_summary(body_text, percentage=0.25)
            summarized_body = compress_string(summarized_body)
            summarized_sub_heading = extractive_summary(news_subHeading, percentage=0.8)

            news = NewsArticle(
                tags=[],
                author=[author],
                title=news_title,
                sub_heading=summarized_sub_heading,
                body=summarized_body,
                timestamp=timestamp,
                src=link,
            )

            news_objects.append(news.to_dict())
            Logger.info(f"TRACE: Fetched news {link}")

        except Exception as e:
            Logger.error(f"ERROR: Unable to process news link {link}: {e}")

    Logger.info(f"INFO: Fetched {len(news_objects)} news articles about BHARAT")

    # --------------------- Save Data ---------------------

    post_news(
        DATA=news_objects,
        current_date=CURRENT_TIME_IST.date(),
        category=Category.BHARAT,
        outlet_code=OutletCode.NDTV,
    )

except Exception as e:
    Logger.critical(f"FATAL: Critical failure during main execution: {e}")
