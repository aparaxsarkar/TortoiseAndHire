"""Run ingestion for the sources in `config/sources.yml` (or a subset).

    python -m scripts.run_ingestion                # every configured source
    python -m scripts.run_ingestion greenhouse     # just one
    python -m scripts.run_ingestion --json         # machine-readable report

Used by the `ingest` GitHub Actions workflow. Needs `DATABASE_URL` (and the
`sources` rows seeded - run `scripts.seed_sources` first). Exits non-zero if any
source's run ends `failed`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import yaml

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.models.enums import RunTrigger
from app.services.ingestion import IngestionService
from app.sources.registry import available

log = get_logger("scripts.run_ingestion")


def load_plan(path: str | Path) -> dict[str, list[str]]:
    """`config/sources.yml` -> `{slug: [targets]}`, validated against the registry."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    configured = (raw or {}).get("sources") or {}
    known = set(available())
    plan: dict[str, list[str]] = {}
    for slug, targets in configured.items():
        if slug not in known:
            raise SystemExit(f"{path}: {slug!r} is not a known source (have: {sorted(known)})")
        cleaned = [str(t).strip() for t in (targets or []) if str(t).strip()]
        if cleaned:
            plan[slug] = cleaned
    return plan


async def _run(only: list[str], *, as_json: bool) -> int:
    settings = get_settings()
    plan = load_plan(settings.sources_config_path)
    if only:
        plan = {slug: targets for slug, targets in plan.items() if slug in only}
    if not plan:
        log.warning("run_ingestion.nothing_to_do", requested=only or "all")
        return 0

    report = await IngestionService().run_all(plan=plan, trigger=RunTrigger.SCHEDULED.value)

    if as_json:
        print(json.dumps(report.model_dump(mode="json"), indent=2, default=str))
    else:
        for r in report.results:
            log.info(
                "run_ingestion.source",
                source=r.source,
                status=r.status,
                inserted=r.inserted,
                updated=r.updated,
                filtered_out=r.filtered_out,
                failed=r.failed,
                error=r.error_summary,
            )
    return 1 if any(r.status == "failed" for r in report.results) else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ingestion for the configured sources.")
    parser.add_argument("sources", nargs="*", help="limit to these source slugs")
    parser.add_argument("--json", action="store_true", dest="as_json", help="print a JSON report")
    args = parser.parse_args()

    configure_logging(get_settings())
    raise SystemExit(asyncio.run(_run(args.sources, as_json=args.as_json)))


if __name__ == "__main__":
    main()
