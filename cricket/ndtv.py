import requests
import json
from datetime import datetime
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer
from bs4 import BeautifulSoup
import pytz

# --------------------- Constants ---------------------

CRICKET_URL = "https://sports.ndtv.com/cricket/news"
BASE_URL = "https://sports.ndtv.com"
IST = pytz.timezone("Asia/Kolkata")
CURRENT_TIME_IST = datetime.now(IST)


def parse_to_iso(date_str):
    date_object = datetime.strptime(date_str, "%b %d, %Y")

    return date_object.isoformat()


def fetch_soup(URL):
    base_page_data = requests.get(URL)
    base_soup = BeautifulSoup(base_page_data.content, "html.parser")

    return base_soup


def extractive_summary(text, expected_len=1000):
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


def upload_summarized_articles(DATA):
    try:
        ist = pytz.timezone("Asia/Kolkata")
        current_date_ist = datetime.now(ist).date()
        doc_id = f"{current_date_ist.day}-{current_date_ist.month}-{current_date_ist.year}_bharat"
        doc_ref = db.collection("cricket").document(doc_id)
        data = {"fp": DATA}
        
        try:
            doc_ref.update(data)
        except:
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
        "author": author,
        "sub_heading": summarized_sub_heading,
        "body": summarized_body,
        "tags": [],
        "src": news_link,
    }

    news_objects.append(news_dict)

print(f"Fetched {len(news_objects)} news article about TECH")

# --------------------- Save JSON Data ---------------------

file_name = f"ndtv_cricket_{CURRENT_TIME_IST.day}.json"

with open(file_name, "w", encoding="utf-8") as file:
    json.dump(news_objects, file, ensure_ascii=False)

print(f"Saved JSON data successfully")
