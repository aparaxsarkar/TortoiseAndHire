"""Canonicalise a posting URL so it is a stable fallback dedup key (ADR-0002).

Deterministic and lossy on purpose: lowercase scheme/host, drop the default
port, drop the fragment, drop known tracking query params, sort the rest, and
trim a trailing slash. Two URLs that point at the same posting but carry
different `utm_*` tags collapse to the same string.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PREFIXES = ("utm_",)
_TRACKING_KEYS = frozenset(
    {
        "gh_src",
        "gh_jid",
        "ref",
        "referer",
        "referrer",
        "source",
        "src",
        "trk",
        "trackingid",
        "recruiter",
        "rid",
        "lever-source",
        "lever-origin",
        "mc_cid",
        "mc_eid",
        "fbclid",
        "gclid",
        "_hsenc",
        "_hsmi",
    }
)
_DEFAULT_PORTS = {"http": "80", "https": "443"}


def _is_tracking(key: str) -> bool:
    low = key.lower()
    return low in _TRACKING_KEYS or low.startswith(_TRACKING_PREFIXES)


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()

    netloc = host
    if parts.port is not None and str(parts.port) != _DEFAULT_PORTS.get(scheme, ""):
        netloc = f"{host}:{parts.port}"

    path = parts.path or "/"
    if len(path) > 1:
        path = path.rstrip("/") or "/"

    pairs = parse_qsl(parts.query, keep_blank_values=True)
    query = urlencode(sorted((k, v) for k, v in pairs if not _is_tracking(k)))

    return urlunsplit((scheme, netloc, path, query, ""))
