"""Pipeline state manager with persistence and TTL-based cleanup.

v0.5.1: Replaces raw dict with thread-safe, TTL-expiring, file-persisted state.
"""

import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_TTL = timedelta(hours=24)
_STATE_DIR = Path.home() / ".judicial-lint" / "sessions"


class PipelineStateManager:
    def __init__(self, ttl: timedelta = _DEFAULT_TTL, persist: bool = True):
        self._state: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._ttl = ttl
        self._persist = persist
        if persist:
            _STATE_DIR.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()

    def save(self, session_id: str, state: dict) -> None:
        with self._lock:
            state["updated_at"] = datetime.now().isoformat()
            self._state[session_id] = state
            if self._persist:
                self._save_to_disk(session_id, state)

    def get(self, session_id: str) -> dict | None:
        with self._lock:
            entry = self._state.get(session_id)
            if entry is None:
                return None
            if self._is_expired(entry):
                del self._state[session_id]
                self._remove_from_disk(session_id)
                return None
            return entry

    def update(self, session_id: str, updates: dict) -> dict | None:
        with self._lock:
            entry = self._state.get(session_id)
            if entry is None:
                return None
            if self._is_expired(entry):
                del self._state[session_id]
                self._remove_from_disk(session_id)
                return None
            entry.update(updates)
            entry["updated_at"] = datetime.now().isoformat()
            if self._persist:
                self._save_to_disk(session_id, entry)
            return entry

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._state.pop(session_id, None)
            self._remove_from_disk(session_id)

    def cleanup_expired(self) -> int:
        removed = 0
        with self._lock:
            expired = [sid for sid, entry in self._state.items() if self._is_expired(entry)]
            for sid in expired:
                del self._state[sid]
                self._remove_from_disk(sid)
                removed += 1
        if removed:
            logger.info("cleanup_expired: removed %d expired sessions", removed)
        return removed

    def _is_expired(self, entry: dict) -> bool:
        updated = entry.get("updated_at")
        if not updated:
            return False
        try:
            updated_dt = datetime.fromisoformat(updated)
            return datetime.now() - updated_dt > self._ttl
        except (ValueError, TypeError):
            return False

    def _save_to_disk(self, session_id: str, state: dict) -> None:
        try:
            path = _STATE_DIR / f"{session_id}.json"
            path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("save_to_disk failed for %s: %s", session_id, e)

    def _remove_from_disk(self, session_id: str) -> None:
        try:
            path = _STATE_DIR / f"{session_id}.json"
            if path.exists():
                path.unlink()
        except Exception as e:
            logger.warning("remove_from_disk failed for %s: %s", session_id, e)

    def _load_from_disk(self) -> int:
        loaded = 0
        try:
            for path in _STATE_DIR.glob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    sid = path.stem
                    if not self._is_expired(data):
                        self._state[sid] = data
                        loaded += 1
                    else:
                        path.unlink()
                except Exception:
                    path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning("load_from_disk failed: %s", e)
        if loaded:
            logger.info("load_from_disk: restored %d sessions", loaded)
        return loaded
