"""Роут страницы Mini App."""

from flask import Blueprint, render_template

miniapp_bp = Blueprint('miniapp', __name__)


@miniapp_bp.route('/miniapp')
def miniapp():
    return render_template('miniapp.html')


@miniapp_bp.route('/v2')
def v2():
    return render_template('miniapp.html')


@miniapp_bp.route('/v3')
def v3():
    """Новый URL — обход кэша."""
    return render_template('miniapp.html')
