"""Validate the narrow item boundary before the worker receives documents."""
from __future__ import annotations

from .items import KnowledgeItem


class KnowledgeItemPipeline:
    def process_item(self, item: KnowledgeItem, spider):
        if not str(item.get("url", "")).strip() or not str(item.get("text", "")).strip():
            raise ValueError("Scrapy yielded an empty knowledge document.")
        return item


__all__ = ["KnowledgeItemPipeline"]
