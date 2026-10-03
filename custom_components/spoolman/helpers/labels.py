"""Centralised user-visible labels for the Spoolman integration.

All suffixes / templates that used to be hardcoded as English f-strings
(e.g. ``f"{spool_name} Used Weight"``) are now declared as translation keys
whose human-readable values live in:

- ``strings.json`` (English source of truth)
- ``translations/en.json`` (English)
- ``translations/it.json`` (Italian)
- ``translations/de.json`` (German)

Entity suffixes use the Home Assistant native mechanism (``translation_key``
+ ``has_entity_name=True``), so HA resolves them automatically when the user
switches language. Only the small set of *dynamic device* fallbacks that HA
cannot translate (device names built at runtime) is resolved here by reading
the same JSON files based on ``hass.config.language`` with English fallback.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_CANDIDATE_DIRS = (
    Path(__file__).resolve().parent.parent / "translations",
    Path(__file__).resolve().parent.parent,
)


def _translations_dir() -> Path:
    for candidate in _CANDIDATE_DIRS:
        if (candidate / "en.json").exists():
            return candidate
    return _CANDIDATE_DIRS[0]


@lru_cache(maxsize=8)
def _load_lang(lang: str) -> dict:
    """Load the translation file for ``lang`` with English fallback."""
    base = _translations_dir()
    normalized = (lang or "en").lower().replace("_", "-").split("-")[0]
    data: dict = {}
    for candidate in ("en", normalized):
        if base.name == "translations":
            path = base / f"{candidate}.json"
        else:
            # Tolerate being pointed at the integration root instead.
            path = base / "translations" / f"{candidate}.json"
        try:
            if path.exists():
                data = {**data, **json.loads(path.read_text(encoding="utf-8"))}
        except (OSError, ValueError):
            continue
    # Also try strings.json as ultimate fallback for English keys.
    if not data:
        strings = (
            base.parent / "strings.json"
            if base.name == "translations"
            else base / "strings.json"
        )
        try:
            if strings.exists():
                data = json.loads(strings.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
    return data


def common_label(hass_or_lang, key: str, default: str = "", **fmt) -> str:
    """Return a translated ``common`` label (device fallbacks).

    ``hass_or_lang`` may be a Home Assistant instance or a language code
    string (``"en"`` / ``"it"`` / ``"de"``). Unknown keys return ``default``.
    """
    if hasattr(hass_or_lang, "config") and hasattr(hass_or_lang.config, "language"):
        lang = hass_or_lang.config.language or "en"
    else:
        lang = str(hass_or_lang or "en")
    template = _load_lang(lang).get("common", {}).get(key)
    if template is None:
        template = _load_lang("en").get("common", {}).get(key, default)
    try:
        return template.format(**fmt) if fmt else template
    except (KeyError, IndexError, ValueError):
        return template


def build_spool_name(filament: dict | None, spool_id, hass_or_lang="en") -> str:
    """Build the spool device name from Spoolman data (data, not translated).

    Falls back to the translatable ``common.spool_fallback`` template
    (``"Spoolman Spool {id}"``) when name/material are missing.
    """
    filament = filament or {}
    vendor_name = (filament.get("vendor") or {}).get("name")
    name = filament.get("name")
    material = filament.get("material")
    if name and material:
        if vendor_name:
            return f"{vendor_name} {name} {material}"
        return f"{name} {material}"
    return common_label(
        hass_or_lang, "spool_fallback", f"Spoolman Spool {spool_id}", id=spool_id
    )


def build_filament_name(filament: dict | None, hass_or_lang="en") -> str:
    """Build the filament device/sensor name from Spoolman data."""
    filament = filament or {}
    vendor_name = (filament.get("vendor") or {}).get("name")
    name = filament.get("name")
    material = filament.get("material")
    if name and material:
        if vendor_name:
            return f"{vendor_name} {name} {material}"
        return f"{name} {material}"
    return common_label(
        hass_or_lang,
        "filament_fallback",
        f"Spoolman Filament {filament.get('id', '?')}",
        id=filament.get("id", "?"),
    )
