"""Веб-админка: вход по одноразовой ссылке из Telegram и оболочка интерфейса."""

import hmac
import secrets
from functools import wraps

from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from config import BOT_USERNAME, WEB_ADMIN_SESSION_HOURS
from permissions import get_admin_role, is_superadmin
from web.utils.webadmin_auth import audit, consume_login_token

webadmin_bp = Blueprint("webadmin", __name__, url_prefix="/admin")


def _csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def _csrf_ok():
    expected = session.get("csrf_token", "")
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
    return bool(expected) and hmac.compare_digest(expected, supplied)


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not g.get("admin_id"):
            return redirect(url_for("webadmin.login"))
        return fn(*args, **kwargs)

    return wrapper


def superadmin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not g.get("admin_id"):
            return redirect(url_for("webadmin.login"))
        if not g.get("admin_is_superadmin"):
            return "Доступно только суперадмину", 403
        return fn(*args, **kwargs)

    return wrapper


@webadmin_bp.after_request
def secure_webadmin_response(response):
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@webadmin_bp.before_request
def load_webadmin_user():
    g.admin_id = session.get("admin_id")
    g.admin_role = None
    g.admin_is_superadmin = False

    if not g.admin_id:
        return None

    role = get_admin_role(g.admin_id)
    if not role:
        session.clear()
        g.admin_id = None
        return None

    g.admin_role = role
    g.admin_is_superadmin = role == "superadmin" or is_superadmin(g.admin_id)
    return None


@webadmin_bp.context_processor
def inject_webadmin_context():
    return {
        "webadmin_role": g.get("admin_role"),
        "webadmin_is_superadmin": g.get("admin_is_superadmin", False),
        "bot_username": BOT_USERNAME,
    }


@webadmin_bp.route("/login")
def login():
    if g.get("admin_id"):
        return redirect(url_for("webadmin.index"))

    error = None
    token = (request.args.get("token") or "").strip()
    if token:
        try:
            admin_id = consume_login_token(token)
        except Exception:
            admin_id = None

        if admin_id is None:
            error = "Ссылка недействительна или уже использована. Получи новую в боте."
        else:
            role = get_admin_role(admin_id)
            if not role:
                error = "У этого аккаунта больше нет доступа к админке."
            else:
                session.clear()
                session.permanent = True
                session["admin_id"] = admin_id
                session["csrf_token"] = secrets.token_urlsafe(32)
                try:
                    audit(admin_id, "webadmin_login")
                except Exception:
                    pass
                return redirect(url_for("webadmin.index"))

    return render_template(
        "admin/login.html",
        error=error,
        bot_username=BOT_USERNAME,
    )


@webadmin_bp.route("")
@login_required
def index():
    return render_template(
        "admin/index.html",
        csrf_token=_csrf_token(),
        admin_role=g.get("admin_role"),
        admin_id=g.get("admin_id"),
        is_superadmin=g.get("admin_is_superadmin", False),
        bot_username=BOT_USERNAME,
        session_hours=WEB_ADMIN_SESSION_HOURS,
    )


@webadmin_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    if not _csrf_ok():
        return "Неверный CSRF-токен", 403

    admin_id = g.get("admin_id")
    try:
        audit(admin_id, "webadmin_logout")
    except Exception:
        pass
    session.clear()
    flash("Вы вышли из веб-админки.", "info")
    return redirect(url_for("webadmin.login"))
