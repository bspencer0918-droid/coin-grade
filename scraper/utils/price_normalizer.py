"""
Price normalization — converts all prices to USD.
Fetches exchange rates once per pipeline run and caches them in memory.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# In-memory exchange rate cache (refreshed each pipeline run)
_rates: dict[str, float] = {"USD": 1.0}

# Fallback rates (updated periodically — used when API is unavailable)
_FALLBACK_RATES: dict[str, float] = {
    "USD": 1.00,
    "GBP": 1.27,
    "EUR": 1.08,
    "CHF": 1.10,
    "CAD": 0.74,
    "AUD": 0.65,
}


def load_exchange_rates(api_key: str = "") -> None:
    """
    Fetch current rates from exchangeratesapi.io.
    Falls back to hardcoded rates if API is unavailable or key is missing.
    """
    global _rates
    if not api_key:
        logger.warning("No EXCHANGE_RATE_API_KEY set, using fallback rates.")
        _rates = _FALLBACK_RATES.copy()
        return

    try:
        url = f"https://api.exchangeratesapi.io/v1/latest?access_key={api_key}&base=EUR&symbols=USD,GBP,CHF,CAD,AUD"
        resp = httpx.get(url, timeout=10)
        data = resp.json()
        if data.get("success"):
            raw = data["rates"]   # EUR-based
            eur_to_usd = raw.get("USD", 1.08)
            _rates = {
                "USD": 1.0,
                "EUR": eur_to_usd,
                "GBP": eur_to_usd / raw.get("GBP", 0.85),
                "CHF": eur_to_usd / raw.get("CHF", 0.93),
                "CAD": eur_to_usd / raw.get("CAD", 1.46),
                "AUD": eur_to_usd / raw.get("AUD", 1.66),
            }
            logger.info(f"Exchange rates loaded: {_rates}")
        else:
            _rates = _FALLBACK_RATES.copy()
    except Exception as e:
        logger.warning(f"Exchange rate fetch failed: {e}. Using fallback rates.")
        _rates = _FALLBACK_RATES.copy()


def to_usd(amount: float, currency: str) -> float:
    """Convert amount in given currency to USD."""
    rate = _rates.get(currency.upper(), _FALLBACK_RATES.get(currency.upper(), 1.0))
    return round(amount * rate, 2)


def normalize_currency_symbol(raw: str) -> str:
    """Convert currency symbols to ISO codes."""
    raw = raw.strip()
    mapping = {"$": "USD", "£": "GBP", "€": "EUR", "CHF": "CHF", "CA$": "CAD", "AU$": "AUD"}
    return mapping.get(raw, raw.upper())


def parse_price(raw_price: str) -> tuple[Optional[float], str]:
    """
    Parse a price string like "$1,250", "£980", "€1.200,00"
    Returns (amount_float, currency_iso) or (None, "USD")
    """
    raw = raw_price.strip()
    currency = "USD"

    # Detect currency prefix
    for symbol, iso in [("CA$", "CAD"), ("AU$", "AUD"), ("£", "GBP"), ("€", "EUR"), ("$", "USD"), ("CHF", "CHF")]:
        if raw.startswith(symbol):
            currency = iso
            raw = raw[len(symbol):]
            break

    # Remove thousands separators and normalize decimal
    raw = re.sub(r"[,\s]", "", raw)   # type: ignore[attr-defined]  # handled below
    raw = raw.replace(",", ".")

    import re
    cleaned = re.sub(r"[^\d.]", "", raw)
    try:
        return float(cleaned), currency
    except ValueError:
        return None, currency
