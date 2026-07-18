"""Custom Jinja2 environment for Django's Jinja2 template backend.

Registers the `dmy` date filter, exactly as the FastAPI portal did on its
Jinja2Templates instance in dependencies.py — this lets every template
carry over from the FastAPI version unchanged.
"""

import datetime as dt
import re

from jinja2 import Environment


def dmy(value: str) -> str:
    """Formats an AllCloud date string (YYYY-MM-DD, optionally with a time
    suffix) as dd/mm/yy for display. Returns '—' for blank/unparseable
    input rather than raising, since these dates come from external APIs."""
    if not value:
        return "—"
    head = re.split(r"[T ]", value.strip(), maxsplit=1)[0]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(head, fmt).strftime("%d/%m/%y")
        except ValueError:
            continue
    return "—"


def environment(**options):
    env = Environment(**options)
    env.filters["dmy"] = dmy
    return env
