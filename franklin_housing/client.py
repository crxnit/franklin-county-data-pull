"""ArcGIS REST feature-layer client.

Stdlib-only (urllib). Handles pagination via resultOffset, retries with
exponential backoff on transient HTTP/network errors, and logs progress.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator

from . import config

log = logging.getLogger(__name__)

USER_AGENT = "franklin-housing-pull/1.0 (+personal comp analysis)"


class ArcGISError(RuntimeError):
    pass


class ArcGISClient:
    def __init__(
        self,
        endpoint: str = config.ENDPOINT,
        page_size: int = config.PAGE_SIZE,
        timeout: float = 60.0,
        max_retries: int = 5,
        backoff_base: float = 1.5,
    ):
        self.endpoint = endpoint
        self.page_size = page_size
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base

    # -- low-level ----------------------------------------------------------

    def _get(self, params: dict) -> dict:
        """Single GET with retry/backoff. Raises ArcGISError on give-up or
        on an ArcGIS-level error payload (HTTP 200 with an `error` object)."""
        url = self.endpoint + "?" + urllib.parse.urlencode(params)
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                if isinstance(payload, dict) and "error" in payload:
                    # ArcGIS reports query errors in-band with HTTP 200.
                    raise ArcGISError(f"ArcGIS error: {payload['error']}")
                return payload
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_exc = exc
                if attempt == self.max_retries:
                    break
                wait = self.backoff_base ** attempt
                log.warning("request failed (attempt %d/%d): %s — retrying in %.1fs",
                            attempt, self.max_retries, exc, wait)
                time.sleep(wait)
        raise ArcGISError(f"giving up after {self.max_retries} attempts: {last_exc}")

    # -- public -------------------------------------------------------------

    def count(self, where: str) -> int:
        payload = self._get({"where": where, "returnCountOnly": "true", "f": "json"})
        return int(payload.get("count", 0))

    def query_all(self, where: str, out_fields: list[str] | None = None) -> Iterator[dict]:
        """Yield attribute dicts for every row matching `where`, paginating
        until the server stops returning full pages.

        Pagination is driven by row counts (a short page means done) AND by the
        server's `exceededTransferLimit` flag — whichever signals completion.
        """
        fields = ",".join(out_fields or config.OUT_FIELDS)
        offset = 0
        total = 0
        while True:
            params = {
                "where": where,
                "outFields": fields,
                "orderByFields": "SALEDATE DESC",
                "returnGeometry": "false",
                "resultOffset": offset,
                "resultRecordCount": self.page_size,
                "f": "json",
            }
            payload = self._get(params)
            features = payload.get("features", [])
            n = len(features)
            total += n
            log.info("page offset=%d -> %d rows (total %d)", offset, n, total)
            for feat in features:
                yield feat.get("attributes", {})
            exceeded = payload.get("exceededTransferLimit", False)
            if n < self.page_size and not exceeded:
                break
            if n == 0:
                break
            offset += n
