import logging
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer
from firebase_admin import credentials, firestore
from sumy.parsers.plaintext import PlaintextParser
import os, zlib, base64, pytz, requests, firebase_admin

# --------------------- Logging Setup ---------------------


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("FirstPost_BHARAT.log", mode="a"),
    ],
)

# --------------------- Constants ---------------------

BASE_URL = "https://www.firstpost.com"
BHARAT_URL = "https://www.firstpost.com/category/india"

firebase_credentials = {
    "type": "service_account",
    "project_id": "histral",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "universe_domain": "googleapis.com",
    "client_id": os.getenv("FIREBASE_CLIENT_ID"),
    "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
    "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
    "private_key": os.getenv("FIREBASE_PRIVATE_KEY").replace("\\n", "\n"),
    "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_X509_CERT_URL"),
}

try:
    cred = credentials.Certificate(firebase_credentials)
    firebase_admin.initialize_app(cred)
    DB = firestore.client()
    logging.info("Successfully initialized Firebase client.")
except Exception as e:
    logging.error(f"Error initializing Firebase: {e}")
    raise

# --------------------- Common Functions ---------------------


def parse_date_to_iso(date_str):
    try:
        # Adjust the format string to match 'September 13, 2024,12:52:19'
        date_object = datetime.strptime(date_str.strip(), "%B %d, %Y,%H:%M:%S")
        return date_object.isoformat()
    except ValueError as e:
        logging.error(f"Failed to parse time '{date_str}' to ISO: {e}")
        return None


def fetch_soup(URL):
    try:
        base_page_data = requests.get(URL, timeout=10)
        base_page_data.raise_for_status()  # raises HTTPError for bad responses
        base_soup = BeautifulSoup(base_page_data.content, "html.parser")
        return base_soup
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch URL {URL}: {e}")
        return None


def fetch_all_news_links():
    try:
        news_links = []
        base_soup = fetch_soup(BHARAT_URL)
        if not base_soup:
            return news_links

        news_anchors = base_soup.find_all("a", class_=["en-nw-list", "en-nw"])
        for a_tag in news_anchors:
            if a_tag and a_tag["href"]:
                news_links.append(a_tag["href"])

        logging.info(f"Found {len(news_links)} news links")
        return news_links
    except Exception as e:
        logging.error(f"Error fetching news links: {e}")
        return []


def fetch_news(NEWS_URL):
    try:
        news_soup = fetch_soup(NEWS_URL)
        if not news_soup:
            return None

        news_title = (
            news_soup.find("h1").text if news_soup.find("h1") else "Title not found"
        )

        art_details_info = news_soup.find("div", class_="art-dtls-info")
        if art_details_info:
            details_text = art_details_info.text.split("•")
            news_date = details_text[-1].strip() if len(details_text) > 1 else ""
            news_author = details_text[0].strip() if details_text[0].strip() else ""
        else:
            news_date, news_author = "", ""

        if len(news_date) == 0:
            logging.error(f"Error: Date not found for {NEWS_URL}")
            return None

        times_list = news_date.split(",")

        # Check if the last part contains "IST" and remove it
        if "IST" in times_list[-1]:
            times_list[-1] = times_list[-1].replace("IST", "").strip()

        # Join the list back into a string
        news_date = ",".join(times_list)

        sub_heading_element = news_soup.find("div", class_="art-desc")
        sub_heading_p = sub_heading_element.find("p") if sub_heading_element else None
        news_sub_heading = (
            sub_heading_p.find("span").text
            if sub_heading_p
            else "Sub Heading not found"
        )

        news_body_p_list = (
            news_soup.find("div", class_="art-content").find_all("p")
            if news_soup.find("div", class_="art-content")
            else []
        )
        news_body = "".join([p.text for p in news_body_p_list])

        news_tags = []
        tags_data = news_soup.find("div", class_="tag-cont-wp")
        if tags_data:
            news_tags = [
                tag.strip() for tag in tags_data.text.split("\n") if tag.strip()
            ]

        news_dict = {
            "title": news_title,
            "timestamp": parse_date_to_iso(news_date),
            "author": [news_author],
            "sub_heading": news_sub_heading,
            "body": news_body,
            "tags": news_tags,
            "src": NEWS_URL,
        }

        logging.info(f"Fetched news: {NEWS_URL}")
        return news_dict
    except Exception as e:
        logging.error(f"Error fetching news from {NEWS_URL}: {e}")
        return None


def filter_news_data(DATA):
    filtered_list = []
    ist = pytz.timezone("Asia/Kolkata")

    current_time_ist = datetime.now(ist)

    yesterday_8pm = current_time_ist.replace(
        hour=20, minute=0, second=0, microsecond=0
    ) - timedelta(days=1)
    today_8pm = current_time_ist.replace(hour=20, minute=0, second=0, microsecond=0)

    for item in DATA:

        if item is None:
            continue

        iso_time = item["timestamp"]

        try:
            date_obj = datetime.fromisoformat(iso_time)
            date_timezone = date_obj.astimezone(ist)
            if yesterday_8pm <= date_timezone <= today_8pm:
                filtered_list.append(item)
        except ValueError:
            logging.warning(f"Skipping invalid date format: {iso_time}")

    logging.info(
        f"Filtered {len(filtered_list)} articles between yesterday 8PM and today 8PM"
    )
    return filtered_list


def extractive_summary(text, expected_len=1000):
    try:
        parser = PlaintextParser.from_string(text, Tokenizer("english"))
        summarizer = LsaSummarizer()
        sentence_count = 5
        summary = summarizer(parser.document, sentence_count)
        while (
            len(" ".join([str(sentence) for sentence in summary])) > expected_len
            and sentence_count > 1
        ):
            sentence_count -= 1
            summary = summarizer(parser.document, sentence_count)

        final_summary = " ".join([str(sentence) for sentence in summary])
        return final_summary[:expected_len]
    except Exception as e:
        logging.error(f"Error during summarization: {e}")
        return text[:expected_len]


def compress_string(s):
    try:
        compressed = zlib.compress(s.encode())
        return base64.b64encode(compressed).decode()
    except Exception as e:
        logging.error(f"Error compressing string: {e}")
        return s


def upload_summarized_articles(DATA):
    try:
        ist = pytz.timezone("Asia/Kolkata")
        current_date_ist = datetime.now(ist).date()
        doc_id = f"{current_date_ist.day}-{current_date_ist.month}-{current_date_ist.year}_bharat"
        doc_ref = DB.collection("bharat").document(doc_id)
        data = {"fp": DATA}
        try:
            doc_ref.update(data)
        except:
            doc_ref.set(data)
        logging.info(f"Uploaded {len(DATA)} summarized articles to Firestore")
    except Exception as e:
        logging.error(f"Error uploading summarized articles to Firestore: {e}")


# --------------------- Main Execution ---------------------

try:
    news_links = fetch_all_news_links()
    news_data = [
        fetch_news(BASE_URL + link)
        for link in news_links
        if fetch_news(BASE_URL + link)
    ]
    filtered_news_data = filter_news_data(news_data)

    summarized_news = []
    for news in filtered_news_data:

        if news is None:
            continue

        expected_len = min(int(round(len(news["body"]) * 0.34)), 1200)
        body_summary = extractive_summary(news["body"], expected_len=expected_len)
        sub_heading_summary = extractive_summary(news["sub_heading"], expected_len=200)
        news["body"] = compress_string(body_summary)
        news["sub_heading"] = sub_heading_summary
        summarized_news.append(news)

    upload_summarized_articles(summarized_news)
except Exception as e:
    logging.critical(f"Critical failure during main execution: {e}")
