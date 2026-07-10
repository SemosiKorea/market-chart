from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from time import sleep
from xml.etree import ElementTree

import httpx


GDELT_DOC_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
DEFAULT_MARKET_NEWS_QUERY = (
    '(QQQ OR Nasdaq OR "Federal Reserve" OR inflation OR "interest rates" OR recession) '
    "sourcecountry:US sourcelang:english"
)
YAHOO_FINANCE_RSS_URL = "https://finance.yahoo.com/rss/headline"


@dataclass(frozen=True)
class GDELTArticle:
    title: str
    domain: str
    url: str


def fetch_market_headlines(
    *,
    target_date: date,
    query: str = DEFAULT_MARKET_NEWS_QUERY,
    max_records: int = 5,
    timeout: float = 30.0,
    max_attempts: int = 3,
) -> list[GDELTArticle]:
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": str(max_records),
        "sort": "HybridRel",
        "startdatetime": f"{target_date:%Y%m%d}000000",
        "enddatetime": f"{target_date:%Y%m%d}235959",
    }
    for attempt in range(1, max_attempts + 1):
        response = httpx.get(GDELT_DOC_API_URL, params=params, timeout=timeout)
        if response.status_code == 429 and attempt < max_attempts:
            sleep(10 * attempt)
            continue
        response.raise_for_status()
        return parse_gdelt_articles(response.json())
    return []


def parse_gdelt_articles(data: object) -> list[GDELTArticle]:
    if not isinstance(data, dict):
        return []
    raw_articles = data.get("articles")
    if not isinstance(raw_articles, list):
        return []

    articles: list[GDELTArticle] = []
    seen_urls: set[str] = set()
    for item in raw_articles:
        if not isinstance(item, dict):
            continue
        title = _clean_title(item.get("title"))
        url = item.get("url")
        domain = item.get("domain")
        if not title or not isinstance(url, str) or not isinstance(domain, str):
            continue
        if _is_low_signal_market_headline(title):
            continue
        if url in seen_urls:
            continue
        articles.append(GDELTArticle(title=title, domain=domain, url=url))
        seen_urls.add(url)
    return articles


def fetch_yahoo_finance_headlines(
    *,
    symbol: str,
    max_records: int = 5,
    timeout: float = 30.0,
) -> list[GDELTArticle]:
    response = httpx.get(
        YAHOO_FINANCE_RSS_URL,
        params={"s": symbol},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=timeout,
        follow_redirects=True,
    )
    response.raise_for_status()
    return parse_yahoo_finance_rss(response.text)[:max_records]


def parse_yahoo_finance_rss(xml_text: str) -> list[GDELTArticle]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []
    articles: list[GDELTArticle] = []
    for item in root.findall(".//item"):
        title = _clean_title(item.findtext("title"))
        link = _clean_title(item.findtext("link"))
        if not title or not link:
            continue
        if _is_low_signal_market_headline(title):
            continue
        articles.append(GDELTArticle(title=title, domain="finance.yahoo.com", url=link))
    return articles


def _clean_title(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _is_low_signal_market_headline(title: str) -> bool:
    lower = title.lower()
    noisy_terms = ("btc", "bitcoin", "crypto", "shiba", "cardano", "pepe")
    return any(term in lower for term in noisy_terms)
