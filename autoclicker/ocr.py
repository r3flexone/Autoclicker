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

_easyocr_reader = None


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
    """Cached EasyOCR Reader (Erstinitialisierung dauert ~2-5s)."""
    global _easyocr_reader
    if _easyocr_reader is None:
        langs = languages or ["en"]
        use_gpu = _cuda_available()
        if not use_gpu:
            logger.info(
                "EasyOCR läuft auf CPU (kein CUDA-fähiges PyTorch gefunden). "
                "Für GPU: torch mit CUDA-Support installieren, z.B. "
                "pip install torch --index-url https://download.pytorch.org/whl/cu121"
            )
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*pin_memory.*accelerator.*")
            _easyocr_reader = _easyocr_mod.Reader(langs, gpu=use_gpu, verbose=False)
    return _easyocr_reader


# ── OCR-Funktionen ─────────────────────────────────────────────────────────────

def read_text(
    img: 'Image.Image',
    backend: str = None,
    languages: list[str] = None,
    min_confidence: float = 0.3,
) -> list[tuple[str, float]]:
    """Liest Text aus einem PIL-Image.

    Args:
        img: PIL Image zum Analysieren
        backend: "easyocr" oder "tesseract" (None = bestes verfügbares)
        languages: Sprach-Codes (Standard: ["en"])
        min_confidence: Mindest-Konfidenz (0-1) für Ergebnisse

    Returns:
        Liste von (text, confidence) Tupeln, sortiert nach Konfidenz absteigend.
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
) -> tuple[bool, Optional[str], str, float]:
    """Versucht einen Boss-Namen per OCR im Bild zu erkennen.

    Args:
        img: PIL Image (Screenshot der Boss-Region)
        boss_names: Liste bekannter Boss-Namen
        backend: OCR-Backend (None = Auto)
        languages: Sprach-Codes
        min_confidence: Mindest-Konfidenz für OCR-Ergebnis

    Returns:
        (success, matched_name, raw_text, duration_ms)
        - success: True wenn ein Boss erkannt wurde
        - matched_name: Erkannter Boss-Name (oder None)
        - raw_text: Gesamter erkannter Text
        - duration_ms: Dauer in Millisekunden
    """
    start = time.time()

    if not is_available():
        return False, None, "Kein OCR-Backend verfügbar", 0.0

    texts = read_text(img, backend=backend, languages=languages,
                      min_confidence=min_confidence)
    duration_ms = (time.time() - start) * 1000

    if not texts:
        return False, None, "", duration_ms

    full_text = " ".join(t for t, _c in texts)

    matched = _match_text_to_boss(full_text, boss_names)
    if matched:
        return True, matched, full_text, duration_ms

    for text, _conf in texts:
        matched = _match_text_to_boss(text, boss_names)
        if matched:
            return True, matched, full_text, duration_ms

    return False, None, full_text, duration_ms


def _match_text_to_boss(text: str, boss_names: list[str]) -> Optional[str]:
    """Matcht einen erkannten Text gegen Boss-Namen."""
    text_lower = text.lower().strip()
    if not text_lower:
        return None

    # Exakt
    for name in boss_names:
        if name.lower() == text_lower:
            return name

    # Boss-Name im Text enthalten
    for name in boss_names:
        if name.lower() in text_lower:
            return name

    # Text im Boss-Namen enthalten (min 3 Zeichen damit nicht false-positives)
    for name in boss_names:
        if len(text_lower) >= 3 and text_lower in name.lower():
            return name

    return None


# ── Status/Test ────────────────────────────────────────────────────────────────

def get_status() -> str:
    """Gibt Info über verfügbare OCR-Backends zurück."""
    backends = available_backends()
    if not backends:
        return "Kein OCR-Backend installiert (pip install easyocr oder pip install pytesseract)"
    return f"Verfügbar: {', '.join(backends)}"
