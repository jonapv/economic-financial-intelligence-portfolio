"""Minimal Google Gemini integration for the synthesis step.

One provider, one call shape, one place to audit. Deliberately not a
multi-provider abstraction. The rest of the project never imports this module —
the schema, prompt, presentation layer, draft validator and renderer all work on
plain dictionaries — so the entire deterministic pipeline and the whole test
suite run without any provider library present.

Transport: the standard library
-------------------------------
This calls the Gemini REST interface directly with ``urllib`` rather than through
``google-genai``. The request is a single POST with a JSON body and two headers,
so an SDK would add nothing material for authentication (one header), structured
output (one JSON field) or response parsing (one root-level field). Against that,
the standard library keeps the project free of third-party dependencies entirely
and lets this module reuse the credential-safety pattern already proven in
``src/fred_client.py``: an injectable ``fetch``, scrubbed error messages, and no
URL ever written to disk.

Credentials come from the environment only:

    GEMINI_API_KEY   the provider API key
    LLM_MODEL        the model identifier, so a model change needs no code change

The key travels in the ``x-goog-api-key`` **header**, never in the query string.
That matters here specifically: the retired prototype put its keys in URL query
parameters, which is exactly how this project's first key leaked. A header keeps
the credential out of URLs, out of any stored request description, and out of
anything a traceback might print.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

from .errors import CollectionError

#: Verified against the current official REST documentation.
API_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
PROVIDER_NAME = "Google Gemini API"

#: Used when LLM_MODEL is not set. A constrained descriptive synthesis task, not
#: autonomous reasoning, so a Flash-class model is the right tier.
DEFAULT_MODEL = "gemini-3.8-flash"

#: Moving aliases are refused: a brief must be reproducible from its recorded
#: model identifier, and an alias silently changes what produced it.
_FORBIDDEN_MODEL_FRAGMENTS = ("latest", "preview", "exp")

#: Conservative generation settings for grounded synthesis. Both field names are
#: verified against the current REST documentation; nothing here is invented.
THINKING_LEVEL = "low"
TEMPERATURE = 0.0

#: JSON Schema keywords the provider documents as supported. The canonical
#: schema in ``brief_schema.py`` remains the source of truth and is left
#: untouched; anything outside this set is stripped for the provider's copy only,
#: and what was stripped is recorded in the call metadata rather than hidden.
_SUPPORTED_SCHEMA_KEYWORDS = frozenset({
    "type", "properties", "required", "additionalProperties",
    "enum", "format", "minimum", "maximum",
    "items", "prefixItems", "minItems", "maxItems",
    "title", "description", "anyOf", "$ref", "nullable",
})

REQUEST_TIMEOUT = 120
REDACTION = "<redacted>"

#: The only Interaction status this project will read output from. Every other
#: documented status is an explicit rejection rather than something to work
#: around: "in_progress" or "queued" would mean polling, which a single-turn
#: structured call should never need.
TERMINAL_OK_STATUS = "completed"

#: Documented status values, each with why it is refused. Taken from the official
#: Interaction resource schema, not inferred.
_STATUS_EXPLANATION = {
    "failed": "the provider reports the interaction failed",
    "incomplete": ("the interaction is incomplete — output may be truncated, and a "
                   "partial brief is never accepted"),
    "cancelled": "the interaction was cancelled",
    "budget_exceeded": "the interaction exceeded its configured budget",
    "in_progress": ("the interaction is still running; this project makes a single "
                    "synchronous call and does not poll"),
    "queued": ("the interaction is queued; this project makes a single synchronous "
               "call and does not poll"),
    "requires_action": ("the interaction is waiting on a tool result, which this "
                        "project never requests — no tools are offered"),
}

#: Step type carrying model output, per the documented schema.
MODEL_OUTPUT_STEP = "model_output"
TEXT_BLOCK = "text"


class SynthesisError(CollectionError):
    """The synthesis request failed, or returned something unusable."""


class MissingLLMCredentialError(SynthesisError):
    """``GEMINI_API_KEY`` was absent from the process environment."""


class InvalidModelConfigurationError(SynthesisError):
    """``LLM_MODEL`` names something this project will not send."""


def read_credentials(env: Optional[Dict[str, str]] = None) -> Tuple[str, str]:
    """Return ``(api_key, model)`` from the environment, or fail clearly."""
    source = os.environ if env is None else env

    key = (source.get("GEMINI_API_KEY") or "").strip()
    if not key:
        raise MissingLLMCredentialError(
            "GEMINI_API_KEY is not set in the environment. Export it before "
            "running synthesis, for example:\n"
            "    export GEMINI_API_KEY=\"$(sed -n 's/^GEMINI_API_KEY=//p' "
            "../../.env | tr -d '[:space:]')\"\n"
            "    export LLM_MODEL=\"gemini-3.8-flash\"\n"
            "Get a key at https://aistudio.google.com/apikey . The key is never "
            "read from source code and never written to disk."
        )

    model = (source.get("LLM_MODEL") or "").strip() or DEFAULT_MODEL
    lowered = model.lower()
    for fragment in _FORBIDDEN_MODEL_FRAGMENTS:
        if fragment in lowered:
            raise InvalidModelConfigurationError(
                f"LLM_MODEL is {model!r}, which contains {fragment!r}. Moving "
                f"aliases are refused: a brief records the model that produced "
                f"it, and an alias would silently change that between runs. Pin "
                f"an explicit version, for example {DEFAULT_MODEL!r}."
            )
    if "/" in model or " " in model:
        raise InvalidModelConfigurationError(
            f"LLM_MODEL is {model!r}, which is not a bare model identifier. "
            f"Supply just the model name, for example {DEFAULT_MODEL!r}."
        )
    return key, model


def _scrub(text: str, secret: Optional[str]) -> str:
    return text.replace(secret, REDACTION) if secret else text


def provider_schema(schema: Any) -> Tuple[Any, set]:
    """Adapt the canonical schema to the provider's supported keyword set.

    Returns ``(adapted_schema, dropped_keywords)``. The canonical schema is not
    modified. Dropped keywords are reported so the difference between what this
    project requires and what the provider enforces is visible rather than
    assumed — the deterministic validator remains the real gate either way.
    """
    dropped: set = set()

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            out = {}
            for key, value in node.items():
                if key in ("properties",):
                    out[key] = {k: walk(v) for k, v in value.items()}
                elif key in _SUPPORTED_SCHEMA_KEYWORDS:
                    out[key] = walk(value) if isinstance(value, (dict, list)) else value
                else:
                    dropped.add(key)
            return out
        if isinstance(node, list):
            return [walk(item) for item in node]
        return node

    return walk(schema), dropped


def _default_fetch(url: str, body: bytes, headers: Dict[str, str]) -> bytes:
    """Perform the HTTPS POST. Replaced by a stub in tests."""
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        return response.read()


def _model_name(raw: Any) -> Optional[str]:
    """Return the model as a string, whatever shape the field takes.

    The schema types this field as a ModelOption, and the documented example
    shows a bare string. Both are accepted; nothing is inferred beyond that.
    """
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        for key in ("model", "name", "id"):
            value = raw.get(key)
            if isinstance(value, str):
                return value
    return None


def extract_output_text(interaction: Dict[str, Any]) -> str:
    """Pull the model's text out of a raw Interaction resource.

    Walks the documented REST shape:

        status == "completed"
          -> steps[] where type == "model_output"
            -> content[] where type == "text"
              -> text

    There is deliberately **no** reliance on a root-level ``output_text``. That
    field is an SDK convenience property, not part of the REST resource, so
    reading it here would have worked in a stubbed test and failed on the first
    live call.

    This project makes one single-turn, tool-free, schema-constrained request, so
    anything more complicated than one model_output step carrying a contiguous run
    of text blocks is treated as ambiguous and **rejected**. Concatenation happens
    only across consecutive text blocks, which is the documented semantic; a run
    broken by a non-text block is not silently stitched together.
    """
    status = interaction.get("status")
    if status != TERMINAL_OK_STATUS:
        reason = _STATUS_EXPLANATION.get(
            status, f"unrecognised status {status!r}")
        raise SynthesisError(
            f"{PROVIDER_NAME} interaction status is {status!r}, not "
            f"{TERMINAL_OK_STATUS!r}: {reason}. No output is read."
        )

    steps = interaction.get("steps")
    if not isinstance(steps, list):
        raise SynthesisError(
            f"{PROVIDER_NAME} response has no 'steps' list "
            f"(found {type(steps).__name__}); the Interaction resource is malformed"
        )

    output_steps = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise SynthesisError(
                f"{PROVIDER_NAME} response step {index} is "
                f"{type(step).__name__}, expected an object"
            )
        if step.get("type") == MODEL_OUTPUT_STEP:
            output_steps.append((index, step))

    if not output_steps:
        seen = sorted({s.get("type") for s in steps if isinstance(s, dict)})
        raise SynthesisError(
            f"{PROVIDER_NAME} response contains no {MODEL_OUTPUT_STEP!r} step; "
            f"step types present: {seen or 'none'}"
        )
    if len(output_steps) > 1:
        raise SynthesisError(
            f"{PROVIDER_NAME} response contains {len(output_steps)} "
            f"{MODEL_OUTPUT_STEP!r} steps. This project issues one single-turn "
            f"request and will not guess which output is the brief; the response "
            f"is rejected rather than interpreted."
        )

    _, step = output_steps[0]
    content = step.get("content")
    if not isinstance(content, list) or not content:
        raise SynthesisError(
            f"{PROVIDER_NAME} {MODEL_OUTPUT_STEP} step has no 'content' list "
            f"(found {type(content).__name__})"
        )

    kinds = []
    for position, block in enumerate(content):
        if not isinstance(block, dict):
            raise SynthesisError(
                f"{PROVIDER_NAME} content block {position} is "
                f"{type(block).__name__}, expected an object"
            )
        kinds.append(block.get("type"))

    text_positions = [i for i, kind in enumerate(kinds) if kind == TEXT_BLOCK]
    if not text_positions:
        raise SynthesisError(
            f"{PROVIDER_NAME} {MODEL_OUTPUT_STEP} step carries no {TEXT_BLOCK!r} "
            f"content block; block types present: {sorted(set(kinds))}"
        )

    # Concatenate only a contiguous run. A gap means a non-text block sits
    # between two text blocks, which is interleaved output, not one message.
    first, last = text_positions[0], text_positions[-1]
    if text_positions != list(range(first, last + 1)):
        interleaved = [kinds[i] for i in range(first, last + 1)
                       if kinds[i] != TEXT_BLOCK]
        raise SynthesisError(
            f"{PROVIDER_NAME} {MODEL_OUTPUT_STEP} step interleaves "
            f"{TEXT_BLOCK!r} blocks with {sorted(set(interleaved))}. Consecutive "
            f"text blocks may be joined; interleaved output is ambiguous and is "
            f"rejected rather than guessed."
        )

    parts = []
    for i in text_positions:
        value = content[i].get("text")
        if not isinstance(value, str):
            raise SynthesisError(
                f"{PROVIDER_NAME} {TEXT_BLOCK} block at position {i} has a "
                f"'text' field of type "
                f"{type(content[i].get('text')).__name__}, expected a string"
            )
        parts.append(value)

    joined = "".join(parts)
    if not joined.strip():
        raise SynthesisError(
            f"{PROVIDER_NAME} {MODEL_OUTPUT_STEP} step carried only empty text"
        )
    return joined


def safe_interaction_metadata(interaction: Dict[str, Any]) -> Dict[str, Any]:
    """Provider metadata worth keeping, with nothing sensitive in it.

    Carries the interaction identity, status, model and token counts. Never
    carries a credential, a request header, or any URL.
    """
    usage = interaction.get("usage")
    usage_out = None
    if isinstance(usage, dict):
        usage_out = {
            key: usage[key] for key in
            ("total_input_tokens", "total_output_tokens", "total_tokens",
             "total_thinking_tokens", "total_cached_tokens")
            if isinstance(usage.get(key), int)
        } or None

    steps = interaction.get("steps")
    return {
        "interaction_id": interaction.get("id"),
        "interaction_object": interaction.get("object"),
        "status": interaction.get("status"),
        "model_reported": _model_name(interaction.get("model")),
        "created": interaction.get("created"),
        "usage": usage_out,
        "step_count": len(steps) if isinstance(steps, list) else None,
    }


def request_brief(
    system_prompt: str,
    user_message: str,
    output_schema: Dict[str, Any],
    *,
    env: Optional[Dict[str, str]] = None,
    fetch=None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Ask the model for a brief. Returns ``(draft_dict, call_metadata)``.

    The response is constrained to JSON matching ``output_schema`` by the
    provider, but that is never treated as sufficient: the caller still runs the
    deterministic validator over whatever comes back. Schema enforcement
    guarantees shape, not truth.

    ``call_metadata`` records what produced the draft and contains no credential.
    """
    api_key, model = read_credentials(env)
    send = fetch or _default_fetch

    adapted_schema, dropped = provider_schema(output_schema)

    payload = {
        "model": model,
        "input": user_message,
        "system_instruction": system_prompt,
        "response_format": {
            "type": "text",
            "mime_type": "application/json",
            "schema": adapted_schema,
        },
        "generation_config": {
            "thinking_level": THINKING_LEVEL,
            "temperature": TEMPERATURE,
        },
    }
    headers = {
        "x-goog-api-key": api_key,   # header, never a query parameter
        "Content-Type": "application/json",
    }

    try:
        raw = send(API_ENDPOINT, json.dumps(payload).encode("utf-8"), headers)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
            parsed = json.loads(body)
            message = (parsed.get("error") or {}).get("message")
            detail = f" — {message}" if message else f" — {body.strip()[:200]}"
        except Exception:
            pass
        raise SynthesisError(
            _scrub(f"{PROVIDER_NAME} returned HTTP {exc.code} ({exc.reason})"
                   f"{detail}", api_key)
        ) from None
    except urllib.error.URLError as exc:
        raise SynthesisError(
            _scrub(f"could not reach {PROVIDER_NAME}: {exc.reason}", api_key)
        ) from None
    except Exception as exc:
        raise SynthesisError(
            _scrub(f"synthesis request failed: {type(exc).__name__}: {exc}", api_key)
        ) from None

    try:
        response = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise SynthesisError(
            _scrub(f"{PROVIDER_NAME} returned a body that is not JSON: {exc}", api_key)
        ) from None
    if not isinstance(response, dict):
        raise SynthesisError(
            f"{PROVIDER_NAME} returned {type(response).__name__}, expected an object"
        )
    if "error" in response:
        message = (response.get("error") or {}).get("message", "unspecified")
        raise SynthesisError(
            _scrub(f"{PROVIDER_NAME} rejected the request: {message}", api_key)
        )

    # Parsed from the documented Interaction resource, not from a root-level
    # output_text, which is an SDK convenience property and absent over REST.
    text = extract_output_text(response)

    try:
        draft = json.loads(text)
    except ValueError as exc:
        raise SynthesisError(
            f"the model output was not valid JSON despite a schema-constrained "
            f"request: {exc}"
        ) from None

    metadata = {
        "provider": PROVIDER_NAME,
        "endpoint": API_ENDPOINT,
        "model_requested": model,
        "auth": "x-goog-api-key header; no credential in any URL",
        "structured_output": "response_format mime_type=application/json with schema",
        "response_parsing": (
            "steps[type=model_output].content[type=text].text from the raw "
            "Interaction resource; no dependency on SDK output_text"
        ),
        "schema_keywords_dropped_for_provider": sorted(dropped),
        "thinking_level": THINKING_LEVEL,
        "temperature": TEMPERATURE,
        "transport": "python standard library urllib; no third-party SDK",
        **safe_interaction_metadata(response),
    }
    return draft, metadata
