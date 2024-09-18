from histral_core.firebase import post_news_list, Category, OutletCode

from firstpost.common import (
    BASE_URL,
    CURRENT_TIME_IST,
    fetch_all_news_links,
    fetch_news,
    filter_news_data,
    Logger,
)


# --------------------- Constants ---------------------


TECH_URL = "https://www.firstpost.com/tech/news-analysis/"


# --------------------- Main Execution ---------------------


try:
    news_links = fetch_all_news_links(TECH_URL)
    news_data = []

    for link in news_links:
        news = fetch_news(BASE_URL + link)

        if news:
            news_data.append(news.to_dict())

    filtered_news_data = filter_news_data(news_data)

    post_news_list(
        DATA=filtered_news_data,
        current_date=CURRENT_TIME_IST.date(),
        category=Category.TECHNOLOGY,
        outlet_code=OutletCode.FP,
    )

    Logger.info(
        f"INFO: Posted total *{len(filtered_news_data)}* news articles to firestore"
    )

except Exception as e:
    Logger.critical(f"FATAL: Critical failure during main execution: {e}")
