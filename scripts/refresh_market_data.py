"""Fetch a compact TSETMC snapshot for the public Streamlit deployment."""

from datetime import datetime, timezone
import json
from pathlib import Path

import requests

HEADERS = {"User-Agent": "Mozilla/5.0"}
SYMBOLS = ("زر", "فزر")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "market_snapshot.json"


def get(path):
    response = requests.get(f"https://cdn.tsetmc.com/api/{path}", headers=HEADERS, timeout=20)
    response.raise_for_status()
    return response.json()


def instrument(symbol):
    data = get(f"Instrument/GetInstrumentSearch/{requests.utils.quote(symbol)}")
    rows = data.get("instrumentSearch", data)
    if isinstance(rows, dict):
        rows = rows.get("instrumentSearch", rows.get("items", []))
    for row in rows if isinstance(rows, list) else []:
        if str(row.get("lVal18AFC", row.get("symbol", ""))) == symbol:
            return row
    return rows[0] if rows else None


def history(ins_code):
    data = get(f"ClosingPrice/GetClosingPriceDailyList/{ins_code}/365")
    rows = data.get("closingPriceDaily", data)
    if isinstance(rows, dict):
        rows = rows.get("closingPriceDaily", rows.get("items", []))
    return [
        {"date": row.get("dEven"), "close": row.get("pClosing") or row.get("pc"), "volume": row.get("qTotTran5J") or 0}
        for row in (rows if isinstance(rows, list) else [])
    ]


def client(ins_code):
    return get(f"ClientType/GetClientType/{ins_code}/1/0").get("clientType", {})


def main():
    symbols = {}
    for symbol in SYMBOLS:
        item = instrument(symbol)
        if not item or not item.get("insCode"):
            raise RuntimeError(f"Instrument not found: {symbol}")
        ins_code = item["insCode"]
        symbols[symbol] = {"insCode": ins_code, "history": history(ins_code), "client": client(ins_code)}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "symbols": symbols}, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
