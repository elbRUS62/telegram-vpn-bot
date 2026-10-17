"""Роуты документов."""

from datetime import datetime

from flask import Blueprint, render_template

docs_bp = Blueprint('docs', __name__)

DOCS_META = {
    "rules": {"title": "Правила использования", "template": "docs/rules.html"},
    "privacy": {"title": "Политика конфиденциальности", "template": "docs/privacy.html"},
    "terms": {"title": "Пользовательское соглашение", "template": "docs/terms.html"},
}


@docs_bp.route('/docs/<doc_key>')
def docs_page(doc_key):
    meta = DOCS_META.get(doc_key)
    if not meta:
        return render_template('error.html', message="Документ не найден"), 404

    return render_template('docs.html',
        title=meta["title"],
        content=render_template(meta["template"]),
        updated=datetime.now().strftime("%d.%m.%Y"))
