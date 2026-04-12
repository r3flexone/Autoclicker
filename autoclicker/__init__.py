"""
Autoclicker-Paket für Windows mit Sequenz-Unterstützung und Farberkennung.
"""

from .config import AppConfig, CONFIG, load_config, save_config, DEFAULT_CONFIG
from .models import (
    ClickPoint, ElseConfig, WaitCondition, SequenceStep, LoopPhase, Sequence,
    ItemProfile, ItemSlot, ItemScanConfig, AutoClickerState
)

__all__ = [
    'AppConfig', 'CONFIG', 'load_config', 'save_config', 'DEFAULT_CONFIG',
    'ClickPoint', 'ElseConfig', 'WaitCondition', 'SequenceStep', 'LoopPhase', 'Sequence',
    'ItemProfile', 'ItemSlot', 'ItemScanConfig', 'AutoClickerState',
]
