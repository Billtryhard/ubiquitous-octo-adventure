"""Layer 3b — daily Claude news analysis, per held name.

For each underlying in the book we pull recent headlines (default 3-day
window) and send them to Claude through the API, which returns a short factual
summary of what happened, a sentiment read (positive / neutral / negative),
the key drivers, and a flag for anything that specifically affects a held
position.

**Claude summarizes and flags — it does not advise.** It never says buy, sell,
hold, or roll. This is the only paid part of the system; per-call cost is
small, and each name's analysis is cached per day so re-runs don't re-bill.

Everything is pluggable and degrades gracefully:

* ``HeadlineProvider`` — default ``SyntheticHeadlineProvider`` (deterministic,
  offline); a ``YFinanceHeadlineProvider`` is provided for live use.
* ``NewsAnalyzer``     — ``ClaudeNewsAnalyzer`` calls the Anthropic API. If the
  ``anthropic`` SDK is missing or ``ANTHROPIC_API_KEY`` is unset, analysis is
  skipped with a clear status instead of crashing, so the rest of the monitor
  still runs offline.
"""

from __future__ import annotations

import hashlib
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Protocol

from .models import Position
from .storage import Storage

# Model + structured-output schema for the Claude call.
DEFAULT_MODEL = "claude-opus-4-8"

# Opus 4.8 pricing ($ per 1M tokens) for the small cost estimate we surface.
_INPUT_USD_PER_MTOK = 5.0
_OUTPUT_USD_PER_MTOK = 25.0

SENTIMENTS = ("positive", "neutral", "negative")

NEWS_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "sentiment": {"type": "string", "enum": list(SENTIMENTS)},
        "key_drivers": {"type": "array", "items": {"type": "string"}},
        "position_flag": {"type": ["string", "null"]},
    },
    "required": ["summary", "sentiment", "key_drivers", "position_flag"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are a markets news analyst supporting a portfolio monitor. For a single "
    "underlying, you are given recent headlines and a description of the positions "
    "held in that name. Return, strictly as the provided JSON schema:\n"
    "- summary: 1-3 sentences on what actually happened, grounded only in the "
    "headlines. If the headlines are thin or off-topic, say so.\n"
    "- sentiment: positive | neutral | negative — the tone of the news for the "
    "company, not a market call.\n"
    "- key_drivers: the concrete drivers behind the news (e.g. earnings, guidance, "
    "product, legal, macro). Empty list if none are clear.\n"
    "- position_flag: a short note ONLY if something in the news specifically "
    "affects the described position (e.g. earnings dated before an option's expiry, "
    "a move that threatens a strike or stop). Otherwise null.\n\n"
    "IMPORTANT: You summarize and flag facts. You are NOT a trade trigger. Never "
    "recommend buying, selling, holding, rolling, hedging, or sizing. Do not give "
    "advice or predictions — surface what happened and what it touches."
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class Headline:
    title: str
    publisher: str
    published_at: datetime
    url: Optional[str] = None


@dataclass
class NewsAnalysis:
    ticker: str
    asof: date
    status: str                       # "ok" | "no_headlines" | "skipped"
    summary: Optional[str] = None
    sentiment: Optional[str] = None
    key_drivers: List[str] = field(default_factory=list)
    position_flag: Optional[str] = None
    headline_count: int = 0
    model: Optional[str] = None
    est_cost_usd: Optional[float] = None
    reason: Optional[str] = None       # why skipped, if applicable


# ---------------------------------------------------------------------------
# Headline providers
# ---------------------------------------------------------------------------


class HeadlineProvider(ABC):
    @abstractmethod
    def get_headlines(self, ticker: str, asof: date, window_days: int) -> List[Headline]:
        ...


def _unit(*parts) -> float:
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


class SyntheticHeadlineProvider(HeadlineProvider):
    """Deterministic placeholder headlines so the pipeline runs offline.

    These are obviously synthetic; the real signal comes from a live provider.
    Useful for exercising caching and the analyzer wiring in tests.
    """

    _TEMPLATES = [
        ("{t} shares move as analysts revise estimates ahead of earnings", "Synthetic Newswire"),
        ("{t} unveils product update; market reaction mixed", "Synthetic Markets"),
        ("Sector rotation pressures {t} amid macro data", "Synthetic Daily"),
        ("{t} option activity picks up into the next expiry", "Synthetic Options Report"),
    ]

    def get_headlines(self, ticker: str, asof: date, window_days: int) -> List[Headline]:
        n = 1 + int(_unit(ticker, asof.isoformat(), "count") * 3)  # 1..3
        out = []
        for i in range(n):
            tpl, pub = self._TEMPLATES[i % len(self._TEMPLATES)]
            days_back = int(_unit(ticker, asof.isoformat(), i, "age") * window_days)
            out.append(
                Headline(
                    title=tpl.format(t=ticker),
                    publisher=pub,
                    published_at=datetime(asof.year, asof.month, asof.day, tzinfo=timezone.utc)
                    - timedelta(days=days_back),
                )
            )
        return out


class YFinanceHeadlineProvider(HeadlineProvider):
    """Live headlines via yfinance. Best-effort; returns [] on any failure."""

    def get_headlines(self, ticker: str, asof: date, window_days: int) -> List[Headline]:
        try:  # pragma: no cover - network/optional dependency
            import yfinance  # type: ignore

            cutoff = datetime(asof.year, asof.month, asof.day, tzinfo=timezone.utc) - timedelta(
                days=window_days
            )
            items = yfinance.Ticker(ticker).news or []
            out: List[Headline] = []
            for it in items:
                content = it.get("content", it)  # yfinance schema has shifted over versions
                title = content.get("title") or it.get("title")
                if not title:
                    continue
                ts = it.get("providerPublishTime")
                published = (
                    datetime.fromtimestamp(ts, tz=timezone.utc)
                    if ts
                    else datetime.now(timezone.utc)
                )
                if published < cutoff:
                    continue
                pub = (
                    it.get("publisher")
                    or (content.get("provider") or {}).get("displayName")
                    or "unknown"
                )
                url = it.get("link") or (content.get("canonicalUrl") or {}).get("url")
                out.append(Headline(title=title, publisher=pub, published_at=published, url=url))
            return out
        except Exception:
            return []


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class NewsAnalyzer(Protocol):
    def analyze(
        self, ticker: str, asof: date, headlines: List[Headline], position_context: str
    ) -> NewsAnalysis:
        ...


def position_context(positions: List[Position]) -> str:
    """One-line description of the positions held in a single ticker."""
    parts = []
    for p in positions:
        if p.is_option:
            parts.append(
                f"{p.option_type} {p.strike:g} exp {p.expiry.isoformat()} "
                f"x{p.contracts:g} (entry {p.entry_price:g}/sh)"
            )
        else:
            parts.append(f"{p.contracts:g} shares (entry {p.entry_price:g})")
    return "; ".join(parts) if parts else "no position details"


class ClaudeNewsAnalyzer:
    """Summarize a name's headlines via the Anthropic API (structured output)."""

    def __init__(self, model: str = DEFAULT_MODEL, client=None):
        self.model = model
        self._client = client  # injectable for testing

    def _get_client(self):
        if self._client is not None:
            return self._client
        import anthropic  # raises ImportError if the SDK isn't installed

        return anthropic.Anthropic()  # resolves ANTHROPIC_API_KEY from the env

    def analyze(
        self, ticker: str, asof: date, headlines: List[Headline], position_context: str
    ) -> NewsAnalysis:
        client = self._get_client()
        headline_block = "\n".join(
            f"- [{h.published_at.date().isoformat()}] {h.title} ({h.publisher})"
            for h in headlines
        )
        user = (
            f"Underlying: {ticker}\n"
            f"As-of date: {asof.isoformat()}\n"
            f"Position held: {position_context}\n\n"
            f"Recent headlines:\n{headline_block}"
        )
        resp = client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": NEWS_SCHEMA}},
        )
        text = next(b.text for b in resp.content if b.type == "text")
        data = json.loads(text)

        est_cost = None
        usage = getattr(resp, "usage", None)
        if usage is not None:
            inp = getattr(usage, "input_tokens", 0) or 0
            out = getattr(usage, "output_tokens", 0) or 0
            est_cost = round(
                inp / 1_000_000 * _INPUT_USD_PER_MTOK
                + out / 1_000_000 * _OUTPUT_USD_PER_MTOK,
                6,
            )

        return NewsAnalysis(
            ticker=ticker,
            asof=asof,
            status="ok",
            summary=data.get("summary"),
            sentiment=data.get("sentiment"),
            key_drivers=list(data.get("key_drivers") or []),
            position_flag=data.get("position_flag"),
            headline_count=len(headlines),
            model=self.model,
            est_cost_usd=est_cost,
        )


def analyzer_available() -> tuple[bool, str]:
    """Whether a live Claude analysis can run. Returns (ok, reason_if_not)."""
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False, "anthropic SDK not installed"
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False, "ANTHROPIC_API_KEY not set"
    return True, ""


# ---------------------------------------------------------------------------
# Orchestration with per-day caching
# ---------------------------------------------------------------------------


def compute_news(
    positions: List[Position],
    asof: date,
    storage: Storage,
    headline_provider: Optional[HeadlineProvider] = None,
    analyzer: Optional[NewsAnalyzer] = None,
    window_days: int = 3,
    use_cache: bool = True,
) -> List[NewsAnalysis]:
    """Per held name: load cached analysis, else pull headlines and analyze.

    Caching is per (asof_date, ticker) so re-running a day never re-bills the
    API. If no analyzer is available (no SDK / no key), names without a cached
    entry are returned with status ``"skipped"`` and a reason.
    """
    ensure_news_schema(storage)
    headline_provider = headline_provider or SyntheticHeadlineProvider()

    by_ticker: Dict[str, List[Position]] = {}
    for p in positions:
        by_ticker.setdefault(p.ticker, []).append(p)

    ok, skip_reason = (True, "")
    if analyzer is None:
        ok, skip_reason = analyzer_available()
        if ok:
            analyzer = ClaudeNewsAnalyzer()

    results: List[NewsAnalysis] = []
    for ticker in sorted(by_ticker):
        if use_cache:
            cached = get_news(storage, asof, ticker)
            if cached is not None:
                results.append(cached)
                continue

        headlines = headline_provider.get_headlines(ticker, asof, window_days)
        if not headlines:
            res = NewsAnalysis(
                ticker=ticker, asof=asof, status="no_headlines",
                headline_count=0, reason="no headlines in window",
            )
        elif not ok:
            res = NewsAnalysis(
                ticker=ticker, asof=asof, status="skipped",
                headline_count=len(headlines), reason=skip_reason,
            )
        else:
            res = analyzer.analyze(
                ticker, asof, headlines, position_context(by_ticker[ticker])
            )

        # Only persist (cache) a completed analysis — never a skip, so a later
        # run with a key can fill it in.
        if res.status == "ok":
            store_news(storage, res)
        results.append(res)

    return results


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

NEWS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS news_analysis (
    asof_date      TEXT NOT NULL,
    ticker         TEXT NOT NULL,
    status         TEXT NOT NULL,
    summary        TEXT,
    sentiment      TEXT,
    key_drivers    TEXT,            -- JSON array
    position_flag  TEXT,
    headline_count INTEGER NOT NULL,
    model          TEXT,
    est_cost_usd   REAL,
    pulled_at      TEXT NOT NULL,
    PRIMARY KEY (asof_date, ticker)
);
"""


def ensure_news_schema(storage: Storage) -> None:
    storage.conn.executescript(NEWS_SCHEMA_SQL)
    storage.conn.commit()


def store_news(storage: Storage, a: NewsAnalysis) -> None:
    ensure_news_schema(storage)
    with storage._tx() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO news_analysis
               (asof_date, ticker, status, summary, sentiment, key_drivers,
                position_flag, headline_count, model, est_cost_usd, pulled_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                a.asof.isoformat(), a.ticker, a.status, a.summary, a.sentiment,
                json.dumps(a.key_drivers), a.position_flag, a.headline_count,
                a.model, a.est_cost_usd,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )


def get_news(storage: Storage, asof: date, ticker: str) -> Optional[NewsAnalysis]:
    ensure_news_schema(storage)
    row = storage.conn.execute(
        "SELECT * FROM news_analysis WHERE asof_date = ? AND ticker = ?",
        (asof.isoformat(), ticker),
    ).fetchone()
    if row is None:
        return None
    return NewsAnalysis(
        ticker=row["ticker"],
        asof=asof,
        status=row["status"],
        summary=row["summary"],
        sentiment=row["sentiment"],
        key_drivers=json.loads(row["key_drivers"]) if row["key_drivers"] else [],
        position_flag=row["position_flag"],
        headline_count=row["headline_count"],
        model=row["model"],
        est_cost_usd=row["est_cost_usd"],
    )
