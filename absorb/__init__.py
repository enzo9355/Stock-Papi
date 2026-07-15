"""Canonical ABSORB application package.

The legacy ``stock_papi`` tree remains a compatibility implementation during
the staged package migration. New product code belongs under ``absorb``.
"""

__all__ = ["create_app"]


def create_app(config=None):
    """Load the existing Flask factory lazily to preserve cold-start behavior."""
    from stock_papi.web.app_factory import create_app as legacy_create_app

    return legacy_create_app(config)
