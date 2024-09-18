from histral_core.firebase import post_news_list, Category, OutletCode

from hindu.common import CURRENT_TIME_IST, Logger, fetch_all_links, fetch_news_from_link


# --------------------- Constants ---------------------


NEWS_URL = "https://www.thehindu.com/news/national/"


# --------------------- Main Execution ---------------------


try:
    news_objects = []

    news_links = fetch_all_links(NEWS_URL)

    for link in news_links:
        news = fetch_news_from_link(link)

        if news:
            news_objects.append(news.to_dict())

    Logger.info(f"INFO: Fetched total {len(news_objects)} news articles")

    post_news_list(
        DATA=news_objects,
        current_date=CURRENT_TIME_IST.date(),
        category=Category.BHARAT,
        outlet_code=OutletCode.HINDU,
    )
except Exception as e:
    Logger.critical(f"FATAL: Critical failure during main execution: {e}")
