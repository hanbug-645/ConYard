"""Redis-backed signal store for inter-agent coordination.

Signal types:
    task        — PM → Engineer: a granular coding task
    task_done   — Engineer → QA: code written, ready for testing
    fix_request — QA → Engineer: test failed, fix needed
    green       — QA → PM: file passed tests, code verified
"""

import json
import logging
import time
import uuid
from typing import Optional

import redis

logger = logging.getLogger("fireant")

SIGNAL_TYPES = ("task", "task_done", "fix_request", "green")


class SignalStore:
    """Thin wrapper around Redis for typed signal coordination."""

    def __init__(self, redis_url: str = "redis://localhost:6379", prefix: str = "fireant:"):
        self.prefix = prefix
        self.r = redis.Redis.from_url(redis_url, decode_responses=True)
        # Verify connection eagerly so we fail fast with a clear message
        try:
            self.r.ping()
        except redis.ConnectionError as e:
            raise ConnectionError(
                f"Cannot connect to Redis at {redis_url}. "
                f"Is the Redis server running? Error: {e}"
            ) from e
        logger.info(f"[signals] Connected to Redis at {redis_url}")

    # ── Key helpers ──────────────────────────────────────────────────

    def _queue_key(self, signal_type: str) -> str:
        return f"{self.prefix}signals:{signal_type}"

    def _claimed_key(self, signal_type: str) -> str:
        return f"{self.prefix}claimed:{signal_type}"

    def _lock_key(self, signal_id: str) -> str:
        return f"{self.prefix}lock:{signal_id}"

    # ── Push ─────────────────────────────────────────────────────────

    def push_signal(
        self,
        signal_type: str,
        payload: dict,
        producer: str = "",
    ) -> str:
        """Add a signal to the queue. Returns the signal ID."""
        assert signal_type in SIGNAL_TYPES, f"Unknown signal type: {signal_type}"
        signal_id = f"sig-{uuid.uuid4().hex[:12]}"
        envelope = {
            "id": signal_id,
            "type": signal_type,
            "producer": producer,
            "timestamp": time.time(),
            **payload,
        }
        self.r.rpush(self._queue_key(signal_type), json.dumps(envelope))
        logger.debug(f"[signals] Pushed {signal_type} {signal_id} from {producer}")
        return signal_id

    # ── Claim (atomic) ───────────────────────────────────────────────

    def claim_signal(self, signal_type: str, agent_id: str) -> Optional[dict]:
        """Atomically pop the oldest signal of the given type.

        Uses LPOP for atomic single-consumer claim. Returns the signal
        envelope dict, or None if the queue is empty.
        """
        raw = self.r.lpop(self._queue_key(signal_type))
        if raw is None:
            return None
        envelope = json.loads(raw)
        # Track claimed signals for observability
        envelope["claimed_by"] = agent_id
        envelope["claimed_at"] = time.time()
        self.r.hset(self._claimed_key(signal_type), envelope["id"], json.dumps(envelope))
        logger.debug(f"[signals] {agent_id} claimed {signal_type} {envelope['id']}")
        return envelope

    # ── Read (non-destructive) ───────────────────────────────────────

    def peek_signals(self, signal_type: str, limit: int = 50) -> list[dict]:
        """Read pending signals without consuming them."""
        raw_list = self.r.lrange(self._queue_key(signal_type), 0, limit - 1)
        return [json.loads(r) for r in raw_list]

    def count_pending(self, signal_type: str) -> int:
        """Return the number of pending (unclaimed) signals."""
        return self.r.llen(self._queue_key(signal_type))

    # ── Green file tracking ──────────────────────────────────────────

    def get_green_files(self) -> list[dict]:
        """Return all green (verified) file signals."""
        return [json.loads(v) for v in self.r.hvals(self._claimed_key("green"))]

    def push_green(self, file_path: str, layer: str, producer: str = "qa") -> str:
        """Mark a file as verified (green) in the fast-lookup set.

        Does NOT push to the signals:green list queue (nobody consumes it).
        Returns a synthetic signal ID for logging consistency.
        """
        signal_id = f"sig-{uuid.uuid4().hex[:12]}"
        self.r.sadd(f"{self.prefix}green_files", file_path)
        logger.debug(f"[signals] Green {signal_id}: {file_path} (from {producer})")
        return signal_id

    def is_green(self, file_path: str) -> bool:
        """Check if a file has been verified (green)."""
        return self.r.sismember(f"{self.prefix}green_files", file_path)

    def all_green_paths(self) -> set[str]:
        """Return set of all verified file paths."""
        return self.r.smembers(f"{self.prefix}green_files")

    # ── Retry tracking ────────────────────────────────────────────────

    def _retry_key(self, file_path: str) -> str:
        return f"{self.prefix}retries:{file_path}"

    def increment_retries(self, file_path: str) -> int:
        """Increment and return the retry count for a file."""
        return self.r.incr(self._retry_key(file_path))

    def get_retries(self, file_path: str) -> int:
        """Get the current retry count for a file."""
        val = self.r.get(self._retry_key(file_path))
        return int(val) if val else 0

    # ── Cleanup ──────────────────────────────────────────────────────

    def flush_project(self) -> None:
        """Remove all signals for this prefix. Used between runs."""
        pattern = f"{self.prefix}*"
        cursor = 0
        while True:
            cursor, keys = self.r.scan(cursor, match=pattern, count=100)
            if keys:
                self.r.delete(*keys)
            if cursor == 0:
                break
        logger.info("[signals] Flushed all project signals")
