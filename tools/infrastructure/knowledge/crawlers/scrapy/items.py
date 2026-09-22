"""Internal Scrapy item shape."""
from __future__ import annotations

from scrapy.item import Field, Item


class KnowledgeItem(Item):
    url = Field()
    title = Field()
    text = Field()
    depth = Field()


__all__ = ["KnowledgeItem"]
