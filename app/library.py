"""
Named part library — save favorite designs by name for remix / reload.
Persisted next to sessions so it survives restarts.
"""

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

LIBRARY_FILE = "outputs/library.json"
_lock = threading.Lock()


class PartLibrary:
    def __init__(self, path: str = LIBRARY_FILE):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.items = self._load()

    def _load(self) -> list:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def _persist(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.items, f, indent=2)

    def list(self) -> list:
        return sorted(self.items, key=lambda x: x.get("updated_at", ""), reverse=True)

    def get(self, part_id: str) -> Optional[dict]:
        for item in self.items:
            if item["id"] == part_id:
                return item
        return None

    def save(self, name: str, params: dict, session_id: str = None,
             tags: list = None, notes: str = "") -> dict:
        with _lock:
            now = datetime.now(timezone.utc).isoformat()
            # Upsert by name (case-insensitive)
            existing = next(
                (i for i in self.items if i["name"].lower() == name.strip().lower()),
                None,
            )
            if existing:
                existing["params"] = params
                existing["session_id"] = session_id
                existing["tags"] = tags or existing.get("tags", [])
                existing["notes"] = notes if notes is not None else existing.get("notes", "")
                existing["updated_at"] = now
                self._persist()
                return existing

            item = {
                "id": str(uuid.uuid4())[:8],
                "name": name.strip(),
                "params": params,
                "session_id": session_id,
                "tags": tags or [],
                "notes": notes or "",
                "created_at": now,
                "updated_at": now,
            }
            self.items.append(item)
            self._persist()
            return item

    def delete(self, part_id: str) -> bool:
        with _lock:
            before = len(self.items)
            self.items = [i for i in self.items if i["id"] != part_id]
            if len(self.items) < before:
                self._persist()
                return True
            return False
