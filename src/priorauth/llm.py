"""Every model call in the project goes through here.

Two reasons this file exists:
  1. Caching. Extractions get re-run hundreds of times during eval tuning; without
     a cache the project blows its budget on day one.
  2. Structured output discipline. Callers pass a Pydantic model and get an instance
     back, via Anthropic tool use. Nothing in this codebase parses JSON out of prose.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Type, TypeVar

import anthropic
import pydantic
from pydantic import BaseModel

from . import config, db

T = TypeVar("T", bound=BaseModel)

# Per-million-token prices, used for the cost table.
# Verify against current console pricing before publishing numbers.
PRICING_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-opus-5": (15.00, 75.00),
}

_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.require_api_key())
    return _client


def _cache_key(model: str, system: str, prompt: str, schema_name: str) -> str:
    blob = json.dumps([model, system, prompt, schema_name], sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


class LLMResponse(BaseModel):
    parsed: dict
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    cached: bool = False

    def cost_usd(self, model: str) -> float:
        inp, out = PRICING_USD_PER_MTOK.get(model, (0.0, 0.0))
        return (self.input_tokens * inp + self.output_tokens * out) / 1_000_000


def structured(
    schema: Type[T],
    prompt: str,
    *,
    system: str = "",
    model: str | None = None,
    max_tokens: int = 16000,
    temperature: float | None = None,
) -> tuple[T, LLMResponse]:
    """Call Claude and get back a validated instance of `schema`.

    Uses tool use with the Pydantic JSON schema, which forces well-formed output
    rather than hoping the model emits parseable JSON.
    """
    model = model or config.MODEL
    key = _cache_key(model, system, prompt, schema.__name__)

    if config.CACHE_ENABLED:
        with db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM llm_cache WHERE cache_key = ?", (key,)
            ).fetchone()
        if row:
            payload = json.loads(row["response"])
            return schema.model_validate(payload), LLMResponse(
                parsed=payload,
                input_tokens=row["input_tokens"] or 0,
                output_tokens=row["output_tokens"] or 0,
                cached=True,
            )

    tool = {
        "name": "emit_result",
        "description": f"Emit the result as a well-formed {schema.__name__}.",
        "input_schema": schema.model_json_schema(),
    }

    started = time.perf_counter()
    msg = client().messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature if temperature is not None else anthropic.NOT_GIVEN,
        system=system or anthropic.NOT_GIVEN,
        tools=[tool],
        tool_choice={"type": "tool", "name": "emit_result"},
        messages=[{"role": "user", "content": prompt}],
    )
    latency = time.perf_counter() - started

    if msg.stop_reason == "max_tokens":
        raise RuntimeError(
            f"Response truncated at max_tokens={max_tokens} ({msg.usage.output_tokens} "
            f"output tokens) before the tool call completed. Raise max_tokens rather than "
            f"treat this as a bad extraction — the failure is a token budget, not the model."
        )

    block = next(b for b in msg.content if b.type == "tool_use")
    payload = block.input
    try:
        parsed = schema.model_validate(payload)
    except pydantic.ValidationError:
        # Rare tool-use quirk: the model occasionally wraps the whole answer in a
        # single spurious key (seen as both "parameters" and "parameter name")
        # instead of emitting the schema's fields at the top level. Unwrap once if
        # that shape matches, then let a genuine validation error propagate normally
        # — this targets the wrapper, not tolerance for actually-wrong content.
        if isinstance(payload, dict) and len(payload) == 1:
            (inner,) = payload.values()
            payload = inner
        parsed = schema.model_validate(payload)

    if config.CACHE_ENABLED:
        with db.connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO llm_cache
                   (cache_key, model, response, input_tokens, output_tokens)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    key,
                    model,
                    json.dumps(payload),
                    msg.usage.input_tokens,
                    msg.usage.output_tokens,
                ),
            )

    return parsed, LLMResponse(
        parsed=payload,
        input_tokens=msg.usage.input_tokens,
        output_tokens=msg.usage.output_tokens,
        latency_s=latency,
    )
