from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from market_signal.providers.gdelt import GDELTArticle
from market_signal.providers.kis import DailyOHLCBar


@dataclass(frozen=True)
class DailyBriefing:
    symbol: str
    trade_date: date
    open: Decimal
    close: Decimal
    open_to_close_return: Decimal
    close_to_close_return: Decimal | None
    epu_z: Decimal | None
    epu_status: str
    articles: tuple[GDELTArticle, ...]
    interpretation: str


def build_daily_briefing(
    *,
    symbol: str,
    bar: DailyOHLCBar,
    previous_bar: DailyOHLCBar | None,
    epu_z: Decimal | None,
    articles: list[GDELTArticle],
) -> DailyBriefing:
    open_to_close_return = (bar.close - bar.open) / bar.open
    close_to_close_return = None
    if previous_bar is not None:
        close_to_close_return = (bar.close - previous_bar.close) / previous_bar.close
    epu_status = _epu_status(epu_z)
    return DailyBriefing(
        symbol=symbol,
        trade_date=bar.date,
        open=bar.open,
        close=bar.close,
        open_to_close_return=open_to_close_return,
        close_to_close_return=close_to_close_return,
        epu_z=epu_z,
        epu_status=epu_status,
        articles=tuple(articles),
        interpretation=_interpret(
            open_to_close_return=open_to_close_return,
            close_to_close_return=close_to_close_return,
            epu_status=epu_status,
            articles=articles,
        ),
    )


def format_daily_briefing_message(briefing: DailyBriefing) -> str:
    lines = [
        f"[QQQ Daily Close Brief] {briefing.trade_date.isoformat()}",
        f"open: {briefing.open}",
        f"close: {briefing.close}",
        f"open_to_close: {_pct(briefing.open_to_close_return)}",
        f"close_to_close: {_pct_or_na(briefing.close_to_close_return)}",
        f"EPU: {briefing.epu_status} ({_z_or_na(briefing.epu_z)})",
        "",
        "news headlines:",
    ]
    if briefing.articles:
        for index, article in enumerate(briefing.articles[:5], start=1):
            lines.append(f"{index}. {article.title} ({article.domain})")
            lines.append(f"   {article.url}")
    else:
        lines.append("No GDELT headlines found for the query.")
    lines.extend(["", "interpretation:", briefing.interpretation])
    return "\n".join(lines)


def _interpret(
    *,
    open_to_close_return: Decimal,
    close_to_close_return: Decimal | None,
    epu_status: str,
    articles: list[GDELTArticle],
) -> str:
    move = close_to_close_return if close_to_close_return is not None else open_to_close_return
    direction = "상승" if move > 0 else "하락" if move < 0 else "보합"
    keywords = _headline_keywords(articles)

    parts = [f"QQQ는 {direction} 마감했습니다."]
    if keywords:
        parts.append(f"헤드라인상 주요 맥락은 {', '.join(keywords)}입니다.")
    if epu_status == "extreme":
        parts.append("뉴스 기반 정책 불확실성이 극단 구간이라 포지션 과확대는 피하는 쪽이 좋습니다.")
    elif epu_status == "elevated":
        parts.append("뉴스 불확실성이 평소보다 높아 변동성 확대 가능성을 같이 봐야 합니다.")
    else:
        parts.append("뉴스 불확실성은 극단 구간은 아닙니다.")
    return " ".join(parts)


def _headline_keywords(articles: list[GDELTArticle]) -> list[str]:
    text = " ".join(article.title.lower() for article in articles)
    mapping = [
        ("Fed/금리", ("fed", "federal reserve", "rate", "interest")),
        ("물가/CPI", ("inflation", "cpi", "prices")),
        ("경기침체", ("recession", "slowdown")),
        ("기술주/Nasdaq", ("nasdaq", "tech", "ai", "semiconductor")),
        ("실적", ("earnings", "outlook", "forecast")),
    ]
    found: list[str] = []
    for label, words in mapping:
        if any(word in text for word in words):
            found.append(label)
    return found[:3]


def _epu_status(epu_z: Decimal | None) -> str:
    if epu_z is None:
        return "unknown"
    if epu_z >= Decimal("2.0"):
        return "extreme"
    if epu_z >= Decimal("1.25"):
        return "elevated"
    return "normal"


def _pct(value: Decimal) -> str:
    return f"{value * Decimal('100'):+.2f}%"


def _pct_or_na(value: Decimal | None) -> str:
    if value is None:
        return "n/a"
    return _pct(value)


def _z_or_na(value: Decimal | None) -> str:
    if value is None:
        return "z=n/a"
    return f"z={value:.2f}"
