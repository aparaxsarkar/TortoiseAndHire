"""Root of the first-party exception hierarchy.

Every deliberate error raised by TortoiseAndHire code derives from
`TortoiseError`. Layer-specific hierarchies (`sources/` gets `SourceError`,
`api/` maps these to HTTP problem responses) all root here, so a single
`except TortoiseError` can distinguish "our code said no" from an unexpected
crash.
"""

from __future__ import annotations


class TortoiseError(Exception):
    """Base class for all first-party errors.

    `http_status` / `http_title` say how the API should render this if it reaches
    the request boundary unhandled - so `app/api/` never has to import specific
    exception subclasses to map them.
    """

    http_status: int = 400
    http_title: str = "Bad Request"


class ConfigError(TortoiseError):
    """Configuration is missing or invalid."""

    http_status = 500
    http_title = "Internal Server Error"
