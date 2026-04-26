# -*- coding: utf-8 -*-
"""Lightweight JSON-based internationalization helpers."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings


DEFAULT_LANGUAGE = "zh-CN"
SUPPORTED_LANGUAGES = {
    "zh-CN": "简体中文",
    "en-US": "English",
}


def _settings() -> QSettings:
    return QSettings("PhotoTriage", "GUI")


def current_language() -> str:
    lang = _settings().value("ui/language", DEFAULT_LANGUAGE) or DEFAULT_LANGUAGE
    return lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def set_language(lang: str) -> None:
    if lang not in SUPPORTED_LANGUAGES:
        lang = DEFAULT_LANGUAGE
    _settings().setValue("ui/language", lang)
    load_catalog.cache_clear()


@lru_cache(maxsize=8)
def load_catalog(lang: str) -> dict[str, str]:
    root = Path(__file__).resolve().parent.parent
    path = root / "i18n" / f"{lang}.json"
    fallback = root / "i18n" / f"{DEFAULT_LANGUAGE}.json"
    if not path.is_file():
        path = fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def tr(key: str, **kwargs: Any) -> str:
    catalog = load_catalog(current_language())
    text = catalog.get(key)
    if text is None and current_language() != DEFAULT_LANGUAGE:
        text = load_catalog(DEFAULT_LANGUAGE).get(key)
    if text is None:
        text = key
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text
