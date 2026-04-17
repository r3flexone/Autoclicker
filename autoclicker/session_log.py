"""
Session-Log: Schreibt alle Aktionen in eine CSV-Datei.
Eine Datei pro Sequenz-Start. Bei deaktiviertem Log No-Op.
"""

import csv
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import AutoClickerState

logger = logging.getLogger("autoclicker")

_FIELDS = ["timestamp", "elapsed_sec", "event", "detail", "x", "y", "extra"]


class SessionLog:
    """Thread-sicheres CSV-Log für eine einzelne Sequenz-Session."""

    def __init__(self, path: Path, start_time: float):
        self._path = path
        self._start_time = start_time
        self._lock = threading.Lock()
        self._file = None
        self._writer = None

    def open(self) -> bool:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(self._path, "w", newline="", encoding="utf-8")
            self._writer = csv.DictWriter(self._file, fieldnames=_FIELDS)
            self._writer.writeheader()
            self._file.flush()
            return True
        except (IOError, OSError) as e:
            logger.error(f"Session-Log konnte nicht geöffnet werden: {e}")
            self._file = None
            self._writer = None
            return False

    def log(self, event: str, detail: str = "", x: Optional[int] = None,
            y: Optional[int] = None, extra: str = "") -> None:
        if self._writer is None:
            return
        import time as _time
        now = _time.time()
        row = {
            "timestamp": datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "elapsed_sec": f"{now - self._start_time:.2f}",
            "event": event,
            "detail": detail,
            "x": "" if x is None else x,
            "y": "" if y is None else y,
            "extra": extra,
        }
        with self._lock:
            try:
                self._writer.writerow(row)
                self._file.flush()
            except (IOError, OSError, ValueError) as e:
                logger.error(f"Session-Log-Fehler: {e}")

    def close(self) -> None:
        with self._lock:
            if self._file is not None:
                try:
                    self._file.close()
                except (IOError, OSError):
                    pass
                self._file = None
                self._writer = None

    @property
    def path(self) -> Path:
        return self._path


def start_session_log(state: 'AutoClickerState') -> Optional[SessionLog]:
    """Erzeugt (wenn aktiviert) ein neues Session-Log. Gibt None zurück wenn deaktiviert."""
    if not state.config.session_log_enabled:
        return None
    try:
        log_dir = Path(state.config.session_log_dir)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        seq_name = state.active_sequence or "session"
        from .utils import sanitize_filename
        safe_name = sanitize_filename(seq_name)
        log_path = log_dir / f"{timestamp}_{safe_name}.csv"
        log = SessionLog(log_path, state.start_time or 0)
        if log.open():
            return log
    except (IOError, OSError, ValueError) as e:
        logger.error(f"Session-Log-Start fehlgeschlagen: {e}")
    return None


def log_event(state: 'AutoClickerState', event: str, detail: str = "",
              x: Optional[int] = None, y: Optional[int] = None, extra: str = "") -> None:
    """Schreibt ein Event, wenn ein aktives Log vorhanden ist."""
    log = getattr(state, "session_log", None)
    if log is not None:
        log.log(event, detail, x, y, extra)
