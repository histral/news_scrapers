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

BASE_URL = "https://www.ndtv.com/india"
IST = pytz.timezone("Asia/Kolkata")
CURRENT_TIME_IST = datetime.now(IST)

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
        date_object = datetime.strptime(date_str.strip(), "%A %B %d %Y")
        return date_object.isoformat()
    except ValueError as e:
        logging.error(f"Error parsing date {date_str}: {e}")
        return None


def fetch_soup(URL):
    try:
        base_page_data = requests.get(URL)
        base_page_data.raise_for_status()  # Ensure request was successful
        base_soup = BeautifulSoup(base_page_data.content, "html.parser")
        return base_soup
    except requests.RequestException as e:
        logging.error(f"Error fetching URL {URL}: {e}")
        return None


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
        doc_ref = DB.collection("bharat").document(doc_id)
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
        logging.error(f"Failed to fetch page {page_link}. Exiting loop.")
        break

    news_divs = base_data.find_all("div", class_=["news_Itm"])

    if len(news_divs) == 0:
        logging.info("No more news divs found, stopping pagination.")
        break

    for news in news_divs:
        posted_by = news.find("span", class_=["posted-by"])

        if posted_by is None:
            continue

        date_str = " ".join(posted_by.text.split("|")[-1].split(",")[0:2])

        news_date = parse_date_to_iso(date_str)
        if not news_date:
            continue  # Skip if date parsing failed

        date_obj = datetime.fromisoformat(news_date)

        if CURRENT_TIME_IST.date() == date_obj.date():
            link = news.find("a")["href"]
            news_links.append(link)
        else:
            should_break = True
            break

    if should_break:
        break

    page += 1

logging.info(f"Fetched total {len(news_links)} news links")

# --------------------- Fetch all news links one by one ---------------------

news_objects = []

for link in news_links:
    news_soup = fetch_soup(link)
    if not news_soup:
        logging.error(f"Failed to fetch article from {link}")
        continue

    try:
        content_div = news_soup.find("div", class_="content")

        h2 = content_div.find("h2")
        nav_div = content_div.find("nav", class_="pst-by")
        authors_span = nav_div.find("span", {"itemprop": "author"})

        heading = content_div.find("h1").text
        subHeading = h2.text if h2 else ""
        timestamp = nav_div.find("span", {"itemprop": "dateModified"})["content"]
        author = authors_span.find("span", {"itemprop": "name"}).text
        body_div = content_div.find("div", {"itemprop": "articleBody"})
        body_content = []

        for p_tag in body_div.find_all("p"):
            if p_tag.find():
                continue
            body_content.append(p_tag.text)

        body_text = " ".join(body_content)

        expected_body_len = int(round(len(body_text) * 0.25))
        summarized_body = extractive_summary(body_text, expected_body_len)
        summarized_sub_heading = extractive_summary(subHeading, 120)

        news_dict = {
            "title": heading,
            "timestamp": timestamp,
            "author": [author],
            "sub_heading": summarized_sub_heading,
            "body": compress_string(summarized_body),
            "tags": [],
            "src": link,
        }

        news_objects.append(news_dict)
        logging.info(f"Fetched news: {link}")
        
    except Exception as e:
        logging.error(f"Error processing news link {link}: {e}")

logging.info(f"Fetched {len(news_objects)} news articles about BHARAT")

# --------------------- Save Data ---------------------

upload_summarized_articles(news_objects)

logging.info("Saved data successfully")
