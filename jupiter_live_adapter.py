from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

import requests


JUPITER_BASE_URL = "https://lite-api.jup.ag/tokens/v2"
DEFAULT_BAR_SECONDS = 3600

# Jupiter's public docs show SOL's canonical mint directly.
SOL_MINT = "So11111111111111111111111111111111111111112"

# Strategy symbols are mapped to Jupiter-supported public assets.
# BTC intentionally resolves to a wrapped BTC asset rather than a random BTC-named token.
DEFAULT_SYMBOL_QUERIES: dict[str, tuple[str, ...]] = {
    "BTC": ("WBTC", "cbBTC", "xBTC", "zBTC"),
    "ETH": ("ETH", "WETH"),
    "SOL": (SOL_MINT, "SOL"),
}


@dataclass(frozen=True)
class JupiterResolvedAsset:
    requested_symbol: str
    mint: str
    asset_symbol: str
    name: str
    query_used: str


@dataclass(frozen=True)
class JupiterTokenSnapshot:
    requested_symbol: str
    mint: str
    asset_symbol: str
    name: str
    usd_price: float
    volume_1h: float
    liquidity: float
    price_block_id: int | None
    updated_at: str | None
    raw: dict[str, Any]


@dataclass
class _SymbolBucket:
    start_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    sample_count: int = 1

    def update(self, price: float, volume: float) -> None:
        if self.sample_count == 0:
            self.open = self.high = self.low = self.close = price
            self.volume = volume
            self.sample_count = 1
            return

        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume = volume
        self.sample_count += 1

    def to_bar(self, symbol: str, funding_rate: float = 0.0) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "timestamp": self.start_ms,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "funding_rate": funding_rate,
        }


class JupiterPublicMarketDataClient:
    def __init__(self, *, timeout: float = 20.0, session: requests.Session | None = None):
        self.timeout = float(timeout)
        self.session = session or requests.Session()
        self._asset_cache: dict[str, JupiterResolvedAsset] = {}

    def close(self) -> None:
        self.session.close()

    def search_tokens(self, query: str) -> list[dict[str, Any]]:
        response = self.session.get(
            f"{JUPITER_BASE_URL}/search",
            params={"query": query},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError(f"unexpected Jupiter search payload type: {type(payload)!r}")
        return [item for item in payload if isinstance(item, dict)]

    def resolve_asset(self, requested_symbol: str) -> JupiterResolvedAsset:
        cached = self._asset_cache.get(requested_symbol.upper())
        if cached is not None:
            return cached

        queries = DEFAULT_SYMBOL_QUERIES.get(requested_symbol.upper(), (requested_symbol,))
        best: tuple[tuple[float, float, float, float], JupiterResolvedAsset] | None = None

        for query in queries:
            for token in self.search_tokens(query):
                asset = self._candidate_asset(requested_symbol, query, token)
                if asset is None:
                    continue
                score = self._score_candidate(query, token)
                if best is None or score > best[0]:
                    best = (score, asset)

            if best is not None:
                break

        if best is None:
            raise RuntimeError(f"could not resolve Jupiter asset for symbol={requested_symbol!r}")

        self._asset_cache[requested_symbol.upper()] = best[1]
        return best[1]

    def fetch_snapshots(self, requested_symbols: list[str]) -> dict[str, JupiterTokenSnapshot]:
        assets = [self.resolve_asset(symbol) for symbol in requested_symbols]
        mint_query = ",".join(asset.mint for asset in assets)
        response = self.session.get(
            f"{JUPITER_BASE_URL}/search",
            params={"query": mint_query},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError(f"unexpected Jupiter snapshot payload type: {type(payload)!r}")

        by_mint = {str(item.get("id")): item for item in payload if isinstance(item, dict)}
        snapshots: dict[str, JupiterTokenSnapshot] = {}
        for asset in assets:
            token = by_mint.get(asset.mint)
            if token is None:
                token = self.search_tokens(asset.mint)
                token = token[0] if token else None
            if token is None:
                raise RuntimeError(f"missing Jupiter market data for {asset.requested_symbol} ({asset.mint})")
            snapshots[asset.requested_symbol] = self._build_snapshot(asset, token)
        return snapshots

    def describe_universe(self, requested_symbols: list[str]) -> dict[str, dict[str, str]]:
        return {
            symbol: {
                "mint": asset.mint,
                "asset_symbol": asset.asset_symbol,
                "name": asset.name,
                "query_used": asset.query_used,
            }
            for symbol in requested_symbols
            if (asset := self.resolve_asset(symbol))
        }

    def _candidate_asset(
        self,
        requested_symbol: str,
        query: str,
        token: dict[str, Any],
    ) -> JupiterResolvedAsset | None:
        mint = str(token.get("id") or "").strip()
        asset_symbol = str(token.get("symbol") or "").strip()
        name = str(token.get("name") or "").strip()
        if not mint or not asset_symbol:
            return None
        return JupiterResolvedAsset(
            requested_symbol=requested_symbol.upper(),
            mint=mint,
            asset_symbol=asset_symbol,
            name=name,
            query_used=query,
        )

    def _score_candidate(self, query: str, token: dict[str, Any]) -> tuple[float, float, float, float]:
        symbol = str(token.get("symbol") or "")
        mint = str(token.get("id") or "")
        is_verified = 1.0 if token.get("isVerified") else 0.0
        liquidity = float(token.get("liquidity") or 0.0)
        organic = float(token.get("organicScore") or 0.0)

        exact_match = 0.0
        if query.upper() == mint.upper():
            exact_match = 2.0
        elif symbol.upper() == query.upper():
            exact_match = 1.0

        return (exact_match, is_verified, liquidity, organic)

    def _build_snapshot(self, asset: JupiterResolvedAsset, token: dict[str, Any]) -> JupiterTokenSnapshot:
        stats1h = token.get("stats1h") or {}
        buy_volume = float(stats1h.get("buyVolume") or 0.0)
        sell_volume = float(stats1h.get("sellVolume") or 0.0)
        return JupiterTokenSnapshot(
            requested_symbol=asset.requested_symbol,
            mint=asset.mint,
            asset_symbol=asset.asset_symbol,
            name=asset.name,
            usd_price=float(token.get("usdPrice") or 0.0),
            volume_1h=max(0.0, buy_volume + sell_volume),
            liquidity=float(token.get("liquidity") or 0.0),
            price_block_id=int(token["priceBlockId"]) if token.get("priceBlockId") is not None else None,
            updated_at=str(token.get("updatedAt") or "") or None,
            raw=token,
        )


class JupiterLiveMarketFeed:
    def __init__(
        self,
        client: JupiterPublicMarketDataClient,
        symbols: list[str],
        *,
        bar_seconds: int = DEFAULT_BAR_SECONDS,
        fill_gaps: bool = True,
    ):
        self.client = client
        self.symbols = [symbol.upper() for symbol in symbols]
        self.bar_seconds = int(bar_seconds)
        self.bar_ms = self.bar_seconds * 1000
        self.fill_gaps = bool(fill_gaps)

        self._current_bucket_start_ms: int | None = None
        self._buckets: dict[str, _SymbolBucket] = {}
        self._last_close: dict[str, float] = {}

    def poll(self, now_ms: int | None = None) -> list[dict[str, dict[str, Any]]]:
        now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
        bucket_start = (now_ms // self.bar_ms) * self.bar_ms
        snapshots = self.client.fetch_snapshots(self.symbols)

        if self._current_bucket_start_ms is None:
            self._start_bucket(bucket_start, snapshots)
            return []

        if bucket_start < self._current_bucket_start_ms:
            raise RuntimeError(
                "Jupiter feed clock moved backwards: "
                f"{bucket_start} < {self._current_bucket_start_ms}"
            )

        if bucket_start == self._current_bucket_start_ms:
            self._update_bucket(snapshots)
            return []

        emitted = [self._finalize_current_bucket()]
        self._current_bucket_start_ms = self._current_bucket_start_ms + self.bar_ms

        while self.fill_gaps and self._current_bucket_start_ms < bucket_start:
            emitted.append(self._make_gap_bucket(self._current_bucket_start_ms))
            self._current_bucket_start_ms += self.bar_ms

        self._start_bucket(bucket_start, snapshots)
        return emitted

    def _start_bucket(self, bucket_start_ms: int, snapshots: dict[str, JupiterTokenSnapshot]) -> None:
        self._current_bucket_start_ms = bucket_start_ms
        self._buckets = {}
        for symbol in self.symbols:
            snapshot = snapshots.get(symbol)
            if snapshot is None:
                snapshot = self._carry_forward_snapshot(symbol)
            self._buckets[symbol] = _SymbolBucket(
                start_ms=bucket_start_ms,
                open=snapshot.usd_price,
                high=snapshot.usd_price,
                low=snapshot.usd_price,
                close=snapshot.usd_price,
                volume=snapshot.volume_1h,
            )

    def _update_bucket(self, snapshots: dict[str, JupiterTokenSnapshot]) -> None:
        for symbol in self.symbols:
            snapshot = snapshots.get(symbol)
            if snapshot is None:
                snapshot = self._carry_forward_snapshot(symbol)
            bucket = self._buckets[symbol]
            bucket.update(snapshot.usd_price, snapshot.volume_1h)

    def _finalize_current_bucket(self) -> dict[str, dict[str, Any]]:
        emitted = {symbol: bucket.to_bar(symbol) for symbol, bucket in self._buckets.items()}
        for symbol, bucket in self._buckets.items():
            self._last_close[symbol] = bucket.close
        return emitted

    def _make_gap_bucket(self, bucket_start_ms: int) -> dict[str, dict[str, Any]]:
        emitted: dict[str, dict[str, Any]] = {}
        for symbol in self.symbols:
            close = self._last_close.get(symbol)
            if close is None:
                close = self._buckets[symbol].close
            emitted[symbol] = {
                "symbol": symbol,
                "timestamp": bucket_start_ms,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 0.0,
                "funding_rate": 0.0,
            }
        return emitted

    def _carry_forward_snapshot(self, symbol: str) -> JupiterTokenSnapshot:
        close = self._last_close.get(symbol)
        if close is None and symbol in self._buckets:
            close = self._buckets[symbol].close
        if close is None:
            raise RuntimeError(f"missing live market data for {symbol} and no carry-forward value is available")
        return JupiterTokenSnapshot(
            requested_symbol=symbol,
            mint="",
            asset_symbol=symbol,
            name=symbol,
            usd_price=close,
            volume_1h=0.0,
            liquidity=0.0,
            price_block_id=None,
            updated_at=None,
            raw={},
        )
