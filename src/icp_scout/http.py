"""HTTP with a disk cache, a rate limit and retries. Shared by both open-data sources.

Every response is stored as `<cache_dir>/<source>/<key>.json`, so a run is
resumable and a re-run makes no calls. `offline` reads the cache only and
fails on a miss; `refresh` ignores what is cached (and overwrites it).
"""

import hashlib
import json
import time
from pathlib import Path

import httpx

MAX_ATTEMPTS = 8


class CacheMiss(RuntimeError):
    """Offline mode asked for a response that is not cached."""


class CachedClient:
    def __init__(
        self,
        source: str,
        cache_dir: str | Path,
        *,
        offline: bool = False,
        refresh: bool = False,
        rate_per_s: float = 5.0,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 60.0,
    ):
        self.source = source
        self.dir = Path(cache_dir) / source
        self.offline = offline
        self.refresh = refresh
        self.min_interval = 1.0 / rate_per_s if rate_per_s else 0.0
        self.calls = 0  # HTTP requests actually made, retries included
        self._last = 0.0
        self._http = None if offline else httpx.Client(transport=transport, timeout=timeout)

    def get_json(self, url: str, params: dict | None = None, key: str | None = None) -> dict:
        """GET `url` and return its JSON body, from the cache when possible."""
        params = params or {}
        path = self.dir / f"{key or request_key(url, params)}.json"
        if path.exists() and not self.refresh:
            return json.loads(path.read_text(encoding="utf-8"))
        if self.offline:
            raise CacheMiss(f"not cached: {self.source} {url} {params} ({path})")
        body = self._fetch(url, params)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
        return body

    def _fetch(self, url: str, params: dict) -> dict:
        for attempt in range(MAX_ATTEMPTS):
            self._throttle()
            self.calls += 1
            try:
                response = self._http.get(url, params=params)
            except httpx.TransportError:
                # Connection resets and timeouts: transient, try again.
                time.sleep(min(2**attempt, 30))
                continue
            if response.status_code == 429 or response.status_code >= 500:
                wait = response.headers.get("retry-after", "")
                time.sleep(float(wait) if wait.isdigit() else min(2**attempt, 30))
                continue
            response.raise_for_status()
            return response.json()
        raise RuntimeError(f"{self.source}: gave up after {MAX_ATTEMPTS} attempts: {url} {params}")

    def _throttle(self) -> None:
        wait = self._last + self.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()


def request_key(url: str, params: dict) -> str:
    raw = url + "?" + json.dumps(params, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(raw.encode()).hexdigest()
