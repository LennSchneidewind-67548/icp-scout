"""WP2. The second door to a model: the `claude` CLI on the author's subscription.

`claude -p` runs the whole research loop with its own WebSearch and WebFetch
tools and ends with structured output against a JSON schema. The transcript
(stream-json) is recorded like an API answer, keyed by a hash of the request, and
replays the same way (modes as in llm.py). A ledger line records usd 0, since no
API money is spent, and the CLI's own list-price estimate as `notional_usd`.

Guards, because the project has a hard cap on API spend:
- the API key is removed from the child's environment, and a run whose init
  message reports any key source other than "none" is killed before its first
  model call;
- the stream reports how full the subscription's usage windows are. Once one
  passes its cap in `max_utilization`, or a limit is hit, `UsageLimit` stops the run. The
  lead in flight is not recorded, so the next run resumes it.
"""

import hashlib
import json
import os
import subprocess
import tempfile
import threading
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

from icp_scout.llm import MODES, RecordingMiss, write_json

BACKEND = "claude-code"
TIMEOUT_S = 20 * 60  # per lead
DEFAULT_CAP = 0.9  # utilization cap for a usage window not named in max_utilization
# Credentials that would make the CLI bill an API account instead of the plan.
API_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK",
           "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY")  # fmt: skip


class UsageLimit(RuntimeError):
    """The subscription's usage window is full (or past max_utilization)."""


class CliError(RuntimeError):
    """The CLI ended without a usable result."""


def request_key(request: dict) -> str:
    raw = json.dumps(request, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def argv(request: dict, system_file: Path) -> list[str]:
    tools = ",".join(request["tools"])
    return [
        "claude", "-p",
        "--model", request["model"],
        "--effort", request["effort"],
        "--system-prompt-file", str(system_file),
        "--json-schema", json.dumps(request["schema"], separators=(",", ":")),
        "--tools", tools,
        "--allowedTools", tools,
        # Nothing from the author's setup leaks in: no settings, MCP servers or skills.
        "--setting-sources", "",
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--no-session-persistence",
        "--output-format", "stream-json",
        "--verbose",
    ]  # fmt: skip


def run_cli(cmd: list[str], prompt: str, cwd: Path, timeout: float) -> Iterator[dict]:
    """Run the CLI with the prompt on stdin and yield its stream-json messages."""
    env = {k: v for k, v in os.environ.items() if k not in API_ENV}
    proc = subprocess.Popen(
        cmd, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
    )  # fmt: skip
    timer = threading.Timer(timeout, proc.kill)
    timer.start()
    try:
        proc.stdin.write(prompt)
        proc.stdin.close()
        for line in proc.stdout:
            if line.strip():
                yield json.loads(line)
        proc.wait()
        if proc.returncode:
            raise CliError(f"claude exited {proc.returncode}: {proc.stderr.read()[:500]}")
    finally:
        timer.cancel()
        if proc.poll() is None:
            proc.kill()
            proc.wait()


class ClaudeCode:
    def __init__(
        self,
        recordings_dir: str | Path,
        mode: str = "replay",
        ledger_path: str | Path | None = None,
        *,
        max_utilization: dict[str, float] | None = None,
        runner: Callable[[list[str], str, Path, float], Iterator[dict]] = run_cli,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, not {mode!r}")
        self.dir = Path(recordings_dir)
        self.mode = mode
        self.ledger_path = Path(ledger_path) if ledger_path else None
        self.max_utilization = max_utilization or {}
        self.runner = runner
        self.clock = clock
        self.spent_usd = 0.0  # always 0: the run loop's budget guard never trips
        self.windows: dict[str, float] = {}  # usage window -> utilization, from the stream
        self._lock = threading.Lock()

    def run(self, purpose: str, lead_id: str, **request) -> dict:
        """One research run. `request`: model, effort, system, prompt, schema, tools.
        Returns the recording: request, transcript, result, notional_usd."""
        request = {"backend": BACKEND, **request}
        key = request_key(request)
        path = self.dir / purpose / f"{key}.json"
        replayed = path.exists() and self.mode != "refresh"
        if replayed:
            rec = json.loads(path.read_text(encoding="utf-8"))
        elif self.mode == "replay":
            raise RecordingMiss(f"no recording for {purpose} / {lead_id}: {path}")
        else:
            self.check_headroom()
            transcript = self._call(request)
            result = transcript[-1]
            rec = {
                "request": request,
                "transcript": transcript,
                "result": result,
                "notional_usd": round(result.get("total_cost_usd") or 0.0, 6),
                "recorded_at": self.clock().isoformat(timespec="seconds"),
            }
            write_json(path, rec)
        self._log(purpose, lead_id, key, rec, replayed)
        return rec

    def check_headroom(self) -> None:
        with self._lock:
            full = {w: u for w, u in self.windows.items() if u >= self.cap(w)}
        if full:
            used = ", ".join(f"{w} window {u:.0%} used (cap {self.cap(w):.0%})"
                             for w, u in full.items())  # fmt: skip
            raise UsageLimit(used)

    def cap(self, window: str) -> float:
        return self.max_utilization.get(window, DEFAULT_CAP)

    def _call(self, request: dict) -> list[dict]:
        # An empty working directory: no CLAUDE.md or project memory is picked up.
        with tempfile.TemporaryDirectory(prefix="icp-scout-cc-") as tmp:
            cwd = Path(tmp)
            system_file = cwd / "system.md"
            system_file.write_text(request["system"], encoding="utf-8")
            transcript = []
            stream = self.runner(argv(request, system_file), request["prompt"], cwd, TIMEOUT_S)
            try:
                for msg in stream:
                    self._watch(msg)
                    transcript.append(msg)
            finally:
                close = getattr(stream, "close", None)
                if close:
                    close()  # kills the process if a guard stopped the run
        result = transcript[-1] if transcript else {}
        if result.get("type") != "result":
            raise CliError("the CLI stream ended without a result message")
        if result.get("is_error") or result.get("subtype") != "success":
            if result.get("api_error_status") == 429:
                raise UsageLimit(f"rate limited: {str(result.get('result'))[:300]}")
            raise CliError(f"{result.get('subtype')}: {str(result.get('result'))[:500]}")
        return transcript

    def _watch(self, msg: dict) -> None:
        """Stop at once on API-key billing or a full usage window."""
        if msg.get("type") == "system" and msg.get("subtype") == "init":
            source = msg.get("apiKeySource")
            if source != "none":
                raise CliError(f"the CLI would bill an API key ({source}), not the plan: stopped")
        if msg.get("type") == "rate_limit_event":
            info = msg.get("rate_limit_info") or {}
            with self._lock:
                for window, w in (info.get("unifiedWindows") or {}).items():
                    self.windows[window] = w.get("utilization") or 0.0
            status = info.get("status")
            if status and not status.startswith("allowed"):
                raise UsageLimit(f"usage limit: {info.get('rateLimitType')} {info.get('status')}")

    def _log(self, purpose: str, lead_id: str, key: str, rec: dict, replayed: bool) -> None:
        usage = rec["result"].get("usage") or {}
        tools = tool_calls(rec["transcript"])
        line = {
            "at": self.clock().isoformat(timespec="seconds"),
            "lead": lead_id,
            "purpose": purpose,
            "key": key,
            "backend": BACKEND,
            "model": rec["request"]["model"],
            "input_tokens": usage.get("input_tokens") or 0,
            "cache_write_tokens": usage.get("cache_creation_input_tokens") or 0,
            "cache_read_tokens": usage.get("cache_read_input_tokens") or 0,
            "output_tokens": usage.get("output_tokens") or 0,
            "web_searches": sum(1 for t in tools if t["name"] == "WebSearch"),
            "web_fetches": sum(1 for t in tools if t["name"] == "WebFetch"),
            "usd": 0.0,
            "notional_usd": rec["notional_usd"],
            "windows": dict(self.windows),
            "replayed": replayed,
        }
        with self._lock:
            if self.ledger_path:
                self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
                with self.ledger_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(line, ensure_ascii=False) + "\n")


def tool_calls(transcript: list[dict]) -> list[dict]:
    """Every tool_use block the model sent, in order."""
    return [
        block
        for msg in transcript
        if msg.get("type") == "assistant"
        for block in (msg.get("message") or {}).get("content") or []
        if isinstance(block, dict) and block.get("type") == "tool_use"
    ]


def tool_results(transcript: list[dict]) -> list[str]:
    """The text of every tool result the model got back."""
    out = []
    for msg in transcript:
        if msg.get("type") != "user":
            continue
        content = (msg.get("message") or {}).get("content")
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                out.append(json.dumps(block.get("content"), ensure_ascii=False))
    return out
