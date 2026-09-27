"""Writing the reproducibility artefacts to disk.

Persists the raw source payloads exactly as received, plus the derived outputs
and the validation report. The raw snapshot is what makes a published figure
traceable: it records what the source actually said at retrieval time, including
any missing-value sentinels, before anything touched it.

Secret safety: :func:`write_json` refuses to write any payload whose serialised
form contains the API key, or the substring ``api_key=``. That check is a
backstop, not the primary defence — no URL is ever passed into this module.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Optional

from .errors import CollectionError

FORBIDDEN_SUBSTRINGS = ("api_key=", "api_key\":")


class SecretLeakError(CollectionError):
    """A payload about to be written contained a credential. Nothing was written."""


def assert_secret_free(text: str, secret: Optional[str] = None) -> None:
    """Raise if ``text`` carries a credential. Never echoes the secret."""
    for needle in FORBIDDEN_SUBSTRINGS:
        if needle in text:
            raise SecretLeakError(
                f"refusing to write: payload contains {needle!r}, which may "
                f"carry a credential"
            )
    if secret and secret in text:
        raise SecretLeakError(
            "refusing to write: payload contains the API key"
        )


def write_json(path: pathlib.Path, payload: Any, *, secret: Optional[str] = None) -> pathlib.Path:
    """Serialise ``payload`` to ``path`` after a secret-safety check."""
    text = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False)
    assert_secret_free(text, secret)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    return path


def scan_tree_for_secret(root: pathlib.Path, secret: Optional[str]) -> list:
    """Return files under ``root`` that contain the secret or ``api_key=``.

    Enumerates files explicitly rather than relying on a recursive grep, which
    can skip dot-files depending on the tool and environment.
    """
    offenders = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(n in text for n in FORBIDDEN_SUBSTRINGS) or (secret and secret in text):
            offenders.append(path)
    return offenders
