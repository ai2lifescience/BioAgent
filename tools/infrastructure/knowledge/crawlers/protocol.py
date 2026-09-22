"""Crawler contracts contain documents and crawl limits, never RAG storage."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ..models import KnowledgePage


ProgressCallback = Callable[[dict], None]


@dataclass(frozen=True)
class CrawlRequest:
    request: str
    seed_urls: list[str]
    allowed_domains: list[str]
    max_pages: int = 20
    max_depth: int = 1

    def __post_init__(self) -> None:
        if not 1 <= self.max_pages <= 100 or not 0 <= self.max_depth <= 3:
            raise ValueError("Crawls require 1–100 pages and depth 0–3.")


class Crawler(Protocol):
    async def crawl(self, request: CrawlRequest, progress: ProgressCallback | None = None) -> list[KnowledgePage]: ...
