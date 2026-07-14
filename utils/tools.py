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

import requests

_TIMEOUT = 12
_UA = {"User-Agent": "Mozilla/5.0 (BookRAG)"}


def _get(url: str, **kw):
    return requests.get(url, timeout=_TIMEOUT, headers=_UA, **kw)


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
    result = _safe_eval(ast.parse(str(expression), mode="eval").body)
    if isinstance(result, float) and result == int(result):
        formatted = f"{int(result):,}"
    elif isinstance(result, (int, float)):
        formatted = f"{result:,}"
    else:
        formatted = str(result)
    return {"expression": expression, "result": result, "formatted": formatted}


# ---------------------------------------------------------------- weather (Open-Meteo)
def get_weather(location: str) -> dict:
    g = _get("https://geocoding-api.open-meteo.com/v1/search",
             params={"name": location, "count": 1}).json()
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
    fr, to = from_currency.upper(), to_currency.upper()
    d = _get("https://api.frankfurter.app/latest", params={"from": fr, "to": to}).json()
    if to not in d.get("rates", {}):
        return {"error": f"cannot convert {fr}->{to}"}
    rate = d["rates"][to]
    return {"amount": float(amount), "from": fr, "to": to, "rate": rate,
            "result": round(float(amount) * rate, 2)}


# ---------------------------------------------------------------- stock (Yahoo Finance)
def get_stock_quote(symbol: str) -> dict:
    d = _get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}").json()
    res = (d.get("chart", {}).get("result") or [])
    if not res:
        return {"error": f"symbol '{symbol}' not found"}
    m = res[0]["meta"]
    price, prev = m.get("regularMarketPrice"), m.get("chartPreviousClose")
    chg = round(price - prev, 2) if price and prev else None
    pct = round((chg / prev) * 100, 2) if chg is not None and prev else None
    return {"symbol": symbol.upper(), "price": price, "currency": m.get("currency"),
            "previous_close": prev, "change": chg, "change_pct": pct}


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
