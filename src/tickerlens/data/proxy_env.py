"""Work around malformed proxy env vars breaking httpx.

httpx's ``get_environment_proxies()`` turns each ``no_proxy`` entry into a
mount key. Bracketed IPv6 literals (``[::1]``) — which some runtimes inject
into ``no_proxy`` — are not recognized by its ``is_ipv6_hostname`` check, so
they fall through to the ``all://*<host>`` branch and ``URLPattern`` raises
``InvalidURL``. The exception escapes ``httpx.Client()`` construction itself,
meaning a single bad env entry breaks every HTTP call in the process.

Fix: rewrite bracketed IPv6 literals to their bare form (``[::1]`` → ``::1``)
in ``no_proxy``/``NO_PROXY`` before httpx ever reads the environment. The bare
form is handled correctly and matches the same host.
"""

from __future__ import annotations

import os
import re

_BRACKETED_IPV6 = re.compile(r"^\[([0-9a-fA-F:]+)\]$")


def _clean_entry(entry: str) -> str:
    entry = entry.strip()
    m = _BRACKETED_IPV6.match(entry)
    if m:
        return m.group(1)
    return entry


def sanitize_proxy_env() -> bool:
    """Rewrite bracketed IPv6 literals in no_proxy/NO_PROXY.

    Returns True if any entry was changed.
    """
    changed = False
    for var in ("no_proxy", "NO_PROXY"):
        raw = os.environ.get(var)
        if not raw:
            continue
        entries = [e.strip() for e in raw.split(",")]
        cleaned = [_clean_entry(e) for e in entries]
        if cleaned != entries:
            os.environ[var] = ",".join(cleaned)
            changed = True
    return changed
