import os
from datetime import datetime, timedelta

import feedparser
import requests
from dotenv import load_dotenv
load_dotenv(override=True)

from database import db_execute, db_fetchall

# Key name: NEWS_API_KEY (per .env spec)
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
if not NEWS_API_KEY:
    print("[WARN] NEWS_API_KEY missing — NewsAPI calls disabled, using RSS only")

ET_RSS_FEEDS = [
    "https://economictimes.indiatimes.com/markets/stocks/news/rssfeeds/2146842.cms",
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "https://economictimes.indiatimes.com/indices/rssfeeds/7771602.cms",
]

COMPANY_NAMES = {
    "RELIANCE": "Reliance Industries",
    "TCS": "Tata Consultancy Services",
    "INFY": "Infosys",
    "HDFCBANK": "HDFC Bank",
    "ICICIBANK": "ICICI Bank",
    "TATAMOTORS": "Tata Motors",
    "WIPRO": "Wipro",
    "BAJFINANCE": "Bajaj Finance",
    "SUNPHARMA": "Sun Pharma",
    "ITC": "ITC Limited",
    "SBIN": "State Bank India",
    "ADANIENT": "Adani Enterprises",
    "MARUTI": "Maruti Suzuki",
    "NESTLEIND": "Nestle India",
    "POWERGRID": "Power Grid Corporation",
}


def fetch_et_rss() -> list:
    articles = []
    for url in ET_RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:15]:
                articles.append(
                    {
                        "headline": entry.get("title", ""),
                        "source": "ET Markets",
                        "url": entry.get("link", ""),
                        "published_at": entry.get("published", ""),
                        "symbol": None,
                    }
                )
        except Exception as e:
            print(f"[RSS] Error parsing {url}: {e}")
    return articles


def fetch_newsapi(query: str, symbol: str = None) -> list:
    if not NEWS_API_KEY:
        return []
    try:
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 10,
                "apiKey": NEWS_API_KEY,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return [
            {
                "headline": a.get("title", ""),
                "source": a.get("source", {}).get("name", "NewsAPI"),
                "url": a.get("url", ""),
                "published_at": a.get("publishedAt", ""),
                "symbol": symbol,
            }
            for a in resp.json().get("articles", [])
        ]
    except Exception as e:
        print(f"[NewsAPI] Error for {query}: {e}")
        return []


def get_stock_news(symbol: str, max_age_minutes: int = 15) -> list:
    cutoff = (datetime.utcnow() - timedelta(minutes=max_age_minutes)).isoformat()
    cached = db_fetchall(
        "SELECT * FROM news_cache WHERE symbol=? AND fetched_at > ? ORDER BY published_at DESC LIMIT 8",
        (symbol.upper(), cutoff),
    )
    if cached:
        return cached

    articles = fetch_newsapi(f"{symbol} NSE India stock", symbol=symbol.upper())
    company = COMPANY_NAMES.get(symbol.upper())
    if company:
        articles += fetch_newsapi(company, symbol=symbol.upper())

    # Also enrich with ET RSS headlines relevant to symbol
    rss_articles = fetch_et_rss()

    seen, unique = set(), []
    for a in articles + rss_articles:
        if a["url"] not in seen and a["headline"]:
            seen.add(a["url"])
            unique.append(a)

    try:
        db_execute("DELETE FROM news_cache WHERE symbol=?", (symbol.upper(),))
        for a in unique[:8]:
            db_execute(
                "INSERT INTO news_cache (symbol, headline, source, url, published_at) VALUES (?,?,?,?,?)",
                (symbol.upper(), a["headline"], a["source"], a["url"], a["published_at"]),
            )
    except Exception as e:
        print(f"[NewsCache] DB error: {e}")

    return unique[:8]


def get_market_headlines(n: int = 5) -> list:
    try:
        articles = fetch_et_rss()
        return [a["headline"] for a in articles[:n]]
    except Exception as e:
        print(f"[Headlines] Error: {e}")
        return []
