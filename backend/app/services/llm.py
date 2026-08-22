from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


CLAIM_SCHEMA_HINT = """
Return ONLY valid JSON matching:
{
  "claims": [
    {
      "text": "atomic checkable claim",
      "category": "gurbani_misquote|out_of_context|historical|rehat|propaganda|other",
      "quoted_gurbani": "optional Gurmukhi or romanized verse snippet or null"
    }
  ]
}
Rules:
- Split mixed posts into separate verifiable factual claims.
- Skip pure opinion unless it asserts a false factual premise.
- Prefer category gurbani_misquote when a verse/Ang/Guru attribution is asserted.
- Prefer out_of_context when a real-looking verse is used with misleading framing.
"""

VERDICT_SCHEMA_HINT = """
Return ONLY valid JSON matching:
{
  "verdict": "false|misleading|unverified|true|not_checkable",
  "confidence": 0.0,
  "summary": "plain-language explanation",
  "correction": "accurate information or null",
  "evidence_ids": ["id from provided evidence list only"]
}
Rules:
- You MUST only cite evidence_ids that appear in the provided evidence list.
- If evidence is insufficient, use unverified and never invent citations.
- Every false/misleading/true verdict MUST include at least one evidence_id.
- Distinguish wrong quote vs quote exists but framing is misleading (misleading).
- Do not claim Panthic authority; frame as research-assisted assessment.
"""


async def chat_json(system: str, user: str, *, temperature: float = 0.1) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.llm_enabled:
        return None

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = resp.choices[0].message.content or "{}"
        return json.loads(content)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM call failed: %s", exc)
        return None


def extract_json_object(text: str) -> dict[str, Any] | None:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
