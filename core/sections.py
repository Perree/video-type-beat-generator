# -*- coding: utf-8 -*-
"""Identificadores de sección de la app y filtrado de canales por sección."""

SECTION_BEATS = "beats"
SECTION_LOOP_KITS = "loop_kits"
SECTION_PERSONAL = "personal"

ALL_SECTIONS = (SECTION_BEATS, SECTION_LOOP_KITS, SECTION_PERSONAL)
DEFAULT_SECTION = SECTION_BEATS

PLACEHOLDER_MESSAGE = "Esta sección se completa en una fase siguiente."


def channel_section(channel_cfg: dict) -> str:
    """
    Devuelve la sección de un canal; sin campo explícito cuenta como beats.

    Args:
        channel_cfg: dict de configuración del canal (groups, title_template, …).

    Returns:
        Uno de beats, loop_kits o personal.
    """
    if not isinstance(channel_cfg, dict):
        return DEFAULT_SECTION
    section = channel_cfg.get("section")
    if section in ALL_SECTIONS:
        return section
    return DEFAULT_SECTION


def filter_channels_by_section(channels: dict, section: str) -> dict:
    """
    Filtra el dict de canales de app_config por sección.

    Args:
        channels: mapa nombre -> configuración del canal.
        section: sección activa (beats, loop_kits, personal).

    Returns:
        Subconjunto de channels cuya section coincide.
    """
    if not isinstance(channels, dict):
        return {}
    result = {}
    for name, cfg in channels.items():
        if channel_section(cfg if isinstance(cfg, dict) else {}) == section:
            result[name] = cfg
    return result


def channel_names_for_section(channels: dict, section: str) -> list:
    """Lista ordenada de nombres de canal en la sección dada."""
    return sorted(filter_channels_by_section(channels, section).keys())


def section_library_kind(section: str) -> str:
    """
    Mapea la sección activa al kind de core.library.

    Returns:
        'loop_kit' en Loop kits; 'beat' en Beats y en el resto.
    """
    if section == SECTION_LOOP_KITS:
        from core.library import KIND_LOOP_KIT
        return KIND_LOOP_KIT
    from core.library import KIND_BEAT
    return KIND_BEAT


def ensure_channel_sections(channels: dict) -> bool:
    """
    Añade section=beats a canales legacy que no lo tengan.

    Returns:
        True si se modificó algún canal.
    """
    if not isinstance(channels, dict):
        return False
    changed = False
    for _name, cfg in channels.items():
        if not isinstance(cfg, dict):
            continue
        if cfg.get("section") not in ALL_SECTIONS:
            cfg["section"] = DEFAULT_SECTION
            changed = True
    return changed
