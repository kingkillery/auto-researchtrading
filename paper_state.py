from __future__ import annotations

import dataclasses
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any


STATE_SCHEMA_VERSION = 1


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {field.name: _jsonable(getattr(value, field.name)) for field in dataclasses.fields(value)}

    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}

    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]

    if isinstance(value, set):
        return sorted(_jsonable(item) for item in value)

    if isinstance(value, Path):
        return str(value)

    if hasattr(value, "item") and callable(value.item):
        try:
            return value.item()
        except Exception:
            pass

    if hasattr(value, "tolist") and callable(value.tolist):
        try:
            return _jsonable(value.tolist())
        except Exception:
            pass

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    return repr(value)


class JsonStateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()

    def load(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None

        with self.path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serialized = _jsonable(payload)
        last_error: OSError | None = None
        for attempt in range(5):
            fd, tmp_name = tempfile.mkstemp(
                dir=str(self.path.parent),
                prefix=f"{self.path.name}.",
                suffix=".tmp",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(serialized, handle, indent=2, sort_keys=True)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp_name, self.path)
                return
            except PermissionError as exc:
                last_error = exc
                try:
                    os.unlink(tmp_name)
                except FileNotFoundError:
                    pass
                time.sleep(0.05 * (attempt + 1))
            except Exception:
                try:
                    os.unlink(tmp_name)
                except FileNotFoundError:
                    pass
                raise
        if last_error is not None:
            raise last_error


def default_state_path(strategy_spec: str, root: str | Path | None = None) -> Path:
    base = Path(root).expanduser() if root is not None else Path.home() / ".cache" / "autotrader" / "paper"
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", strategy_spec.strip()) or "strategy"
    return base / f"{safe_name}.json"
