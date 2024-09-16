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


def parse_date_to_iso(date_str):
    try:
        date_object = datetime.strptime(date_str, "%d %b %Y %H:%M %Z")

        date_with_timezone = IST.localize(date_object)

        return date_with_timezone.isoformat()
    except Exception as e:
        logging.error(f"Error parsing time '{date_str}': {e}")
        return None


def fetch_soup(URL):
    try:
        base_page_data = requests.get(URL)
        base_soup = BeautifulSoup(base_page_data.content, "html.parser")
        return base_soup
    except Exception as e:
        logging.error(f"Error fetching soup from {URL}: {e}")
        return None


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
        doc_ref = DB.collection("business").document(doc_id)
        data = {"isn": DATA}

        try:
            doc_ref.update(data)
        except:
            doc_ref.set(data)
        logging.info(f"Uploaded {len(DATA)} summarized articles to Firestore")
    except Exception as e:
        logging.error(f"Error uploading summarized articles to Firestore: {e}")


# --------------------- Main Execution ---------------------

try:
    news_objects = []

    yesterday_8pm = CURRENT_TIME_IST.replace(
        hour=20, minute=0, second=0, microsecond=0
    ) - timedelta(days=1)

    today_8pm = CURRENT_TIME_IST.replace(hour=20, minute=0, second=0, microsecond=0)

    count = 0

    for URL in NEWS_URLS:
        base_soup = fetch_soup(URL)

        if base_soup is None:
            logging.critical(f"Error: Unable to scrape for {URL}")
            continue

        main_div = base_soup.find("div", class_="main")

        news_divs = main_div.find_all("section", class_="page")
        featured_article = main_div.find("div", class_="article-box")

        news_links = []

        if featured_article and featured_article.find("a"):
            link = featured_article.find("a")["href"]
            news_links.append(BASE_URL + link)

        for div in news_divs:
            link = div.find("a")["href"]
            news_links.append(BASE_URL + link)

        logging.info(f"Found total {len(news_links)} links in {URL}")

        for link in news_links:
            news_soup = fetch_soup(link)

            time_div = news_soup.find("time", class_="date")

            news_time_iso = parse_date_to_iso(time_div.text)
            news_time = datetime.fromisoformat(news_time_iso)

            date_timezone = news_time.astimezone(IST)

            # if news time in smaller then yesterday 8PM or is after today 8PM
            # then skip this news, otherwise scrape it and store it
            if (date_timezone < yesterday_8pm) or (date_timezone > today_8pm):
                continue

            heading = news_soup.find("h1").text
            author_div = news_soup.find("div", class_="author").text

            author = author_div.split("\n")[1]

            body = news_soup.find("div", class_="article")
            body_content = []
            tags = []

            tags_divs = news_soup.find_all("div", class_="tags-category")
            tags_div = tags_divs[-1] if len(tags_divs) > 1 else None

            if tags_div is None:
                tags = []
            else:
                for a_tag in tags_div.find_all("a"):
                    if a_tag and len(a_tag.text.strip()) > 0:
                        tags.append(a_tag.text)

            for tag in body.find_all(["p", "h2"]):
                body_content.append(tag.text)

            content = " ".join(body_content)

            expected_body_len = int(round(len(content) * 0.6))
            summarized_body = extractive_summary(content, expected_body_len)

            news_dict = {
                "title": heading,
                "timestamp": news_time_iso,
                "author": [author],
                "sub_heading": "",
                "body": compress_string(summarized_body),
                "tags": tags,
                "src": link,
            }

            logging.info(f"Fetched {news_dict['title']} from {link}")
            news_objects.append(news_dict)
            count += 1

        logging.info(f"Fetched {count} news from {URL}")

    logging.info(f"Fetched {len(news_objects)} news article from ISN")
    upload_summarized_articles(news_objects)
except Exception as e:
    logging.critical(f"Critical failure during main execution: {e}")
