from __future__ import annotations

from market_signal.providers.gdelt import GDELTArticle, parse_gdelt_articles, parse_yahoo_finance_rss


def test_parse_gdelt_articles_cleans_titles_and_deduplicates_urls() -> None:
    articles = parse_gdelt_articles(
        {
            "articles": [
                {"title": "  Stock   market today  ", "domain": "example.com", "url": "https://a.test"},
                {"title": "Duplicate", "domain": "example.com", "url": "https://a.test"},
                {"title": "BTC crypto shock", "domain": "example.com", "url": "https://crypto.test"},
                {"title": "", "domain": "example.com", "url": "https://b.test"},
            ]
        }
    )

    assert articles == [
        GDELTArticle(title="Stock market today", domain="example.com", url="https://a.test")
    ]


def test_parse_yahoo_finance_rss() -> None:
    xml_text = """
    <rss>
      <channel>
        <item>
          <title>QQQ rises after Fed decision</title>
          <link>https://finance.yahoo.com/news/qqq</link>
        </item>
        <item>
          <title>BTC crypto update</title>
          <link>https://finance.yahoo.com/news/btc</link>
        </item>
      </channel>
    </rss>
    """

    articles = parse_yahoo_finance_rss(xml_text)

    assert articles == [
        GDELTArticle(
            title="QQQ rises after Fed decision",
            domain="finance.yahoo.com",
            url="https://finance.yahoo.com/news/qqq",
        )
    ]
