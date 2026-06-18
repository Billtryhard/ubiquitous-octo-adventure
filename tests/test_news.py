from datetime import date

from portfolio_monitor import Storage, load_positions
from portfolio_monitor.news import (
    Headline,
    NewsAnalysis,
    SyntheticHeadlineProvider,
    compute_news,
    get_news,
    position_context,
)
from portfolio_monitor.models import Position


class StubAnalyzer:
    """Records calls so we can assert caching prevents re-billing."""

    def __init__(self):
        self.calls = 0

    def analyze(self, ticker, asof, headlines, position_context):
        self.calls += 1
        return NewsAnalysis(
            ticker=ticker, asof=asof, status="ok",
            summary=f"{ticker}: synthetic summary",
            sentiment="neutral",
            key_drivers=["earnings"],
            position_flag=None,
            headline_count=len(headlines),
            model="stub",
            est_cost_usd=0.0012,
        )


def test_synthetic_headlines_deterministic():
    prov = SyntheticHeadlineProvider()
    a = prov.get_headlines("AAPL", date(2026, 6, 17), 3)
    b = prov.get_headlines("AAPL", date(2026, 6, 17), 3)
    assert [h.title for h in a] == [h.title for h in b]
    assert all(h.published_at.date() <= date(2026, 6, 17) for h in a)


def test_position_context_describes_holdings():
    opt = Position(asset_type="option", ticker="AAPL", option_type="call", strike=190,
                   expiry=date(2026, 9, 18), entry_price=8.5, contracts=5)
    sh = Position(asset_type="shares", ticker="AAPL", entry_price=175.4, contracts=200)
    ctx = position_context([opt, sh])
    assert "call 190" in ctx and "200 shares" in ctx


def test_compute_news_with_stub_and_caching(tmp_path):
    db = tmp_path / "p.db"
    positions = load_positions("positions.json")
    asof = date(2026, 6, 17)
    analyzer = StubAnalyzer()

    storage = Storage(str(db))
    first = compute_news(positions, asof, storage, analyzer=analyzer)
    tickers = sorted({p.ticker for p in positions})
    assert len(first) == len(tickers)
    assert all(r.status == "ok" for r in first)
    assert analyzer.calls == len(tickers)

    # Second run on the same day must hit the cache — no new analyzer calls.
    second = compute_news(positions, asof, storage, analyzer=analyzer)
    assert analyzer.calls == len(tickers)  # unchanged
    assert {r.ticker for r in second} == set(tickers)

    # Persisted and retrievable
    cached = get_news(storage, asof, "AAPL")
    assert cached is not None and cached.status == "ok"
    storage.close()


def test_no_news_cache_rebills(tmp_path):
    db = tmp_path / "p.db"
    positions = load_positions("positions.json")
    asof = date(2026, 6, 17)
    analyzer = StubAnalyzer()
    storage = Storage(str(db))
    compute_news(positions, asof, storage, analyzer=analyzer)
    n = analyzer.calls
    compute_news(positions, asof, storage, analyzer=analyzer, use_cache=False)
    assert analyzer.calls == 2 * n  # re-ran every name
    storage.close()


def test_skips_gracefully_without_analyzer(tmp_path, monkeypatch):
    # No analyzer passed and no API key -> skipped, not crashed, not cached.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    db = tmp_path / "p.db"
    positions = load_positions("positions.json")
    asof = date(2026, 6, 17)
    storage = Storage(str(db))
    results = compute_news(positions, asof, storage)
    assert all(r.status == "skipped" for r in results)
    assert all(r.reason for r in results)
    # skips are not cached
    assert get_news(storage, asof, "AAPL") is None
    storage.close()


class _FakeBlock:
    type = "text"
    def __init__(self, text):
        self.text = text


class _FakeUsage:
    input_tokens = 1200
    output_tokens = 180


class _FakeMessage:
    def __init__(self, text):
        self.content = [_FakeBlock(text)]
        self.usage = _FakeUsage()


class _FakeMessages:
    def __init__(self, payload):
        self.payload = payload
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        import json
        return _FakeMessage(json.dumps(self.payload))


class _FakeClient:
    def __init__(self, payload):
        self.messages = _FakeMessages(payload)


def test_claude_analyzer_builds_call_and_parses():
    from portfolio_monitor.news import ClaudeNewsAnalyzer, NEWS_SCHEMA, DEFAULT_MODEL

    payload = {
        "summary": "Earnings beat expectations.",
        "sentiment": "positive",
        "key_drivers": ["earnings", "guidance"],
        "position_flag": "Earnings land before the Sep expiry.",
    }
    client = _FakeClient(payload)
    analyzer = ClaudeNewsAnalyzer(client=client)
    headlines = [Headline(title="AAPL beats on earnings", publisher="Wire",
                          published_at=__import__("datetime").datetime(2026, 6, 16))]
    res = analyzer.analyze("AAPL", date(2026, 6, 17), headlines, "call 190 exp 2026-09-18 x5")

    assert res.status == "ok"
    assert res.sentiment == "positive"
    assert res.key_drivers == ["earnings", "guidance"]
    assert res.position_flag.startswith("Earnings")
    assert res.est_cost_usd is not None and res.est_cost_usd > 0
    # request used the right model and structured-output schema
    kw = client.messages.last_kwargs
    assert kw["model"] == DEFAULT_MODEL
    assert kw["output_config"]["format"]["schema"] is NEWS_SCHEMA
    assert "AAPL beats on earnings" in kw["messages"][0]["content"]


def test_no_headlines_status(tmp_path):
    class EmptyProvider:
        def get_headlines(self, ticker, asof, window_days):
            return []

    db = tmp_path / "p.db"
    positions = load_positions("positions.json")
    storage = Storage(str(db))
    results = compute_news(positions, date(2026, 6, 17), storage,
                           headline_provider=EmptyProvider(), analyzer=StubAnalyzer())
    assert all(r.status == "no_headlines" for r in results)
    storage.close()
