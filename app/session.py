import json
import os
import threading

SESSIONS_FILE = "outputs/sessions.json"
_lock = threading.Lock()


class SessionStore:
    """
    Stores, per session_id, a version history of params (list) plus a cursor
    (current index into that history). This gives /undo and /redo for free.
    Persisted to a JSON file on disk so sessions survive a server restart.
    """

    def __init__(self, path: str = SESSIONS_FILE):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.store = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _persist(self):
        with open(self.path, "w") as f:
            json.dump(self.store, f)

    def save(self, session_id: str, params: dict):
        """Push a new version onto this session's history (used by /generate and /edit)."""
        with _lock:
            entry = self.store.setdefault(session_id, {"history": [], "cursor": -1})
            # if we'd previously undone some steps, a new edit discards the redo branch
            entry["history"] = entry["history"][: entry["cursor"] + 1]
            entry["history"].append(params)
            entry["cursor"] = len(entry["history"]) - 1
            self._persist()

    def get(self, session_id: str) -> dict:
        entry = self.store.get(session_id)
        if not entry or entry["cursor"] < 0:
            return {}
        return entry["history"][entry["cursor"]]

    def history(self, session_id: str) -> list:
        entry = self.store.get(session_id)
        return entry["history"] if entry else []

    def undo(self, session_id: str):
        with _lock:
            entry = self.store.get(session_id)
            if not entry or entry["cursor"] <= 0:
                return None
            entry["cursor"] -= 1
            self._persist()
            return entry["history"][entry["cursor"]]

    def redo(self, session_id: str):
        with _lock:
            entry = self.store.get(session_id)
            if not entry or entry["cursor"] >= len(entry["history"]) - 1:
                return None
            entry["cursor"] += 1
            self._persist()
            return entry["history"][entry["cursor"]]

    def can_undo(self, session_id: str) -> bool:
        entry = self.store.get(session_id)
        return bool(entry and entry["cursor"] > 0)

    def can_redo(self, session_id: str) -> bool:
        entry = self.store.get(session_id)
        return bool(entry and entry["cursor"] < len(entry["history"]) - 1)

    def meta(self, session_id: str) -> dict:
        """Cursor + length for history UI."""
        entry = self.store.get(session_id)
        if not entry:
            return {"version": 0, "total": 0, "can_undo": False, "can_redo": False}
        total = len(entry["history"])
        cursor = entry["cursor"]
        return {
            "version": cursor + 1,
            "total": total,
            "can_undo": cursor > 0,
            "can_redo": cursor < total - 1,
        }

    def list_sessions(self) -> list:
        out = []
        for sid, entry in self.store.items():
            if not entry.get("history"):
                continue
            cursor = entry.get("cursor", 0)
            params = entry["history"][cursor] if cursor < len(entry["history"]) else entry["history"][-1]
            out.append({
                "session_id": sid,
                "shape": params.get("shape", "unknown"),
                "material": params.get("material"),
                "versions": len(entry["history"]),
                "clarified": params.get("_clarified_as", ""),
            })
        return out

    def restore_version(self, session_id: str, index: int):
        """Jump cursor to a specific history index (0-based)."""
        with _lock:
            entry = self.store.get(session_id)
            if not entry or index < 0 or index >= len(entry["history"]):
                return None
            entry["cursor"] = index
            self._persist()
            return entry["history"][index]
