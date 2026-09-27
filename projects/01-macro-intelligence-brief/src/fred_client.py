"""HTTP boundary for the FRED API.

The only module in this project that opens a network connection. It fetches
payloads and hands them on unmodified; it does not parse observation values,
does not compute anything, and does not decide whether data is acceptable.

Credential handling
-------------------
The API key is read from the ``FRED_API_KEY`` environment variable and is never
written to source, logs, exceptions, snapshots or any file on disk. Every URL is
built at the moment of the request and discarded; the key is scrubbed from error
messages by :func:`_scrub`. Requests are described on disk by endpoint name and
by parameters with the key removed (see :meth:`FredClient.describe_request`).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Mapping, Optional

from .errors import MissingCredentialError, SourcePayloadError, SourceRequestError

BASE_URL = "https://api.stlouisfed.org/fred"
SERIES_ENDPOINT = "series"
OBSERVATIONS_ENDPOINT = "series/observations"
SOURCE_NAME = "Federal Reserve Bank of St. Louis (FRED)"
USER_AGENT = "macro-intelligence-brief/0.2 (portfolio research project)"
DEFAULT_TIMEOUT = 30

#: Substituted wherever the key might otherwise surface in text.
REDACTION = "<redacted>"


def read_api_key(env: Optional[Mapping[str, str]] = None) -> str:
    """Return the FRED API key from the environment, or fail clearly.

    The error message deliberately names the variable and how to supply it, and
    contains no value.
    """
    source = os.environ if env is None else env
    key = (source.get("FRED_API_KEY") or "").strip()
    if not key:
        raise MissingCredentialError(
            "FRED_API_KEY is not set in the environment. Export it before "
            "running the collector, for example:\n"
            "    export FRED_API_KEY=\"$(awk -F= '/^FRED_API_KEY=/{print $2}' "
            ".env)\"\n"
            "Request a key at https://fredaccount.stlouisfed.org/apikeys . The "
            "key is never read from source code and never written to disk."
        )
    return key


def _scrub(text: str, secret: Optional[str]) -> str:
    """Remove the API key from a string, however it was embedded."""
    if not secret:
        return text
    return text.replace(secret, REDACTION).replace(
        urllib.parse.quote(secret), REDACTION
    )


def _default_fetch(url: str, timeout: int = DEFAULT_TIMEOUT) -> bytes:
    """Perform the HTTPS GET. Replaced by a stub in tests."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


class FredClient:
    """Minimal read-only FRED client.

    ``fetch`` is injectable so that tests never touch the network: it takes a
    URL and returns raw bytes.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        fetch: Optional[Callable[[str], bytes]] = None,
        base_url: str = BASE_URL,
    ) -> None:
        self._api_key = read_api_key() if api_key is None else api_key
        if not self._api_key:
            raise MissingCredentialError("an empty API key was supplied")
        self._fetch = fetch or _default_fetch
        self._base_url = base_url.rstrip("/")

    # -- request description, safe to persist ------------------------------
    @staticmethod
    def describe_request(endpoint: str, params: Mapping[str, str]) -> Dict[str, Any]:
        """Describe a request for the manifest, with no credential in it.

        Returns the endpoint name and the parameters excluding ``api_key``.
        Deliberately returns no URL, so that nothing key-bearing can be written
        to disk by accident.
        """
        return {
            "endpoint": endpoint,
            "params": {k: v for k, v in sorted(params.items()) if k != "api_key"},
        }

    # -- internals ---------------------------------------------------------
    def _get(self, endpoint: str, params: Mapping[str, str]) -> Any:
        query = dict(params)
        query["api_key"] = self._api_key
        query.setdefault("file_type", "json")
        url = f"{self._base_url}/{endpoint}?{urllib.parse.urlencode(query)}"

        try:
            payload = self._fetch(url)
        except urllib.error.HTTPError as exc:
            # FRED puts a diagnostic in the body of a 4xx, which is far more
            # useful than the status line. Read it, then scrub it: never
            # interpolate the URL, which carries the key.
            detail = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
                parsed = json.loads(body)
                if isinstance(parsed, dict) and parsed.get("error_message"):
                    detail = f" — {parsed['error_message']}"
                elif body.strip():
                    detail = f" — {body.strip()[:200]}"
            except Exception:
                pass
            raise SourceRequestError(
                _scrub(
                    f"FRED returned HTTP {exc.code} for endpoint {endpoint!r} "
                    f"(series={params.get('series_id', '?')}): {exc.reason}{detail}",
                    self._api_key,
                )
            ) from None
        except urllib.error.URLError as exc:
            raise SourceRequestError(
                _scrub(
                    f"could not reach FRED at endpoint {endpoint!r}: {exc.reason}",
                    self._api_key,
                )
            ) from None
        except Exception as exc:  # timeouts, socket errors, stub failures
            raise SourceRequestError(
                _scrub(
                    f"request to FRED endpoint {endpoint!r} failed: "
                    f"{type(exc).__name__}: {exc}",
                    self._api_key,
                )
            ) from None

        try:
            decoded = json.loads(payload)
        except (ValueError, TypeError) as exc:
            raise SourcePayloadError(
                _scrub(f"FRED endpoint {endpoint!r} returned invalid JSON: {exc}",
                       self._api_key)
            ) from None

        if not isinstance(decoded, dict):
            raise SourcePayloadError(
                f"FRED endpoint {endpoint!r} returned {type(decoded).__name__}, "
                f"expected a JSON object"
            )
        if "error_message" in decoded:
            raise SourceRequestError(
                _scrub(
                    f"FRED rejected the request to {endpoint!r}: "
                    f"{decoded.get('error_message')}",
                    self._api_key,
                )
            )
        return decoded

    # -- public API --------------------------------------------------------
    def series_metadata(self, series_id: str) -> Dict[str, Any]:
        """Fetch ``fred/series`` for one series and return its metadata block."""
        payload = self._get(SERIES_ENDPOINT, {"series_id": series_id})
        entries = payload.get("seriess")
        if not isinstance(entries, list) or not entries:
            raise SourcePayloadError(
                f"metadata response for {series_id!r} contains no 'seriess' entry"
            )
        metadata = entries[0]
        if not isinstance(metadata, dict):
            raise SourcePayloadError(
                f"metadata entry for {series_id!r} is not an object"
            )
        return metadata

    def observations(
        self,
        series_id: str,
        *,
        limit: int,
        units: str = "lin",
        sort_order: str = "desc",
    ) -> Dict[str, Any]:
        """Fetch ``fred/series/observations``.

        ``units`` defaults to ``lin`` — the raw, untransformed source values.
        The primary calculation always uses ``lin``; any other value is a
        secondary cross-check and must be labelled as such by the caller.

        ``sort_order='desc'`` asks for the most recent observations first, which
        is how a ``limit`` yields the latest window. Chronological ordering is
        restored in the normalisation layer, not here.
        """
        payload = self._get(
            OBSERVATIONS_ENDPOINT,
            {
                "series_id": series_id,
                "limit": str(limit),
                "sort_order": sort_order,
                "units": units,
            },
        )
        if not isinstance(payload.get("observations"), list):
            raise SourcePayloadError(
                f"observations response for {series_id!r} has no "
                f"'observations' list"
            )
        return payload

    def scrub(self, text: str) -> str:
        """Remove this client's key from ``text``. Used when reporting errors."""
        return _scrub(text, self._api_key)
