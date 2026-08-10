"""
Einstiegspunkt für das Sequenz-Studio (läuft als eigener Subprocess).

Aufruf:
    python -m autoclicker.sequence_studio "<Sequenz-Name>"
    python -m autoclicker.sequence_studio            # leere/neue Sequenz

Wird vom Hotkey-Handler (handle_sequence_studio in handlers.py) per subprocess.Popen
gestartet, damit der Dear-PyGui-Event-Loop nicht mit der Windows-Hotkey-Message-
Pump des Hauptprozesses kollidiert. Liest/schreibt sequences/<name>.json direkt;
nach dem Speichern lädt man im Hauptprozess mit CTRL+ALT+L neu.
"""

import sys
import time
from pathlib import Path

from .config import SEQUENCES_DIR
from .models import Sequence
from .persistence import (
    ensure_sequences_dir, list_available_sequences, load_sequence_file,
)
from .utils import sanitize_filename


def _resolve_sequence(name: str) -> tuple[Sequence, Path]:
    """Lädt die Sequenz mit gegebenem Namen oder legt eine neue an."""
    ensure_sequences_dir()
    if name:
        for seq_name, path in list_available_sequences():
            if seq_name == name:
                seq = load_sequence_file(path)
                if seq:
                    return seq, path
    # Neue Sequenz
    base = name or f"Sequenz_{int(time.time())}"
    seq = Sequence(name=base)
    path = Path(SEQUENCES_DIR) / f"{sanitize_filename(base)}.json"
    return seq, path


def main(argv: list[str]) -> int:
    seq_name = argv[1] if len(argv) > 1 else ""

    try:
        import dearpygui.dearpygui  # noqa: F401
    except ImportError:
        print("Dear PyGui ist nicht installiert. Installieren mit:")
        print("    pip install dearpygui")
        return 1

    seq, path = _resolve_sequence(seq_name)

    # Erst hier importieren — zieht Dear PyGui nur wenn wirklich gebraucht.
    from .editors.sequence_studio.view_dpg import SequenceStudioApp
    app = SequenceStudioApp(seq, path, SEQUENCES_DIR)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
