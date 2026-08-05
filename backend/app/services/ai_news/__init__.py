"""AI news aggregation: multi-source fetch + LLM curation for daily Feishu push."""
from .sources import NewsItem, fetch_all_candidates

__all__ = ["NewsItem", "fetch_all_candidates"]
