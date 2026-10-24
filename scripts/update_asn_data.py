#!/usr/bin/env python3
"""Обновление локального ASN-справочника для диагностики."""

import gzip
import io
import sqlite3
import urllib.request

from config import DB_PATH

URL = "https://iptoasn.com/data/ip2asn-v4-u32.tsv.gz"


def operator_name(asn: int, description: str) -> str:
    text = (description or "").strip()
    lowered = text.lower()
    if "mts" in lowered or "mobile telesystems" in lowered:
        return "МТС"
    if "veon" in lowered or "vimpel" in lowered or "beeline" in lowered:
        return "Билайн"
    if "megafon" in lowered or "mega fon" in lowered:
        return "МегаФон"
    if "tele2" in lowered or "t2 mobile" in lowered:
        return "Tele2"
    if "yota" in lowered:
        return "Yota"
    if "rostelecom" in lowered:
        return "Ростелеком"
    if "er-telecom" in lowered or "dom.ru" in lowered:
        return "Дом.ру"
    if "ttk" in lowered:
        return "ТТК"
    return text[:80] if text else f"AS{asn}"


def main():
    request = urllib.request.Request(
        URL,
        headers={"User-Agent": "SkrepNet-ASN/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        compressed = response.read()

    rows = []
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as archive:
        for raw in archive:
            line = raw.decode("utf-8", errors="replace").rstrip("\n")
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            try:
                start = int(parts[0])
                end = int(parts[1])
                asn = int(parts[2])
            except ValueError:
                continue
            if asn <= 0 or start > end:
                continue
            description = parts[4] if len(parts) > 4 else ""
            rows.append((start, end, asn, operator_name(asn, description)))

    connection = sqlite3.connect(DB_PATH, timeout=30)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS asn_ranges (
                start INTEGER PRIMARY KEY,
                end INTEGER NOT NULL,
                asn INTEGER NOT NULL,
                operator TEXT NOT NULL DEFAULT 'unknown'
            )
        """)
        connection.execute("DELETE FROM asn_ranges")
        connection.executemany(
            "INSERT INTO asn_ranges(start, end, asn, operator) VALUES (?, ?, ?, ?)",
            rows,
        )
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_asn_ranges_end
            ON asn_ranges(end)
        """)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    print(f"asn ranges loaded: {len(rows)}")


if __name__ == "__main__":
    main()
