"""Локальное определение ASN/оператора по IP без внешнего lookup."""

import ipaddress
import sqlite3

from config import DB_PATH


def _normalize_ip(value):
    if not value:
        return None
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    if address.version == 6 and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address


def lookup_operator(ip_value: str):
    """Возвращает (ASN, оператор) или (None, 'unknown') для IPv6/неизвестного."""
    address = _normalize_ip(ip_value)
    if address is None or address.version != 4:
        return None, "unknown"

    number = int(address)
    try:
        connection = sqlite3.connect(DB_PATH, timeout=3)
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT asn, operator, end FROM asn_ranges "
            "WHERE start <= ? ORDER BY start DESC LIMIT 1",
            (number,),
        ).fetchone()
        connection.close()
    except Exception:
        return None, "unknown"

    if not row or row["end"] < number:
        return None, "unknown"
    return int(row["asn"]), row["operator"] or "unknown"
