# -*- coding: utf-8 -*-
"""Identificadores de sección de la app y filtrado de canales por sección.

El tipo de cada canal sale de ``core.channel_kind``. Un canal sin ``section`` o con una
desconocida es un error explícito: nunca se lo trata como Beats.
"""
from core import channel_kind

SECTION_BEATS = "beats"
SECTION_LOOP_KITS = "loop_kits"

ALL_SECTIONS = (SECTION_BEATS, SECTION_LOOP_KITS)
# Valor que dejó la sección "Marca personal" (dada de baja): los canales con este
# valor se conservan tal cual en la config pero no pertenecen a ninguna sección activa.
_LEGACY_IGNORED_SECTION = channel_kind.IGNORED_SECTION

PLACEHOLDER_MESSAGE = "Esta sección se completa en una fase siguiente."


def channel_section(channel_cfg: dict) -> str:
    """
    Devuelve la sección de un canal.

    Returns:
        beats o loop_kits; "personal" (legacy) se devuelve tal cual para que
        ningún filtro por sección lo incluya.

    Raises:
        channel_kind.ChannelKindError: sin ``section`` o con una desconocida.
    """
    section = channel_cfg.get("section") if isinstance(channel_cfg, dict) else None
    tipo = channel_kind.from_section(section)
    return _LEGACY_IGNORED_SECTION if tipo is None else channel_kind.SECTION_OF[tipo]


def filter_channels_by_section(channels: dict, section: str) -> dict:
    """
    Filtra un dict de canales (``{nombre: {section, …}}``) por sección.

    Raises:
        channel_kind.ChannelKindError: si algún canal no tiene tipo definido.
    """
    if not isinstance(channels, dict):
        return {}
    return {name: cfg for name, cfg in channels.items() if channel_section(cfg) == section}


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
