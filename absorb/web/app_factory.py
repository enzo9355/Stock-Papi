"""Canonical import for the existing Flask application factory."""

from stock_papi.web.app_factory import create_app

__all__ = ["create_app"]
