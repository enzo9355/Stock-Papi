"""Canonical application facade during the staged package migration."""

import sys

from stock_papi import application as _legacy_application


sys.modules[__name__] = _legacy_application
