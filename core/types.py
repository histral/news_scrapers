from dataclasses import dataclass, field
from typing import List


@dataclass
class NewsArticle:
    title: str
    timestamp: str
    body: str
    src: str
    sub_heading: str = ""
    author: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def __init__(
        self,
        title: str,
        timestamp: str,
        body: str,
        src: str,
        sub_heading: str = "",
        author: List[str] = None,
        tags: List[str] = None,
    ):
        self.title = title
        self.timestamp = timestamp
        self.body = body
        self.src = src
        self.sub_heading = sub_heading
        self.author = author if author is not None else []
        self.tags = tags if tags is not None else []

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "timestamp": self.timestamp,
            "author": self.author,
            "sub_heading": self.sub_heading,
            "body": self.body,
            "tags": self.tags,
            "src": self.src,
        }
