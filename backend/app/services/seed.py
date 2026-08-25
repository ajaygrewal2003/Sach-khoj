from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import KnownFalseClaim
from app.services.knowledge_base import get_knowledge_base

logger = logging.getLogger(__name__)


async def seed_known_false_claims(session: AsyncSession) -> int:
    """Seed DB known-false table from curated JSON if empty."""
    existing = await session.scalar(select(KnownFalseClaim).limit(1))
    if existing:
        return 0

    settings = get_settings()
    path = settings.curated_path / "known_false_claims.json"
    if not path.exists():
        logger.warning("known_false_claims.json missing at %s", path)
        return 0

    data = json.loads(path.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else data.get("claims", [])
    count = 0
    for item in items:
        session.add(
            KnownFalseClaim(
                id=item.get("id"),
                claim_pattern=item["claim_pattern"],
                category=item.get("category") or "propaganda",
                explanation=item.get("explanation") or "",
                correction=item.get("correction") or "",
                source_refs=item.get("source_refs"),
            )
        )
        count += 1
    await session.commit()
    get_knowledge_base().load(force=True)
    logger.info("Seeded %s known-false claims", count)
    return count
