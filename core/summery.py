import logging as Logger

from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer
from sumy.parsers.plaintext import PlaintextParser

Logger.basicConfig(
    level=Logger.INFO,
    format="[%(levelname)s] (%(asctime)s) -> %(message)s",
    handlers=[
        Logger.StreamHandler(),
    ],
)


def extractive_summary(text: str, percentage: float = 0.25) -> str:
    """
    Summarize [str] locally with max length calculated with respect 
    to [percentage] and max len is `1200`
    """
    expected_len = min(len(text) * percentage, 1200)

    try:
        parser = PlaintextParser.from_string(text, Tokenizer("english"))
        summarizer = LsaSummarizer()
        sentence_count = 6
        summary = summarizer(parser.document, sentence_count)

        while (
            len(" ".join([str(sentence) for sentence in summary])) > expected_len
            and sentence_count > 1
        ):
            sentence_count -= 1
            summary = summarizer(parser.document, sentence_count)

        final_summary = " ".join([str(sentence) for sentence in summary])
        return final_summary
    except Exception as e:
        Logger.error(f"ERROR: Error occurred during summarization: {e}")
        return text[:expected_len]
