"""
Groq API Key Pool
==================

Rotates across multiple Groq API keys (one per contributor account) to
work around Groq's free-tier per-account daily rate limit. This is a
deliberate stopgap for staying on the free tier — the team's own
assessment (2026-08-22) is that Groq's paid tier is the more reliable
long-term fix and this pool carries real risk (Groq's terms generally
prohibit using multiple accounts to get around a per-account limit, and
each contributor's own account is what's at stake, not just the key) —
the team chose to proceed with the pool anyway for now.

Keys come from GROQ_API_KEYS (comma-separated) in ProAuth_AI_ML/.env,
e.g.:
    GROQ_API_KEYS=gsk_key_one,gsk_key_two,gsk_key_three,...

Falls back to the single GROQ_AGENT_API_KEY if GROQ_API_KEYS isn't set,
so nothing breaks for a deployment that hasn't added a pool.

Rotation: every Groq call from every agent goes through
get_pooled_client(), a drop-in replacement for `groq.Groq(...)` (same
`.chat.completions.create(**kwargs)` surface). On a real RateLimitError
(429 — the key is fine, just past its quota for today) OR an
AuthenticationError/PermissionDeniedError (401/403 — the key itself is
dead: revoked, deleted, or invalid) it marks the current key
exhausted-for-today and transparently retries with the next unused key.
Both failure modes rotate the same way so a single dead key can't break
its own turn in the rotation; only a 429 will actually self-heal at the
next daily reset though — a dead key fails the same way again every day
until it's actually replaced in GROQ_API_KEYS (see the "REJECTED" vs
"rate-limited" wording in this module's own log lines to tell them
apart). Callers never see either error unless every pooled key is
unavailable, which is exactly the same failure mode they already handle
today.

State (which keys are exhausted today) persists to a local JSON file
next to this module, keyed by INDEX into GROQ_API_KEYS rather than the
raw key string, so no key material ever gets written outside of .env.
A stored date different from today means Groq's daily caps have reset,
so every key goes back to available.

Known limitations (accepted for the current deployment):
- In-process state only — safe for a single uvicorn process (the current
  deployment). If this service is ever run with multiple workers or
  replicas, each process gets its own pool and this file becomes a
  cross-process race; that would need a shared store (DB/Redis) instead.
- Reset timing defaults to UTC midnight (GROQ_KEY_RESET_TZ env var to
  override) — confirm the actual reset time in the Groq console for the
  specific plan tier in use; if it's wrong, keys will just look
  "exhausted" a bit longer than necessary until the next real reset,
  not silently used incorrectly.
- GROQ_API_KEYS order should stay stable across restarts within a day
  (indices identify keys) — editing the list mid-day can make an
  already-exhausted key look fresh again; self-heals at the next daily
  reset either way.
"""
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from groq import AuthenticationError, Groq, PermissionDeniedError, RateLimitError

# A key can stop working two different ways: genuinely rate-limited (429 —
# self-heals at the next daily reset), or dead (401/403 — revoked, deleted,
# or mistyped; these are personal accounts, not something this project
# controls, so this is a real possibility, not a hypothetical). Both must
# rotate to the next key the same way, or a single dead key breaks its own
# turn in the rotation forever instead of being skipped — found while
# reasoning through "does this survive a friend revoking their key without
# a manual fix + redeploy" (2026-08-22), not from a live failure.
_SKIP_KEY_ERRORS = (RateLimitError, AuthenticationError, PermissionDeniedError)

load_dotenv()

_STATE_PATH = Path(__file__).parent / ".groq_key_pool_state.json"
_RESET_TZ = os.environ.get("GROQ_KEY_RESET_TZ", "UTC")


def _today_str():
    if _RESET_TZ == "UTC":
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo(_RESET_TZ)).strftime("%Y-%m-%d")


def _pool_exhausted_error(message):
    # Every existing Groq call site in this codebase already has an except
    # block scoped to RateLimitError (either to retry or to degrade
    # gracefully to a fallback result) — raising a real RateLimitError here
    # for "every pooled key is exhausted" means those existing handlers
    # keep working unchanged, instead of an unhandled RuntimeError bypassing
    # them and crashing the request. The synthetic response/body are never
    # inspected by any caller in this codebase, only the exception type and
    # .message are.
    fake_response = httpx.Response(429, request=httpx.Request("POST", "https://groq_key_pool.local"))
    return RateLimitError(message, response=fake_response, body=None)


def _load_keys():
    raw = os.environ.get("GROQ_API_KEYS", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        single = os.environ.get("GROQ_AGENT_API_KEY")
        if single:
            keys = [single]
    if not keys:
        raise RuntimeError(
            "No Groq API key configured — set GROQ_API_KEYS (comma-separated pool) "
            "or GROQ_AGENT_API_KEY (single key) in ProAuth_AI_ML/.env"
        )
    return keys


class GroqKeyPool:
    def __init__(self):
        self._lock = threading.Lock()
        self._keys = _load_keys()
        self._clients = {}  # key index -> real groq.Groq client, built lazily
        self._state = self._load_state()
        print(f"[groq_key_pool] loaded {len(self._keys)} key(s), "
              f"{len(self._state['exhausted'])} already exhausted for {self._state['date']}")

    # ---------- state persistence ----------
    def _fresh_state(self, today):
        return {"date": today, "exhausted": []}

    def _load_state(self):
        today = _today_str()
        data = None
        if _STATE_PATH.exists():
            try:
                data = json.loads(_STATE_PATH.read_text())
            except (json.JSONDecodeError, OSError):
                data = None
        if not data or data.get("date") != today:
            data = self._fresh_state(today)
        data.setdefault("exhausted", [])
        # Drop indices that fall outside the currently configured pool size
        # (GROQ_API_KEYS got shorter since this file was last written).
        data["exhausted"] = [i for i in data["exhausted"] if 0 <= i < len(self._keys)]
        return data

    def _save_state(self):
        try:
            _STATE_PATH.write_text(json.dumps(self._state))
        except OSError:
            pass  # persistence is a nice-to-have; rotation still works in-memory this run

    # ---------- rotation ----------
    # No round-robin counter — the active key is always the lowest-index key
    # that isn't in `exhausted` yet. Exhausted keys are only ever removed
    # from that set at the next daily reset, never re-added mid-day, so
    # this deterministically walks 0, 1, 2, ... as each one gets rate-
    # limited, with no index arithmetic that can skip or repeat a key.
    def _get_active_client(self):
        with self._lock:
            today = _today_str()
            if self._state.get("date") != today:
                print(f"[groq_key_pool] new day ({today}) — resetting all {len(self._keys)} keys to available")
                self._state = self._fresh_state(today)
                self._save_state()

            available = [i for i in range(len(self._keys)) if i not in self._state["exhausted"]]
            if not available:
                raise _pool_exhausted_error(
                    f"All {len(self._keys)} pooled Groq keys are unavailable for today "
                    f"({today}) — either rate-limited (resets at the next {_RESET_TZ} day "
                    f"boundary) or dead (need a real replacement key, see [groq_key_pool] logs)."
                )
            key_index = available[0]
            if key_index not in self._clients:
                self._clients[key_index] = Groq(api_key=self._keys[key_index])
            return key_index, self._clients[key_index]

    def _mark_exhausted(self, key_index, reason):
        with self._lock:
            if key_index not in self._state["exhausted"]:
                self._state["exhausted"].append(key_index)
                self._save_state()
                remaining = len(self._keys) - len(self._state["exhausted"])
                print(f"[groq_key_pool] key #{key_index} {reason} — rotating "
                      f"({remaining} of {len(self._keys)} keys still available today)")

    def create_with_rotation(self, **kwargs):
        while True:
            # Raises RateLimitError itself once no key remains available —
            # that propagates straight out of this loop (it's outside the
            # try below), so this never spins forever and never needs a
            # separate "have I tried them all" counter.
            key_index, client = self._get_active_client()
            try:
                return client.chat.completions.create(**kwargs)
            except RateLimitError:
                self._mark_exhausted(key_index, "rate-limited (will retry automatically at the next daily reset)")
            except (AuthenticationError, PermissionDeniedError):
                # A dead key, not a rate limit — waiting for the daily reset
                # won't fix this one, it'll just fail the same way again
                # tomorrow. Marked exhausted anyway so THIS run keeps moving
                # to a working key instead of breaking here; the log line is
                # the actual signal that this specific key needs replacing
                # in GROQ_API_KEYS, not just time.
                self._mark_exhausted(key_index, "REJECTED (invalid/revoked key — needs manual replacement, will not self-heal)")


class _PooledCompletions:
    def __init__(self, pool):
        self._pool = pool

    def create(self, **kwargs):
        return self._pool.create_with_rotation(**kwargs)


class _PooledChat:
    def __init__(self, pool):
        self.completions = _PooledCompletions(pool)


class PooledGroqClient:
    """Drop-in replacement for `groq.Groq(...)` — same `.chat.completions.create(**kwargs)`
    surface used everywhere in this codebase, but transparently rotates across
    GROQ_API_KEYS on RateLimitError instead of raising after the first exhausted key."""

    def __init__(self, pool):
        self.chat = _PooledChat(pool)


_pool = None
_pooled_client = None


def get_pooled_client():
    """Shared entry point — every agent's _get_client() calls this instead of
    building its own `groq.Groq(...)` directly, so the whole service rotates
    through the same pool/state rather than each agent tracking it separately."""
    global _pool, _pooled_client
    if _pooled_client is None:
        _pool = GroqKeyPool()
        _pooled_client = PooledGroqClient(_pool)
    return _pooled_client
