"""Function/tool-calling registry for BookRAG.

Each tool is a plain Python function returning a JSON-serializable dict. All use FREE,
no-key APIs (Open-Meteo, Frankfurter, Yahoo Finance, CoinGecko) plus a safe local
calculator and clock — so the agent can fetch live, real-world data during a demo.

Tool selection is done via JSON (portable across models + mockable) rather than native
function-calling; see pipeline.tool_call.
"""
from __future__ import annotations

import ast
import datetime
import operator
import re

import requests

_TIMEOUT = 12
_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}


def _get(url: str, **kw):
    return requests.get(url, timeout=_TIMEOUT, headers=_UA, **kw)


# ---------------------------------------------------------------- currency map
_CURRENCY_MAP = {
    "DOLLAR": "USD", "DOLLARS": "USD", "USD": "USD", "$": "USD", "US DOLLAR": "USD", "US DOLLARS": "USD",
    "EURO": "EUR", "EUROS": "EUR", "EUR": "EUR", "€": "EUR",
    "POUND": "GBP", "POUNDS": "GBP", "GBP": "GBP", "£": "GBP", "STERLING": "GBP",
    "YEN": "JPY", "JPY": "JPY", "¥": "JPY",
    "CAD": "CAD", "AUD": "AUD", "CHF": "CHF", "CNY": "CNY", "INR": "INR", "RUPEE": "INR", "RUPEES": "INR", "₹": "INR",
}


# ---------------------------------------------------------------- calculator (safe)
_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv, ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _safe_eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("unsupported expression")


def calculator(expression: str) -> dict:
    """Evaluate a numeric expression safely (no names/calls)."""
    # Preprocess expression to handle common human-written math notations
    expr = str(expression).replace("^", "**")
    expr = re.sub(r"\b[xX]\b", "*", expr)
    # Remove commas in numbers (e.g. 100,000 -> 100000)
    expr = re.sub(r"(?<=\d),(?=\d)", "", expr)
    # Convert N% of X -> N * 0.01 * X
    expr = re.sub(r"(\d+(?:\.\d+)?)\s*%\s*of\s*", r"(\1 * 0.01) * ", expr)
    expr = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1 * 0.01)", expr)
    
    result = _safe_eval(ast.parse(expr, mode="eval").body)
    if isinstance(result, float) and result == int(result):
        formatted = f"{int(result):,}"
    elif isinstance(result, (int, float)):
        formatted = f"{result:,}"
    else:
        formatted = str(result)
    return {"expression": expression, "result": result, "formatted": formatted}


# ---------------------------------------------------------------- weather (Open-Meteo)
def get_weather(location: str) -> dict:
    # Strip common filler/descriptive words that confuse geocoding APIs
    loc_clean = re.sub(r"\b(today|tomorrow|now|weather|in|at|the|current|forecast)\b", "", location, flags=re.IGNORECASE).strip()
    if not loc_clean:
        loc_clean = location
    g = _get("https://geocoding-api.open-meteo.com/v1/search",
             params={"name": loc_clean, "count": 1}).json()
    if not g.get("results"):
        return {"error": f"location '{location}' not found"}
    r = g["results"][0]
    cur = _get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": r["latitude"], "longitude": r["longitude"],
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
    }).json()["current"]
    return {
        "location": f"{r['name']}, {r.get('country', '')}".strip(", "),
        "temperature_c": cur["temperature_2m"],
        "humidity_pct": cur.get("relative_humidity_2m"),
        "wind_kmh": cur.get("wind_speed_10m"),
    }


# ---------------------------------------------------------------- currency (Frankfurter)
def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict:
    from_curr = str(from_currency).strip().upper()
    to_curr = str(to_currency).strip().upper()
    
    # Try direct mapping
    fr_code = _CURRENCY_MAP.get(from_curr, from_curr)
    to_code = _CURRENCY_MAP.get(to_curr, to_curr)
    
    # Try fuzzy mapping if not matched exactly
    for k, v in _CURRENCY_MAP.items():
        if k in from_curr:
            fr_code = v
            break
    for k, v in _CURRENCY_MAP.items():
        if k in to_curr:
            to_code = v
            break
            
    fr, to = fr_code, to_code
    d = _get("https://api.frankfurter.app/latest", params={"from": fr, "to": to}).json()
    if to not in d.get("rates", {}):
        return {"error": f"cannot convert {fr}->{to}"}
    rate = d["rates"][to]
    return {"amount": float(amount), "from": fr, "to": to, "rate": rate,
            "result": round(float(amount) * rate, 2)}


# ---------------------------------------------------------------- stock (Yahoo Finance via yfinance)
def get_stock_quote(symbol: str) -> dict:
    sym = symbol.upper().strip()

    # Primary: yfinance .history() — downloads OHLCV directly and bypasses
    # Yahoo Finance's aggressive bot-detection on the JSON quote endpoints.
    try:
        import yfinance as yf
        ticker = yf.Ticker(sym)
        hist = ticker.history(period="5d", auto_adjust=True)
        if not hist.empty:
            price = round(float(hist["Close"].iloc[-1]), 4)
            prev = round(float(hist["Close"].iloc[-2]), 4) if len(hist) > 1 else None
            chg = round(price - prev, 2) if prev is not None else None
            pct = round((chg / prev) * 100, 2) if chg is not None and prev else None
            currency = "USD"
            try:
                currency = ticker.fast_info.currency or "USD"
            except Exception:
                pass
            return {"symbol": sym, "price": price, "currency": currency,
                    "previous_close": prev, "change": chg, "change_pct": pct}
    except Exception:
        pass

    return {"error": f"Could not retrieve quote for '{sym}'. Yahoo Finance may be temporarily unavailable."}


# ---------------------------------------------------------------- crypto (CoinGecko)
def get_crypto_price(coin: str, vs_currency: str = "usd") -> dict:
    coin, vs = coin.lower(), vs_currency.lower()
    d = _get("https://api.coingecko.com/api/v3/simple/price",
             params={"ids": coin, "vs_currencies": vs}).json()
    if coin not in d:
        return {"error": f"coin '{coin}' not found (use an id like 'bitcoin', 'ethereum')"}
    return {"coin": coin, "price": d[coin][vs], "vs_currency": vs}


# ---------------------------------------------------------------- time
def get_current_time(timezone: str = "UTC") -> dict:
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(timezone)
    except Exception:
        timezone, tz = "UTC", datetime.timezone.utc
    now = datetime.datetime.now(tz)
    return {"timezone": timezone, "datetime": now.strftime("%Y-%m-%d %H:%M:%S %Z")}


# ---------------------------------------------------------------- registry
FUNCS = {
    "calculator": calculator, "get_weather": get_weather,
    "convert_currency": convert_currency, "get_stock_quote": get_stock_quote,
    "get_crypto_price": get_crypto_price, "get_current_time": get_current_time,
}

# Human-readable menu injected into the tool-selection prompt.
TOOL_MENU = """\
- calculator(expression): evaluate math. Convert word problems to arithmetic, e.g. "15% of 2.3 billion" -> {"expression": "0.15 * 2.3e9"}.
- get_weather(location): current weather for a city, e.g. {"location": "Tokyo"}.
- convert_currency(amount, from_currency, to_currency): FX conversion, e.g. {"amount": 100, "from_currency": "USD", "to_currency": "EUR"}.
- get_stock_quote(symbol): live stock price by ticker, e.g. {"symbol": "NVDA"}.
- get_crypto_price(coin, vs_currency): crypto price, coin is an id like "bitcoin", e.g. {"coin": "bitcoin", "vs_currency": "usd"}.
- get_current_time(timezone): current time, e.g. {"timezone": "America/New_York"}."""


def execute_tool(name: str, args: dict) -> dict:
    fn = FUNCS.get(name)
    if fn is None:
        return {"error": f"unknown tool '{name}'"}
    try:
        return fn(**(args or {}))
    except TypeError as e:
        return {"error": f"bad arguments for {name}: {e}"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"{name} failed: {e}"}
