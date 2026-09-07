"""The relevance ruleset - `config/discovery.yml` parsed and validated.

Pure: `load_ruleset()` takes a path, so this module has no dependency on
settings. The caller (the ingestion service) passes
`get_settings().discovery_ruleset_path`.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Ruleset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str
    target_functions: list[str]
    target_levels: list[str] = Field(default_factory=list)
    exclude_title_tokens: list[str] = Field(default_factory=list)
    max_experience_years: int = 3
    include_internships: bool = False
    locations: list[str] | None = None


def load_ruleset(path: str | Path) -> Ruleset:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a YAML mapping at the top level")
    return Ruleset.model_validate(raw)
