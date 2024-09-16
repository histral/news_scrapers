import os
import firebase_admin
import logging as Logger

from enum import Enum
from typing import List
from firebase_admin import credentials, firestore

Logger.basicConfig(
    level=Logger.INFO,
    format="[%(levelname)s] (%(asctime)s) -> %(message)s",
    handlers=[
        Logger.StreamHandler(),
    ],
)


class Category(Enum):
    BHARAT = "bharat"
    CRICKET = "cricket"
    TECHNOLOGY = "tech"
    USA = "usa"
    BUSINESS = "business"


class OutletCode(Enum):
    FP = "fp"
    NDTV = "ndtv"
    HINDU = "hindu"
    ISN = "isn"
    YS = "ys"


def _get_firestore_db():
    try:
        firebase_credentials = {
            "type": "service_account",
            "universe_domain": "googleapis.com",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "project_id": os.getenv("FIREBASE_PROJECT_ID"),
            "client_id": os.getenv("FIREBASE_CLIENT_ID"),
            "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
            "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
            "private_key": os.getenv("FIREBASE_PRIVATE_KEY").replace("\\n", "\n"),
            "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_X509_CERT_URL"),
        }

        cred = credentials.Certificate(firebase_credentials)
        firebase_admin.initialize_app(cred)
        database = firestore.client()

        Logger.info("INFO: Successfully initialized Firebase client.")

        return database
    except Exception as e:
        Logger.error(f"ERROR: initializing Firebase: {e}")
        raise


def post_news(
    DATA: List,
    current_date,
    category: Category,
    outlet_code: OutletCode,
):
    try:
        DB = _get_firestore_db()
        doc_id = f"{current_date.day}-{current_date.month}-{current_date.year}_bharat"
        doc_ref = DB.collection(category.value).document(doc_id)
        data = {outlet_code.value: DATA}

        try:
            doc_ref.update(data)
            Logger.info(f"INFO: Updated {len(DATA)} news")
        except Exception as e:
            doc_ref.set(data)
            Logger.info(f"INFO: Uploaded {len(DATA)} news")
            Logger.warning(f"WARN: New entry created due to: {e}")
    except Exception as e:
        Logger.error(f"ERROR: Unable to upload news to Firestore: {e}")
