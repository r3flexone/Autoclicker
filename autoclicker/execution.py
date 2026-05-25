"""
Backward-Compat-Shim für Imports wie `from autoclicker.execution import ...`.

Die eigentliche Implementierung lebt im autoclicker.runtime-Subpaket:
    - actions.py: Klick/Key-Wrapper, Humanize, Fokus-Check, Status, Else-Aktion
    - item_scan.py: Item-Scan-Runtime + _check_profile_match
    - boss_detection.py: Boss-Scan, OCR/LLM-Erkennung, Async-Pfad
    - steps.py: Step-Dispatcher
    - worker.py: sequence_worker + print_status

Diese Datei bleibt bestehen damit main.py und handlers.py ihre bisherigen
Imports unverändert lassen können.
"""

from .runtime import sequence_worker, print_status

__all__ = ['sequence_worker', 'print_status']
