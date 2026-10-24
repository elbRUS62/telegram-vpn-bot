from config import WEB_BASE_URL

_BASE = (WEB_BASE_URL or "").rstrip("/")


def _doc_url(path, fallback):
    return f"{_BASE}{path}" if _BASE else fallback


DOCS = {
    "rules": {
        "title": "Правила использования",
        "url": _doc_url(
            "/docs/rules",
            "https://telegra.ph/Pravila-ispolzovaniya-10-09",
        ),
    },
    "privacy": {
        "title": "Политика конфиденциальности",
        "url": _doc_url(
            "/docs/privacy",
            "https://telegra.ph/Politika-konfidencialnosti-10-09-83",
        ),
    },
    "terms": {
        "title": "Пользовательское соглашение",
        "url": _doc_url(
            "/docs/terms",
            "https://telegra.ph/Polzovatelskoe-soglashenie-10-09-52",
        ),
    },
}
