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

BASE_URL = "https://www.firstpost.com/"
CRICKET_URL = "https://www.firstpost.com/firstcricket/"

firebase_credentials = {
    "type": "service_account",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "universe_domain": "googleapis.com",
    "project_id": os.getenv("FIREBASE_PROJECT_ID"),
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


def parse_time_to_iso(time):
    try:
        date_object = datetime.strptime(time, "%B %d, %Y, %H:%M:%S %Z")
        return date_object.isoformat()
    except Exception as e:
        logging.error(f"Error parsing time '{time}': {e}")
        return None


def fetch_soup(URL):
    try:
        base_page_data = requests.get(URL)
        base_soup = BeautifulSoup(base_page_data.content, "html.parser")
        return base_soup
    except Exception as e:
        logging.error(f"Error fetching soup from {URL}: {e}")
        return None


def fetch_all_news_links():
    news_links = []
    base_soup = fetch_soup(CRICKET_URL)

    if not base_soup:
        return []

    news_anchors = base_soup.find_all("a", class_=["en-nw-list", "en-nw"])

    for a_tag in news_anchors:
        if a_tag and a_tag["href"]:
            news_links.append(a_tag["href"])

    return news_links


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
            news_date = (
                details_text[-1].strip() if len(details_text) > 1 else "Date not found"
            )
            news_author = (
                details_text[0].strip()
                if details_text[0].strip()
                else "Author not found"
            )
        else:
            news_date, news_author = "Date not found", "Author not found"

        sub_heading_element = news_soup.find("div", class_="art-desc")
        news_sub_heading = (
            sub_heading_element.find("p").find("span").text
            if sub_heading_element and sub_heading_element.find("p")
            else "Sub-heading not found"
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
            "timestamp": parse_time_to_iso(news_date),
            "author": news_author,
            "sub_heading": news_sub_heading,
            "body": news_body,
            "tags": news_tags,
            "src": NEWS_URL,
        }

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
        iso_time = item.get("timestamp")
        if not iso_time:
            logging.warning(
                f"Skipping article due to missing or invalid timestamp: {item}"
            )
            continue

        try:
            date_obj = datetime.fromisoformat(iso_time)
            date_timezone = date_obj.astimezone(ist)

            if yesterday_8pm <= date_timezone <= today_8pm:
                filtered_list.append(item)
        except ValueError as e:
            logging.error(f"Error processing date '{iso_time}': {e}")

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
        doc_ref = DB.collection("cricket").document(doc_id)
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
    news_data = []

    for link in news_links:
        news = fetch_news(BASE_URL + link)

        if news:
            news_data.append(news)

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
