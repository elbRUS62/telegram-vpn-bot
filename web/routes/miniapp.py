"""Роут страницы Mini App."""

from flask import Blueprint, render_template

from config import BOT_NAME, BOT_VERSION

miniapp_bp = Blueprint('miniapp', __name__)


def _render_miniapp():
    return render_template(
        'miniapp.html',
        bot_name=BOT_NAME,
        bot_version=BOT_VERSION,
    )


@miniapp_bp.route('/miniapp')
def miniapp():
    return _render_miniapp()


@miniapp_bp.route('/v2')
def v2():
    return _render_miniapp()


@miniapp_bp.route('/v3')
def v3():
    """Новый URL — обход кэша."""
    return _render_miniapp()
