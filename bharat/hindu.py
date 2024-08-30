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
        logging.FileHandler("Hindu_BHARAT.log", mode="a"),
    ],
)


# --------------------- Constants ---------------------


NEWS_URL = "https://www.thehindu.com/news/national/"
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
    logging.info("Firebase initialized successfully.")
except Exception as e:
    logging.error(f"Error initializing Firebase: {e}")
    raise


# --------------------- Common Functions ---------------------


def parse_to_iso_with_timezone(date_str):
    try:
        date_str = date_str.replace("IST", "").strip()
        date_object = datetime.strptime(date_str, "%B %d, %Y %I:%M %p")
        date_with_timezone = IST.localize(date_object)
        return date_with_timezone.isoformat()
    except Exception as e:
        logging.error(f"Error parsing date: {e}")
        return None


def fetch_soup(URL):
    try:
        response = requests.get(URL)
        response.raise_for_status()
        return BeautifulSoup(response.content, "html.parser")
    except requests.RequestException as e:
        logging.error(f"Error fetching URL {URL}: {e}")
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
        logging.error(f"Error generating summary: {e}")
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
        current_date_ist = datetime.now(IST).date()
        doc_id = f"{current_date_ist.day}-{current_date_ist.month}-{current_date_ist.year}_bharat"
        doc_ref = DB.collection("bharat").document(doc_id)
        data = {"hindu": DATA}
        try:
            doc_ref.update(data)
            logging.info(f"Updated existing document with {len(DATA)} articles.")
        except Exception:
            doc_ref.set(data)
            logging.info(f"Created new document with {len(DATA)} articles.")
    except Exception as e:
        logging.error(f"Error uploading summarized articles to Firestore: {e}")


# --------------------- Fetch All News Links ---------------------


try:
    base_soup = fetch_soup(NEWS_URL)
    if base_soup is None:
        raise ValueError("Failed to fetch base page soup.")
    links = []
    divs = base_soup.find_all(
        "div",
        class_=lambda c: c in ["element row-element", "element row-element no-border"],
    )
    for div in divs:
        a_tag = div.find("a", href=True)
        if a_tag:
            links.append(a_tag["href"])
    logging.info(f"Found total {len(links)} news links.")
except Exception as e:
    logging.error(f"Error fetching news links: {e}")
    raise


# --------------------- Fetch all news links one by one ---------------------

news_objects = []

for link in links:
    try:
        news_soup = fetch_soup(link)
        if news_soup is None:
            logging.warning(f"Skipping link due to fetch failure: {link}")
            continue

        p_time = news_soup.find("p", class_="publish-time-new")

        if not p_time or "-" not in p_time.text:
            logging.warning(
                f"Publish time not found or invalid format for link: {link}"
            )
            continue

        time_published = p_time.text.split("-")[
            -2 if len(p_time.text.split("-")) >= 3 else -1
        ]

        news_time_iso = parse_to_iso_with_timezone(time_published)

        if not news_time_iso:
            continue

        news_time = datetime.fromisoformat(news_time_iso)

        if CURRENT_TIME_IST.date() != news_time.date():
            continue

        heading = news_soup.find("h1", class_="title").text
        subHeading = news_soup.find("h2", class_="sub-title")
        subHeading = subHeading.text if subHeading else ""

        author = news_soup.find("div", class_="author").text.strip()
        content_div = news_soup.find("div", class_="articlebodycontent")
        content = [
            p_tag.text for p_tag in content_div.find_all("p") if not p_tag.get("class")
        ]

        body = " ".join(content)
        summarized_body = extractive_summary(body, int(round(len(body) * 0.4)))
        summarized_subHeading = (
            extractive_summary(subHeading, 120) if subHeading else ""
        )

        news_dict = {
            "title": heading,
            "timestamp": news_time_iso,
            "author": [author],
            "sub_heading": summarized_subHeading,
            "body": compress_string(summarized_body),
            "tags": [],
            "src": link,
        }
        news_objects.append(news_dict)
        
        logging.info(f"Fetched news: {link}")

    except Exception as e:
        logging.error(f"Error processing link {link}: {e}")

logging.info(f"Fetched {len(news_objects)} news articles for Bharat.")


# --------------------- Save Data ---------------------


try:
    upload_summarized_articles(news_objects)
    logging.info("Saved data successfully.")
except Exception as e:
    logging.error(f"Error saving data: {e}")

