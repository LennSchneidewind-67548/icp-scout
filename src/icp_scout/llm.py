"""WP2. The one door to a model: API calls, recordings, cost ledger (ADR 0004).

Every answer is recorded as `<recordings_dir>/<purpose>/<key>.json`, keyed by a
hash of the request, so the demo and CI replay offline with no key. Modes:
`replay` reads recordings only and raises `RecordingMiss` on a miss (it never
builds an API client), `record` calls the API on a miss and stores the answer,
`refresh` always calls and overwrites. Every call, live or replayed, appends one
line to the cost ledger.

Recordings of real companies are case content: they belong in `private/llm/`,
never under the committed `fixtures/llm/` (ADR 0003).
"""

import hashlib
import json
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

MODES = ("replay", "record", "refresh")

# USD per million tokens: (base input, 5-minute cache write, cache read, output).
# Source: https://platform.claude.com/docs/en/about-claude/pricing, read 2026-09-29.
PRICES = {
    "claude-fable-5-1": (10.00, 12.50, 0.25, 50.00),
    "claude-opus-5-5": (4.00, 5.00, 0.20, 20.00),
    "claude-opus-5": (5.00, 6.25, 0.50, 25.00),
    "claude-opus-4-8": (5.00, 6.25, 0.50, 25.00),
    "claude-sonnet-5-5": (2.00, 2.50, 0.20, 10.00),
    "claude-sonnet-5": (2.00, 2.50, 0.20, 10.00),
    "claude-haiku-4-5": (1.00, 1.25, 0.10, 5.00),
}
# Web search is billed per search on top of tokens; web fetch has no extra charge.
WEB_SEARCH_USD_PER_1K = 10.00

# Server-side refusal fallback: a declined request is re-run on the model
# Anthropic recommends for that refusal category, inside the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# The request fields that make an answer what it is. Transport settings
# (streaming, betas, fallbacks) are not part of the key.
KEY_FIELDS = ("model", "system", "messages", "tools", "tool_choice", "output_config",
              "thinking", "max_tokens")  # fmt: skip


class RecordingMiss(RuntimeError):
    """Replay mode asked for an answer that was never recorded."""


def request_key(params: dict) -> str:
    """sha256 of the canonical JSON of the request, so any prompt change is a new key."""
    body = {k: params[k] for k in KEY_FIELDS if k in params}
    raw = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def cost_usd(model: str, usage: dict) -> float:
    if model not in PRICES:
        raise KeyError(f"no price for model {model!r}: add it to llm.PRICES")
    base, write, read, out = PRICES[model]
    tokens = (
        (usage.get("input_tokens") or 0) * base
        + (usage.get("cache_creation_input_tokens") or 0) * write
        + (usage.get("cache_read_input_tokens") or 0) * read
        + (usage.get("output_tokens") or 0) * out
    ) / 1e6
    return tokens + web_searches(usage) * WEB_SEARCH_USD_PER_1K / 1000


def web_searches(usage: dict) -> int:
    return ((usage.get("server_tool_use") or {}).get("web_search_requests")) or 0


def web_fetches(usage: dict) -> int:
    return ((usage.get("server_tool_use") or {}).get("web_fetch_requests")) or 0


class LLM:
    def __init__(
        self,
        recordings_dir: str | Path,
        mode: str = "replay",
        ledger_path: str | Path | None = None,
        *,
        client=None,
        fallbacks: bool = True,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, not {mode!r}")
        self.dir = Path(recordings_dir)
        self.mode = mode
        self.ledger_path = Path(ledger_path) if ledger_path else None
        self.fallbacks = fallbacks
        self.clock = clock
        self.spent_usd = 0.0  # live calls made by this instance
        self._client = client
        self._lock = threading.Lock()

    @property
    def client(self):
        """The API client, built on first live call. Replay mode never gets here."""
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(max_retries=4)
        return self._client

    def create(self, purpose: str, lead_id: str, **params) -> dict:
        """One Messages API call. Returns the response as a dict (`message.to_dict()`)."""
        key = request_key(params)
        path = self.dir / purpose / f"{key}.json"
        replayed = path.exists() and self.mode != "refresh"
        if replayed:
            rec = json.loads(path.read_text(encoding="utf-8"))
        elif self.mode == "replay":
            raise RecordingMiss(f"no recording for {purpose} / {lead_id}: {path}")
        else:
            response = self._call(params)
            usage = response.get("usage") or {}
            rec = {
                "request": {k: params[k] for k in KEY_FIELDS if k in params},
                "response": response,
                "usage": usage,
                "cost_usd": round(cost_usd(response.get("model") or params["model"], usage), 6),
                "recorded_at": self.clock().isoformat(timespec="seconds"),
            }
            write_json(path, rec)
        self._log(purpose, lead_id, key, rec, replayed)
        return rec["response"]

    def _call(self, params: dict) -> dict:
        """Stream the request and return the final message as a dict."""
        extra = {"betas": [FALLBACK_BETA], "fallbacks": "default"} if self.fallbacks else {}
        with self.client.beta.messages.stream(**params, **extra) as stream:
            # mode="json": search results carry datetimes, which must serialize.
            return stream.get_final_message().to_dict(mode="json")

    def _log(self, purpose: str, lead_id: str, key: str, rec: dict, replayed: bool) -> None:
        usage = rec["usage"]
        line = {
            "at": self.clock().isoformat(timespec="seconds"),
            "lead": lead_id,
            "purpose": purpose,
            "key": key,
            "model": rec["response"].get("model") or rec["request"].get("model"),
            "input_tokens": usage.get("input_tokens") or 0,
            "cache_write_tokens": usage.get("cache_creation_input_tokens") or 0,
            "cache_read_tokens": usage.get("cache_read_input_tokens") or 0,
            "output_tokens": usage.get("output_tokens") or 0,
            "web_searches": web_searches(usage),
            "web_fetches": web_fetches(usage),
            "usd": rec["cost_usd"],
            "replayed": replayed,
        }
        with self._lock:
            if not replayed:
                self.spent_usd += rec["cost_usd"]
            if self.ledger_path:
                self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
                with self.ledger_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(line, ensure_ascii=False) + "\n")


def write_json(path: Path, body) -> None:
    """Write atomically: a crash never leaves half a file (as in http.py)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{threading.get_ident()}.tmp")
    text = json.dumps(body, ensure_ascii=False, indent=1)
    tmp.write_text(text, encoding="utf-8", newline="\n")  # the same bytes on every OS
    tmp.replace(path)


def read_ledger(path: str | Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
