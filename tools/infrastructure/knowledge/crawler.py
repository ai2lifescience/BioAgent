"""Compatibility facade for the default HTTP crawler."""
from .crawlers.http import canonical_url, crawl, discover, extract_page, fetch_page, validate_domains

__all__ = ["canonical_url", "crawl", "discover", "extract_page", "fetch_page", "validate_domains"]
