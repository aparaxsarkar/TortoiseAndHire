"""Root of the first-party exception hierarchy.

Every deliberate error raised by TortoiseAndHire code derives from
`TortoiseError`. Layer-specific hierarchies (`sources/` gets `SourceError`,
`api/` maps these to HTTP problem responses) all root here, so a single
`except TortoiseError` can distinguish "our code said no" from an unexpected
crash.
"""

from __future__ import annotations


class TortoiseError(Exception):
    """Base class for all first-party errors."""


class ConfigError(TortoiseError):
    """Configuration is missing or invalid."""
