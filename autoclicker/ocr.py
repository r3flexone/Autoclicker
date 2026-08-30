"""
OCR-Texterkennung für den Autoclicker.
Liest Boss-Namen direkt als Text vom Screenshot — schneller und deterministischer als LLM.

Unterstützte Backends (Priorität):
  1. EasyOCR   — pip install easyocr
  2. Tesseract — pip install pytesseract  (+ Tesseract-Installation)
"""

import logging
import time
import warnings
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

logger = logging.getLogger("autoclicker")

# ── Backend-Erkennung ──────────────────────────────────────────────────────────

BACKEND_EASYOCR = "easyocr"
BACKEND_TESSERACT = "tesseract"

_easyocr_available = False
_tesseract_available = False

try:
    import easyocr as _easyocr_mod
    _easyocr_available = True
except ImportError:
    _easyocr_mod = None

try:
    import pytesseract as _pytesseract_mod
    _tesseract_available = True
except ImportError:
    _pytesseract_mod = None


def available_backends() -> list[str]:
    """Gibt verfügbare OCR-Backends zurück."""
    backends = []
    if _easyocr_available:
        backends.append(BACKEND_EASYOCR)
    if _tesseract_available:
        backends.append(BACKEND_TESSERACT)
    return backends


def is_available() -> bool:
    """Prüft ob mindestens ein OCR-Backend verfügbar ist."""
    return _easyocr_available or _tesseract_available


# ── EasyOCR Reader-Cache ───────────────────────────────────────────────────────

_easyocr_readers: dict[tuple[str, ...], object] = {}


def _cuda_available() -> bool:
    """Prüft ob ein CUDA-fähiges PyTorch installiert ist.

    Wichtig: Ohne diesen Check setzt EasyOCR bei gpu=True trotzdem
    pin_memory=True im DataLoader und PyTorch loggt eine UserWarning,
    wenn kein Accelerator gefunden wird (CPU-only torch).
    """
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _get_easyocr_reader(languages: list[str] = None):
    """EasyOCR-Reader je Sprachkombination cachen (Initialisierung ~2-5s)."""
    langs = tuple(languages or ["en"])
    reader = _easyocr_readers.get(langs)
    if reader is None:
        use_gpu = _cuda_available()
        if not use_gpu:
            logger.info(
                "EasyOCR läuft auf CPU (kein CUDA-fähiges PyTorch gefunden). "
                "Für GPU: torch mit CUDA-Support installieren, z.B. "
                "pip install torch --index-url https://download.pytorch.org/whl/cu121"
            )
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*pin_memory.*accelerator.*")
            reader = _easyocr_mod.Reader(list(langs), gpu=use_gpu, verbose=False)
        _easyocr_readers[langs] = reader
    return reader


# ── OCR-Funktionen ─────────────────────────────────────────────────────────────

def read_text(
    img: 'Image.Image',
    backend: str = None,
    languages: list[str] = None,
    min_confidence: float = 0.3,
) -> list[tuple[str, float]]:
    """Liest Text aus einem PIL-Image.

    `backend` ist "easyocr" oder "tesseract" (None = bestes verfügbares),
    `languages` Sprach-Codes (Standard ["en"]), `min_confidence` die
    Mindest-Konfidenz (0-1) für Ergebnisse.
    """
    if backend is None:
        backend = _select_backend()
    if backend is None:
        return []

    if backend == BACKEND_EASYOCR:
        return _read_easyocr(img, languages, min_confidence)
    elif backend == BACKEND_TESSERACT:
        return _read_tesseract(img, languages, min_confidence)
    else:
        logger.error(f"Unbekanntes OCR-Backend: {backend}")
        return []


def _select_backend() -> Optional[str]:
    """Wählt das beste verfügbare Backend."""
    if _easyocr_available:
        return BACKEND_EASYOCR
    if _tesseract_available:
        return BACKEND_TESSERACT
    return None


def _read_easyocr(img: 'Image.Image', languages: list[str] = None,
                   min_confidence: float = 0.3) -> list[tuple[str, float]]:
    """Liest Text mit EasyOCR."""
    import numpy as np
    reader = _get_easyocr_reader(languages)
    img_array = np.array(img)
    results = reader.readtext(img_array)

    texts = []
    for (_bbox, text, conf) in results:
        if conf >= min_confidence and text.strip():
            texts.append((text.strip(), conf))

    texts.sort(key=lambda x: x[1], reverse=True)
    return texts


def _read_tesseract(img: 'Image.Image', languages: list[str] = None,
                     min_confidence: float = 0.3) -> list[tuple[str, float]]:
    """Liest Text mit Tesseract."""
    lang_str = "+".join(languages) if languages else "eng"
    data = _pytesseract_mod.image_to_data(img, lang=lang_str, output_type=_pytesseract_mod.Output.DICT)

    texts = []
    for i, text in enumerate(data["text"]):
        text = text.strip()
        conf = int(data["conf"][i])
        if conf >= 0 and text:
            conf_normalized = conf / 100.0
            if conf_normalized >= min_confidence:
                texts.append((text, conf_normalized))

    texts.sort(key=lambda x: x[1], reverse=True)
    return texts


# ── Boss-Name-Matching ─────────────────────────────────────────────────────────

def detect_boss_name(
    img: 'Image.Image',
    boss_names: list[str],
    backend: str = None,
    languages: list[str] = None,
    min_confidence: float = 0.3,
    new_boss_min_confidence: float = 0.8,
) -> tuple[bool, Optional[str], str, float, Optional[str]]:
    """Versucht einen Boss-Namen per OCR im Bild zu erkennen.

    `img` ist ein Screenshot der Boss-Region, `boss_names` die bekannten Namen.
    `new_boss_min_confidence` ist die Schwelle, ab der unbekannter Text als neuer
    Boss gemeldet wird.

    Gibt `(success, matched_name, raw_text, duration_ms, new_name_candidate)` zurück.
    """
    start = time.time()

    if not is_available():
        return False, None, "Kein OCR-Backend verfügbar", 0.0, None

    texts = read_text(img, backend=backend, languages=languages,
                      min_confidence=min_confidence)
    duration_ms = (time.time() - start) * 1000

    if not texts:
        return False, None, "", duration_ms, None

    full_text = " ".join(t for t, _c in texts)

    matched = _match_text_to_boss(full_text, boss_names)
    if matched:
        return True, matched, full_text, duration_ms, None

    for text, _conf in texts:
        matched = _match_text_to_boss(text, boss_names)
        if matched:
            return True, matched, full_text, duration_ms, None

    # Kein bekannter Boss — prüfe ob ein Text mit hoher Konfidenz als neuer Name gilt
    new_candidate = None
    if texts:
        best_text, best_conf = texts[0]  # bereits nach Konfidenz absteigend sortiert
        if best_conf >= new_boss_min_confidence and len(best_text.strip()) >= 3:
            new_candidate = best_text.strip()

    return False, None, full_text, duration_ms, new_candidate


def _match_text_to_boss(text: str, boss_names: list[str]) -> Optional[str]:
    """Matcht einen erkannten Text gegen Boss-Namen.

    Muss dieselbe Antwort geben wie `llm_vision.match_boss_name()`: beide
    bekommen dieselbe Boss-Liste und ersetzen einander je nach Fallback, und
    jedes BossProfile hat seine eigene Aktion.

    - Enthält der Text mehrere Namen, gewinnt der längste (sonst fand
      ["Ork", "Orkhäuptling"] in "Der Orkhäuptling erscheint" den *Ork*).
    - Steckt der Text in mehreren Namen, gewinnt der kürzeste — er behauptet am
      wenigsten über das Gelesene hinaus.

    Die Regel steht absichtlich zweimal da: `ocr.py` und `llm_vision.py` sind
    abhängigkeitsfreie Blätter. Ein Test füttert beide und vergleicht.
    """
    text_lower = text.lower().strip()
    if not text_lower:
        return None

    # Exakt
    for name in boss_names:
        if name.lower() == text_lower:
            return name

    # Boss-Name im Text enthalten -> spezifischsten (laengsten) Treffer waehlen
    enthalten = [name for name in boss_names if name.lower() in text_lower]
    if enthalten:
        return max(enthalten, key=len)

    # Text im Boss-Namen enthalten (min 3 Zeichen, sonst matcht ein Kuerzel alles)
    if len(text_lower) >= 3:
        teilweise = [name for name in boss_names if text_lower in name.lower()]
        if teilweise:
            return min(teilweise, key=len)

    return None


# ── Status/Test ────────────────────────────────────────────────────────────────

def get_status() -> str:
    """Gibt Info über verfügbare OCR-Backends zurück."""
    backends = available_backends()
    if not backends:
        return "Kein OCR-Backend installiert (pip install easyocr oder pip install pytesseract)"
    return f"Verfügbar: {', '.join(backends)}"
