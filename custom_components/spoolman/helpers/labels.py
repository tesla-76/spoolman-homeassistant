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
cannot translate (device names built at runtime) is resolved here.

To avoid blocking file I/O inside the event loop, call :func:`preload_labels`
once from ``async_setup_entry`` (before platforms are set up): it loads the
``common`` section through Home Assistant's own translation loader and caches
it in ``hass.data``. :func:`common_label` then serves labels from memory and
only falls back to direct file reads when no preloaded labels exist (e.g.
offline unit tests or a language switch without restart).
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

# Kept as a literal (instead of importing const.DOMAIN) so this module stays
# importable standalone, e.g. for offline unit tests. Must match const.DOMAIN.
_DOMAIN = "spoolman"

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

    When a Home Assistant instance with preloaded labels (see
    :func:`preload_labels`) is passed, labels are served from memory and no
    filesystem access happens (safe inside the event loop). Otherwise the
    translation files are read directly, with English fallback.
    """
    lang, labels = _resolve_labels(hass_or_lang)
    template = (labels or {}).get(key)
    if template is None:
        template = _load_lang(lang).get("common", {}).get(key)
    if template is None:
        template = _load_lang("en").get("common", {}).get(key, default)
    try:
        return template.format(**fmt) if fmt else template
    except (KeyError, IndexError, ValueError):
        return template


def _resolve_labels(hass_or_lang) -> tuple[str, dict | None]:
    """Return ``(language, preloaded labels)`` for a hass instance or lang code.

    Preloaded labels are only used when they were stored for the *current*
    language; on mismatch ``None`` is returned so the caller falls back to
    (correct, freshly read) file data.
    """
    if hasattr(hass_or_lang, "config") and hasattr(hass_or_lang.config, "language"):
        lang = hass_or_lang.config.language or "en"
        try:
            stored = (hass_or_lang.data.get(_DOMAIN, {}) or {}).get(
                "common_labels"
            ) or {}
        except Exception:  # noqa: BLE001 - degraded hass stub, use file fallback
            stored = {}
        if stored.get("lang") == lang:
            return lang, stored.get("labels") or {}
        return lang, None
    return str(hass_or_lang or "en"), None


async def preload_labels(hass) -> None:
    """Preload translated ``common`` device labels into ``hass.data``.

    Call once from ``async_setup_entry`` before platforms are set up. Loading
    goes through Home Assistant's own translation loader (executor-safe and
    cached by HA), so later :func:`common_label` calls never touch the
    filesystem inside the event loop.

    As a safety net the file cache is *also* warmed in an executor job: even
    if the translation loader yields nothing for the custom ``common``
    category, later lookups are pure cache hits and never block the loop.

    Never raises: on any failure the caches are simply left to on-demand
    (file) reads.
    """
    lang = getattr(getattr(hass, "config", None), "language", "en") or "en"
    labels: dict = {}
    try:
        # Local import: keeps this module importable without Home Assistant
        # (offline unit tests).
        from homeassistant.helpers import translation as translation_helper

        loaded = await translation_helper.async_get_translations(
            hass, lang, "common", {"spoolman"}
        )
        prefix = f"component.{_DOMAIN}.common."
        labels = {
            key[len(prefix) :]: value
            for key, value in loaded.items()
            if key.startswith(prefix)
        }
    except Exception:  # noqa: BLE001 - labels must never break setup
        labels = {}
    try:
        hass.data.setdefault(_DOMAIN, {})["common_labels"] = {
            "lang": lang,
            "labels": labels,
        }
    except Exception:  # noqa: BLE001 - same reason as above
        pass
    try:
        await hass.async_add_executor_job(_load_lang, lang)
    except Exception:  # noqa: BLE001 - same reason as above
        pass
    _LOGGER.debug(
        "Preloaded %d device labels for language '%s' (file cache warmed)",
        len(labels),
        lang,
    )


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
