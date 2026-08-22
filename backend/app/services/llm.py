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
      "category": "gurbani_misquote|out_of_context|historical|rehat|doctrine|propaganda|other",
      "quoted_gurbani": "optional Gurmukhi or romanized verse snippet or null"
    }
  ]
}
Rules:
- Split mixed posts into separate verifiable factual claims.
- Skip pure opinion unless it asserts a false factual premise.
- Prefer category doctrine for teachings about Naam, mukti, rituals, Hukam, pilgrimage, diet/meat, or Rehat-as-salvation claims.
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
- Verdict true means the USER CLAIM is accurate. If the claim is wrong, overstated, or fabricated, use false or misleading — never true.
- If a Known False Claims Index row is on-topic, the claim is not true.
- Cite a passage only if it is about the same topic as the claim. Off-topic passages (wrong subject) are not evidence.
- If evidence is insufficient or off-topic, use unverified, set evidence_ids to [], and set correction to null. Never guess from model memory.
- Every false/misleading/true verdict MUST include at least one on-topic evidence_id.
- Distinguish wrong quote vs quote exists but framing is misleading (misleading).
- Do not claim Panthic authority; frame as research-assisted assessment.
Summary and correction requirements:
- summary MUST be 4–8 sentences (about 120–220 words). Do not write a one-liner.
- Quote Gurbani only when a retrieved verse is about the SAME subject as the claim — for whatever the claim is about (diet, caste, formless God, gender, Rehat, history, a quoted Ang, or a novel topic).
- If a verse only shares a filler word (completely, totally, Lord, saved, fulfilled, comforted) or uses a word in a different sense, ignore it completely — do not mention its Ang or quote it.
- Prefer curated Rehat/history notes over off-topic Gurbani. It is better to cite no verse than the wrong verse.
- When an on-topic BaniDB/GurbaniNow verse is present, weave it in: name the Ang, quote a short Gurmukhi snippet, then the English translation, and explain how that verse supports or challenges the claim.
- Use only Gurmukhi, translations, and Ang numbers that appear in the retrieved evidence. Never invent verses.
- correction should also be 2–4 sentences when the verdict is false or misleading, and may quote the same on-topic retrieved Gurbani.
"""


async def chat_json(
    system: str,
    user: str,
    *,
    temperature: float = 0.1,
    max_tokens: int = 1600,
) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.llm_enabled:
        return None

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            temperature=temperature,
            max_tokens=max_tokens,
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


async def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Embed strings for semantic verse ranking. None if LLM/embeddings are unavailable."""
    settings = get_settings()
    if not settings.llm_enabled:
        return None
    cleaned = [(t or "").strip()[:2000] or " " for t in texts]
    if not cleaned:
        return None
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
        resp = await client.embeddings.create(model=settings.openai_embed_model, input=cleaned)
        ordered = sorted(resp.data, key=lambda row: row.index)
        return [list(row.embedding) for row in ordered]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Embedding call failed: %s", exc)
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
