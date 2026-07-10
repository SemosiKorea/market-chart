from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from time import sleep
from typing import Any

import httpx
from pydantic import SecretStr

from market_signal.analysis.qqq_distribution import DailyBar, parse_kis_daily_bars
from market_signal.config import Settings
from market_signal.domain import (
    DataDelayType,
    InstrumentType,
    MarketQuote,
    MarketSession,
    Source,
)
from market_signal.normalization.pricing import classify_qqq_quality


class KISMarketDataError(RuntimeError):
    """Raised when KIS market data requests fail."""


@dataclass(frozen=True)
class DailyOHLCBar:
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


@dataclass(frozen=True)
class KISOverseasQuoteSnapshot:
    exchange: str
    symbol: str
    price_output: dict[str, Any]
    asking_outputs: tuple[dict[str, Any], ...]
    received_at: datetime

    @property
    def max_quote_age(self) -> timedelta:
        return timedelta(seconds=30)

    def to_market_quote(
        self,
        *,
        max_quote_age_seconds: int,
        max_spread_ratio: Decimal,
    ) -> MarketQuote:
        merged = _merge_outputs(self.price_output, *self.asking_outputs)
        last_price = _first_decimal(merged, ("last", "ovrs_nmix_prpr", "stck_prpr", "price"))
        bid_price = _first_decimal(merged, ("pbid1", "pbid", "bidp", "bid_price"))
        ask_price = _first_decimal(merged, ("pask1", "pask", "askp", "ask_price"))
        bid_size = _first_decimal(merged, ("vbid1", "vbid", "bid_size"))
        ask_size = _first_decimal(merged, ("vask1", "vask", "ask_size"))
        reference_price = _first_decimal(merged, ("base", "n_base", "reference_price"))

        quality = classify_qqq_quality(
            bid=bid_price,
            ask=ask_price,
            last_price=last_price,
            quote_timestamp=self.received_at,
            received_at=self.received_at,
            max_quote_age=timedelta(seconds=max_quote_age_seconds),
            max_spread=max_spread_ratio,
        )

        return MarketQuote(
            source=Source.KIS,
            instrument_type=InstrumentType.ETF,
            symbol=self.symbol,
            session=MarketSession.DAYTIME,
            market_timestamp=self.received_at,
            received_at=self.received_at,
            last_price=last_price,
            bid_price=bid_price,
            ask_price=ask_price,
            bid_size=bid_size,
            ask_size=ask_size,
            reference_price=reference_price,
            data_delay_type=DataDelayType.UNKNOWN,
            quality_status=quality.status,
        )


class KISMarketDataClient:
    def __init__(
        self,
        *,
        settings: Settings,
        http_client: httpx.Client,
        access_token: SecretStr,
    ) -> None:
        settings.require_kis_credentials()
        self._settings = settings
        self._http_client = http_client
        self._access_token = access_token

    def get_overseas_price(self, *, exchange: str, symbol: str) -> dict[str, Any]:
        data = self._get_json(
            "/uapi/overseas-price/v1/quotations/price",
            tr_id="HHDFS00000300",
            params={"AUTH": "", "EXCD": exchange, "SYMB": symbol},
        )
        output = data.get("output")
        if not isinstance(output, dict):
            raise KISMarketDataError("KIS overseas price response did not include output object")
        return output

    def get_overseas_asking_price(self, *, exchange: str, symbol: str) -> tuple[dict[str, Any], ...]:
        data = self._get_json(
            "/uapi/overseas-price/v1/quotations/inquire-asking-price",
            tr_id="HHDFS76200100",
            params={"AUTH": "", "EXCD": exchange, "SYMB": symbol},
        )
        outputs: list[dict[str, Any]] = []
        for key in ("output1", "output2", "output3"):
            value = data.get(key)
            outputs.extend(_as_dicts(value))
        if not outputs:
            raise KISMarketDataError("KIS overseas asking price response did not include outputs")
        return tuple(outputs)

    def get_overseas_quote_snapshot(self, *, exchange: str, symbol: str) -> KISOverseasQuoteSnapshot:
        received_at = datetime.now(UTC)
        price_output = self.get_overseas_price(exchange=exchange, symbol=symbol)
        asking_outputs = self.get_overseas_asking_price(exchange=exchange, symbol=symbol)
        return KISOverseasQuoteSnapshot(
            exchange=exchange,
            symbol=symbol,
            price_output=price_output,
            asking_outputs=asking_outputs,
            received_at=received_at,
        )

    def get_overseas_daily_bars_year(
        self,
        *,
        exchange: str,
        symbol: str,
        year: int,
        adjusted: bool = True,
        max_pages: int = 6,
    ) -> list[DailyBar]:
        start_date = datetime(year, 1, 1, tzinfo=UTC).date()
        end_date = datetime(year, 12, 31, tzinfo=UTC).date()
        base_date = f"{year}1231"
        rows_by_date: dict[str, dict[str, Any]] = {}

        for page in range(max_pages):
            data = self._get_json(
                "/uapi/overseas-price/v1/quotations/dailyprice",
                tr_id="HHDFS76240000",
                params={
                    "AUTH": "",
                    "EXCD": exchange,
                    "SYMB": symbol,
                    "GUBN": "0",
                    "BYMD": base_date,
                    "MODP": "1" if adjusted else "0",
                },
            )
            rows = data.get("output2")
            if not isinstance(rows, list) or not rows:
                break

            valid_rows = [row for row in rows if isinstance(row, dict) and isinstance(row.get("xymd"), str)]
            for row in valid_rows:
                xymd = str(row["xymd"])
                if f"{year}0101" <= xymd <= f"{year}1231":
                    rows_by_date[xymd] = row

            earliest = min(str(row["xymd"]) for row in valid_rows)
            if earliest <= f"{year}0101":
                break

            earliest_date = datetime.strptime(earliest, "%Y%m%d").date()
            base_date = (earliest_date - timedelta(days=1)).strftime("%Y%m%d")
            if page < max_pages - 1:
                sleep(self._settings.kis_rate_limit_retry_seconds)

        bars = parse_kis_daily_bars(rows_by_date.values())
        filtered_bars = [bar for bar in bars if start_date <= bar.date <= end_date]
        if len(filtered_bars) < 2:
            raise KISMarketDataError(f"KIS daily bars for {symbol} {year} were insufficient")
        return filtered_bars

    def get_overseas_daily_ohlc_year(
        self,
        *,
        exchange: str,
        symbol: str,
        year: int,
        adjusted: bool = True,
        max_pages: int = 6,
    ) -> list[DailyOHLCBar]:
        rows = self._get_overseas_daily_rows_year(
            exchange=exchange,
            symbol=symbol,
            year=year,
            adjusted=adjusted,
            max_pages=max_pages,
        )
        bars = [_parse_daily_ohlc_row(row) for row in rows]
        filtered_bars = [bar for bar in bars if bar is not None]
        if len(filtered_bars) < 2:
            raise KISMarketDataError(f"KIS daily OHLC bars for {symbol} {year} were insufficient")
        return sorted(filtered_bars, key=lambda bar: bar.date)

    def _get_overseas_daily_rows_year(
        self,
        *,
        exchange: str,
        symbol: str,
        year: int,
        adjusted: bool,
        max_pages: int,
    ) -> list[dict[str, Any]]:
        base_date = f"{year}1231"
        rows_by_date: dict[str, dict[str, Any]] = {}

        for page in range(max_pages):
            data = self._get_json(
                "/uapi/overseas-price/v1/quotations/dailyprice",
                tr_id="HHDFS76240000",
                params={
                    "AUTH": "",
                    "EXCD": exchange,
                    "SYMB": symbol,
                    "GUBN": "0",
                    "BYMD": base_date,
                    "MODP": "1" if adjusted else "0",
                },
            )
            rows = data.get("output2")
            if not isinstance(rows, list) or not rows:
                break

            valid_rows = [row for row in rows if isinstance(row, dict) and isinstance(row.get("xymd"), str)]
            for row in valid_rows:
                xymd = str(row["xymd"])
                if f"{year}0101" <= xymd <= f"{year}1231":
                    rows_by_date[xymd] = row

            earliest = min(str(row["xymd"]) for row in valid_rows)
            if earliest <= f"{year}0101":
                break

            earliest_date = datetime.strptime(earliest, "%Y%m%d").date()
            base_date = (earliest_date - timedelta(days=1)).strftime("%Y%m%d")
            if page < max_pages - 1:
                sleep(self._settings.kis_rate_limit_retry_seconds)

        return list(rows_by_date.values())

    def _get_json(
        self,
        path: str,
        *,
        tr_id: str,
        params: dict[str, str],
    ) -> dict[str, Any]:
        url = f"{self._settings.kis_rest_base_url_text}{path}"
        last_error: KISMarketDataError | None = None
        for attempt in range(1, self._settings.kis_rate_limit_max_attempts + 1):
            try:
                response = self._http_client.get(
                    url,
                    params=params,
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json; charset=UTF-8",
                        "authorization": f"Bearer {self._access_token.get_secret_value()}",
                        "appkey": _secret_value(self._settings.kis_app_key),
                        "appsecret": _secret_value(self._settings.kis_app_secret),
                        "tr_id": tr_id,
                        "custtype": "P",
                    },
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if _is_rate_limit_response(exc.response) and attempt < self._settings.kis_rate_limit_max_attempts:
                    sleep(self._settings.kis_rate_limit_retry_seconds)
                    continue
                raise KISMarketDataError(_format_kis_error(exc.response, "market data")) from exc

            data = _response_json(response)
            rt_cd = data.get("rt_cd")
            if rt_cd in (None, "0", 0):
                return data

            last_error = KISMarketDataError(_format_kis_body_error(data, "market data"))
            if _is_rate_limit_body(data) and attempt < self._settings.kis_rate_limit_max_attempts:
                sleep(self._settings.kis_rate_limit_retry_seconds)
                continue
            raise last_error

        if last_error is not None:
            raise last_error
        raise KISMarketDataError("KIS market data request failed")


def _parse_daily_ohlc_row(row: dict[str, Any]) -> DailyOHLCBar | None:
    xymd = row.get("xymd")
    if not isinstance(xymd, str) or len(xymd) != 8:
        return None
    open_price = _to_decimal(row.get("open"))
    high_price = _to_decimal(row.get("high"))
    low_price = _to_decimal(row.get("low"))
    close_price = _to_decimal(row.get("clos"))
    if None in (open_price, high_price, low_price, close_price):
        return None
    return DailyOHLCBar(
        date=date.fromisoformat(f"{xymd[:4]}-{xymd[4:6]}-{xymd[6:8]}"),
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
    )


def _response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        raise KISMarketDataError("KIS market data response was not valid JSON") from exc
    if not isinstance(data, dict):
        raise KISMarketDataError("KIS market data response JSON was not an object")
    return data


def _format_kis_error(response: httpx.Response, label: str) -> str:
    try:
        data = response.json()
    except ValueError:
        return f"KIS {label} HTTP {response.status_code}: non-JSON response"
    return f"KIS {label} HTTP {response.status_code}: {_format_kis_body_error(data, label)}"


def _format_kis_body_error(data: dict[str, Any], label: str) -> str:
    code = data.get("error_code") or data.get("msg_cd") or data.get("rt_cd") or "unknown"
    message = data.get("error_description") or data.get("msg1") or data.get("message")
    if message:
        return f"{code} {message}"
    return f"KIS {label} error: {code}"


def _is_rate_limit_response(response: httpx.Response) -> bool:
    try:
        data = response.json()
    except ValueError:
        return False
    return isinstance(data, dict) and _is_rate_limit_body(data)


def _is_rate_limit_body(data: dict[str, Any]) -> bool:
    code = str(data.get("error_code") or data.get("msg_cd") or "")
    message = str(data.get("error_description") or data.get("msg1") or data.get("message") or "")
    return code == "EGW00201" or "초당 거래건수" in message


def _secret_value(value: SecretStr | None) -> str:
    if value is None:
        raise KISMarketDataError("required KIS secret was missing")
    return value.get_secret_value()


def _merge_outputs(*outputs: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for output in outputs:
        merged.update(output)
    return merged


def _as_dicts(value: Any) -> tuple[dict[str, Any], ...]:
    if isinstance(value, dict):
        return (value,)
    if isinstance(value, list):
        return tuple(item for item in value if isinstance(item, dict))
    return ()


def _first_decimal(data: dict[str, Any], keys: tuple[str, ...]) -> Decimal | None:
    for key in keys:
        value = data.get(key)
        decimal_value = _to_decimal(value)
        if decimal_value is not None:
            return decimal_value
    return None


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        decimal_value = Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    if decimal_value <= 0:
        return None
    return decimal_value
