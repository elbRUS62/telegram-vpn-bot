import logging

from flask import Blueprint

api = Blueprint("miniapp_api", __name__, url_prefix="/api/miniapp")
logger = logging.getLogger(__name__)
