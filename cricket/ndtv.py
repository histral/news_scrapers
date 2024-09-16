import logging
from bs4 import BeautifulSoup
from datetime import datetime
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
        logging.FileHandler("NDTV_BHARAT.log", mode="a"),
    ],
)


# --------------------- Constants ---------------------


CRICKET_URL = "https://sports.ndtv.com/cricket/news"
BASE_URL = "https://sports.ndtv.com"
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


def parse_to_iso(date_str):
    date_object = datetime.strptime(date_str, "%b %d, %Y")

    return date_object.isoformat()


def fetch_soup(URL):
    base_page_data = requests.get(URL)
    base_soup = BeautifulSoup(base_page_data.content, "html.parser")

    return base_soup


def extractive_summary(text, expected_len=1000):
    try:
        parser = PlaintextParser.from_string(text, Tokenizer("english"))
        summarizer = LsaSummarizer()
        sentence_count = 5

        summary = summarizer(parser.document, sentence_count)

        # Gradually reduce sentences until the length is within the limit
        while (
            len(" ".join([str(sentence) for sentence in summary])) > expected_len
            and sentence_count > 1
        ):
            sentence_count -= 1
            summary = summarizer(parser.document, sentence_count)

        # Final check to truncate if slightly over the expected length
        final_summary = " ".join([str(sentence) for sentence in summary])
        return final_summary[:expected_len]
    except Exception as e:
        logging.error(f"Error during extractive summary: {e}")
        return text[:expected_len]  # Fallback to truncating original text


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
        data = {"ndtv": DATA}
        try:
            doc_ref.update(data)
        except Exception as e:
            logging.warning(f"Document update failed, creating a new document: {e}")
            doc_ref.set(data)
        logging.info(f"Uploaded {len(DATA)} summarized articles to Firestore")
    except Exception as e:
        logging.error(f"Error uploading summarized articles to Firestore: {e}")


# --------------------- Fetch All News Links ---------------------


base_data = fetch_soup(CRICKET_URL)
news_divs = base_data.find_all("div", class_="lst-pg-a")

news_links = []

for div in news_divs:
    link = div.find("a", class_="lst-pg_ttl")
    news_links.append(link["href"])

print(f"Fetched {len(news_links)} news links")


# --------------------- Fetch all news links one by one ---------------------


try:
    news_objects = []

    for link in news_links:
        news_link = f"{BASE_URL}{link}"
        news_soup = fetch_soup(news_link)

        main_div = news_soup.find("article", class_="vjl-lg-9")
        heading = main_div.find("h1").text

        if main_div.find("h2"):
            subHeading = main_div.find("h2").text
        else:
            subHeading = ""

        nav_div = main_div.find("nav", class_="pst-by")

        timestamp = nav_div.find("meta", {"itemprop": "datePublished"})["content"]
        author = nav_div.find("span", {"itemprop": "name"}).text

        body_content = []

        for p_tag in main_div.find_all("p"):

            if p_tag.find():
                continue

            body_content.append(p_tag.text)

        body_text = " ".join(body_content)

        expected_body_len = int(round(len(body_text) * 0.34))
        summarized_body = extractive_summary(body_text, expected_body_len)
        summarized_sub_heading = extractive_summary(subHeading, 120)

        news_dict = {
            "title": heading,
            "timestamp": timestamp,
            "author": [author],
            "sub_heading": summarized_sub_heading,
            "body": summarized_body,
            "tags": [],
            "src": news_link,
        }

        news_objects.append(news_dict)

    upload_summarized_articles(news_objects)
except Exception as e:
    logging.critical(f"Critical failure during main execution: {e}")
