# -*- coding: utf-8 -*-
"""Subtítulos ASS para Shorts: grupos de 3–4 palabras, la activa resaltada.

Sin librerías extra. El archivo se escribe en shorts_cache/ con nombre ASCII
porque el filtro `ass` de FFmpeg se rompe con acentos en la ruta.
"""
import os

PLAY_RES_X = 1080
PLAY_RES_Y = 1920
GROUP_MIN = 3
GROUP_MAX = 4

_DEFAULT_STYLE = {
    "font": "Arial",
    "size": 64,
    "margin_v": 400,
    "primary_color": "&H00FFFFFF",
    "highlight_color": "&H0000FFFF",
    "outline": 4,
}


def subtitle_style(cfg):
    """Estilo ASS desde el bloque shorts de la config.

    margin_v sale de subtitles y, si no está, de layouts.obs_unico
    (alto para no tapar la DAW).

    Args:
        cfg: bloque `shorts` (puede ser None).

    Returns:
        Dict con font, size, margin_v, primary, highlight, outline.
    """
    sub = dict(_DEFAULT_STYLE)
    sub.update((cfg or {}).get("subtitles") or {})
    layouts = (cfg or {}).get("layouts") or {}
    obs = layouts.get("obs_unico") or {}
    if "margin_v" not in ((cfg or {}).get("subtitles") or {}) and "margin_v" in obs:
        sub["margin_v"] = obs["margin_v"]
    primary = _normalize_color(sub.get("primary_color") or _DEFAULT_STYLE["primary_color"])
    highlight = _normalize_color(sub.get("highlight_color") or _DEFAULT_STYLE["highlight_color"])
    return {
        "font": sub.get("font") or "Arial",
        "size": int(sub.get("size") or 64),
        "margin_v": int(sub.get("margin_v") if sub.get("margin_v") is not None else 400),
        "primary": primary,
        "highlight": highlight,
        "outline": int(sub.get("outline") if sub.get("outline") is not None else 4),
    }


def words_in_window(words, start_s, end_s):
    """Palabras que pisan el clip, con tiempos relativos al inicio del corte.

    Args:
        words: lista {t0, t1, w} en tiempo del video largo.
        start_s: inicio del clip.
        end_s: fin del clip.

    Returns:
        Lista {t0, t1, w} en segundos desde 0.
    """
    span = max(0.0, float(end_s) - float(start_s))
    out = []
    for word in words or []:
        t0 = float(word["t0"])
        t1 = float(word["t1"])
        if t1 <= start_s or t0 >= end_s:
            continue
        rel0 = max(0.0, t0 - start_s)
        rel1 = min(span, t1 - start_s)
        if rel1 <= rel0:
            rel1 = min(span, rel0 + 0.05)
        text = str(word.get("w") or "").strip()
        if not text or rel0 >= span:
            continue
        out.append({"t0": rel0, "t1": rel1, "w": text})
    return out


def group_words(words):
    """Parte la lista en grupos de 4 y, si sobra 1, el último grupo queda en 3.

    Un resto de 1 palabra se ve cortado en pantalla. Con 5 palabras el corte
    es 3+2; con 1–4 se deja un solo grupo.

    Args:
        words: palabras ya recortadas al clip.

    Returns:
        Lista de listas de palabras.
    """
    words = list(words or [])
    if not words:
        return []
    groups = [words[i:i + GROUP_MAX] for i in range(0, len(words), GROUP_MAX)]
    if len(groups) >= 2 and len(groups[-1]) == 1 and len(groups[-2]) > GROUP_MIN:
        moved = groups[-2].pop()
        groups[-1].insert(0, moved)
    return groups


def build_ass(words, start_s, end_s, cfg=None):
    """Arma el documento ASS de un clip.

    Cada grupo se dibuja entero mientras dura una de sus palabras, y esa
    palabra lleva el color de resalte. Así no hace falta karaoke `\\k`.

    Args:
        words: palabras del video largo.
        start_s, end_s: ventana del clip.
        cfg: bloque shorts.

    Returns:
        Texto ASS (UTF-8).
    """
    style = subtitle_style(cfg)
    window = words_in_window(words, start_s, end_s)
    events = []
    for group in group_words(window):
        for index, active in enumerate(group):
            if active["t1"] <= active["t0"]:
                continue
            events.append(
                "Dialogue: 0,{start},{end},Default,,0,0,0,,{text}".format(
                    start=_ass_time(active["t0"]),
                    end=_ass_time(active["t1"]),
                    text=_group_text(group, index, style),
                )
            )
    font = str(style["font"]).replace(",", " ")
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {PLAY_RES_X}\n"
        f"PlayResY: {PLAY_RES_Y}\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,{font},{size},{primary},&H000000FF,&H00000000,"
        "&H64000000,-1,0,0,0,100,100,0,0,1,{outline},0,2,80,80,{margin},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    ).format(
        font=font,
        size=style["size"],
        primary=style["primary"],
        outline=style["outline"],
        margin=style["margin_v"],
    )
    return header + "\n".join(events) + ("\n" if events else "")


def write_ass(path, words, start_s, end_s, cfg=None):
    """Escribe el ASS en `path` (UTF-8 con BOM, que libass lee bien en Windows).

    Args:
        path: destino. La carpeta se crea si falta.
        words, start_s, end_s, cfg: ver build_ass.

    Returns:
        path.
    """
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    text = build_ass(words, start_s, end_s, cfg)
    with open(path, "w", encoding="utf-8-sig", newline="\n") as handle:
        handle.write(text)
    return path


def _normalize_color(value):
    """Deja el color como &HAABBGGRR, sin el & final del override."""
    text = str(value or "").strip()
    if text.endswith("&"):
        text = text[:-1]
    if not text.startswith("&H"):
        text = "&H00FFFFFF"
    return text


def _ass_time(seconds):
    """Segundos a H:MM:SS.cc (centésimas, reloj del ASS)."""
    centis = int(round(max(0.0, float(seconds)) * 100))
    hours, centis = divmod(centis, 360000)
    minutes, centis = divmod(centis, 6000)
    secs, centis = divmod(centis, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def _escape_text(text):
    return (
        str(text)
        .replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\n", " ")
    )


def _group_text(group, active_index, style):
    parts = []
    for index, word in enumerate(group):
        color = style["highlight"] if index == active_index else style["primary"]
        parts.append(f"{{\\c{color}&}}{_escape_text(word['w'])}")
    return " ".join(parts)
