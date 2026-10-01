# -*- coding: utf-8 -*-
"""Selección de clips para Shorts: prompt, llamada al LLM, validación y snap.

Solo se envía texto con timestamps al LLM (nunca rutas, audio ni video).
"""
import bisect
import json
import os
import re
import urllib.error
import urllib.request

from core import shorts_store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULTS = {
    'clip_min_s': 20,
    'clip_max_s': 60,
    'clip_count': 6,
    'language': 'es',
}
DURATION_TOLERANCE_S = 0.4
SNAP_MAX_S = 0.6
NEXT_WORD_GUARD_S = 0.15
MAX_TITLE_CHARS = 90
MIN_WORDS = 20
PHRASE_GAP_S = 0.6
PHRASE_MAX_S = 15.0


class ClipSelectError(Exception):
    """Fallo recuperable: el usuario puede exportar el prompt y cargar JSON a mano."""


def _opt(cfg, key):
    return (cfg or {}).get(key, DEFAULTS[key])


def _check_words(words):
    if len(words) < MIN_WORDS:
        raise ClipSelectError(
            f"Transcripción demasiado corta ({len(words)} palabras, mínimo {MIN_WORDS}): "
            "no hay voz suficiente para elegir clips.")


# ---------------------------------------------------------------- prompt

def group_phrases(words):
    """Agrupa palabras en frases [(t0, t1, texto)] por pausas o puntuación."""
    phrases, cur = [], []
    for w in words:
        if cur and (w['t0'] - cur[-1]['t1'] > PHRASE_GAP_S
                    or w['t1'] - cur[0]['t0'] > PHRASE_MAX_S):
            phrases.append(cur)
            cur = []
        cur.append(w)
        if re.search(r'[.?!…]$', w['w'].strip()):
            phrases.append(cur)
            cur = []
    if cur:
        phrases.append(cur)
    return [(p[0]['t0'], p[-1]['t1'], ' '.join(x['w'].strip() for x in p)) for p in phrases]


def build_prompt(words, cfg=None, duration=None):
    """Devuelve (system, user) para el LLM."""
    _check_words(words)
    n = _opt(cfg, 'clip_count')
    lo, hi = _opt(cfg, 'clip_min_s'), _opt(cfg, 'clip_max_s')
    lang = _opt(cfg, 'language')
    duration = duration if duration is not None else words[-1]['t1']
    lines = '\n'.join(f"[{a:.2f}-{b:.2f}] {t}" for a, b, t in group_phrases(words))

    system = (
        "Eres editor de Shorts de YouTube para un canal de producción musical "
        "(beatmaking, type beats, mezcla). Respondes SOLO con JSON válido, sin texto extra.")
    user = (
        f"Transcripción de un video de {duration:.0f} segundos (idioma: {lang}). "
        "Cada línea es una frase con su tiempo en segundos.\n\n"
        f"{lines}\n\n"
        f"Elige hasta {n} clips para Shorts de {lo} a {hi} segundos cada uno.\n"
        "Reglas:\n"
        "- Cada clip debe entenderse solo, sin contexto previo.\n"
        "- El gancho va en los primeros 3 segundos.\n"
        "- Empieza y termina en el límite de una frase, nunca a mitad de una.\n"
        "- Prefiere temas que funcionan en el canal: un número concreto, una opinión "
        "fuerte, un tip accionable o un desglose paso a paso.\n"
        "- Los clips no deben solaparse.\n"
        f"- start y end en segundos, entre 0 y {duration:.0f}; el título tiene máximo "
        f"{MAX_TITLE_CHARS} caracteres; puntaje entre 0 y 1.\n\n"
        "Formato de respuesta exacto:\n"
        '{"clips":[{"start":12.40,"end":51.80,"titulo":"...","gancho":"...",'
        '"motivo":"...","puntaje":0.86}]}')
    return system, user


# ------------------------------------------------------- parse / validate

def _first_balanced_object(text):
    start = text.find('{')
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == '\\':
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        start = text.find('{', start + 1)
    return None


def parse_and_repair(text):
    """Extrae el JSON de una respuesta: quita fences markdown y toma el primer
    objeto {...} balanceado. Lanza ClipSelectError si no se puede."""
    cleaned = re.sub(r'```[a-zA-Z]*', '', text or '')
    candidate = _first_balanced_object(cleaned)
    if candidate is None:
        raise ClipSelectError("La respuesta no contiene un objeto JSON.")
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ClipSelectError(f"JSON inválido: {e}")
    if not isinstance(data, dict) or not isinstance(data.get('clips'), list):
        raise ClipSelectError("El JSON debe ser un objeto con una lista 'clips'.")
    return data


def validate_clips(data, duration, cfg=None):
    """Devuelve (clips_validos, avisos). Descarta clips inválidos con aviso."""
    n = _opt(cfg, 'clip_count')
    lo, hi = _opt(cfg, 'clip_min_s'), _opt(cfg, 'clip_max_s')
    valid, warnings = [], []
    for i, c in enumerate(data.get('clips', []), 1):
        tag = f"Clip {i}"
        try:
            start, end = float(c['start']), float(c['end'])
            titulo = str(c.get('titulo') or '').strip()
            puntaje = float(c.get('puntaje', 0.5))
        except (KeyError, TypeError, ValueError, AttributeError):
            warnings.append(f"{tag}: campos inválidos, descartado.")
            continue
        length = end - start
        if start < 0 or end > duration + DURATION_TOLERANCE_S or end <= start:
            warnings.append(f"{tag}: fuera de la duración del video, descartado.")
        elif not (lo - DURATION_TOLERANCE_S <= length <= hi + DURATION_TOLERANCE_S):
            warnings.append(f"{tag}: dura {length:.1f} s (debe estar entre {lo} y {hi}), descartado.")
        elif not titulo or len(titulo) > MAX_TITLE_CHARS:
            warnings.append(f"{tag}: título vacío o de más de {MAX_TITLE_CHARS} caracteres, descartado.")
        elif not 0 <= puntaje <= 1:
            warnings.append(f"{tag}: puntaje fuera de 0-1, descartado.")
        else:
            valid.append({
                'start': start, 'end': min(end, duration), 'titulo': titulo,
                'gancho': str(c.get('gancho') or '').strip(),
                'motivo': str(c.get('motivo') or '').strip(),
                'puntaje': puntaje,
            })
    if len(valid) > n:
        warnings.append(f"El modelo devolvió {len(valid)} clips; se conservan los {n} de mayor puntaje.")
        valid = sorted(valid, key=lambda c: -c['puntaje'])[:n]
    return valid, warnings


# ------------------------------------------------------------------ snap

def snap_to_words(clip, words, cfg=None):
    """Ajusta start al t0 de una palabra y end al t1 de otra, sin cortar palabras.

    start: t0 de la palabra más cercana hacia atrás (máx SNAP_MAX_S); si no hay,
    la más cercana hacia adelante dentro del mismo margen.
    end: t1 de la palabra más cercana hacia adelante (máx SNAP_MAX_S), ampliado
    mientras la palabra siguiente empiece a menos de NEXT_WORD_GUARD_S.
    Devuelve el clip ajustado o None si queda fuera de rango.
    """
    lo, hi = _opt(cfg, 'clip_min_s'), _opt(cfg, 'clip_max_s')
    t0s = [w['t0'] for w in words]
    t1s = [w['t1'] for w in words]

    i = bisect.bisect_right(t0s, clip['start']) - 1   # última palabra con t0 <= start
    new_start = None
    if i >= 0 and clip['start'] - t0s[i] <= SNAP_MAX_S:
        new_start = t0s[i]
    elif i + 1 < len(words) and t0s[i + 1] - clip['start'] <= SNAP_MAX_S:
        new_start = t0s[i + 1]
    if new_start is None:
        return None

    j = bisect.bisect_left(t1s, clip['end'])           # primera palabra con t1 >= end
    if j >= len(words) or t1s[j] - clip['end'] > SNAP_MAX_S:
        return None
    while (j + 1 < len(words) and t0s[j + 1] - t1s[j] < NEXT_WORD_GUARD_S
           and t1s[j + 1] - clip['end'] <= SNAP_MAX_S):
        j += 1
    new_end = t1s[j]

    length = new_end - new_start
    if not (lo - DURATION_TOLERANCE_S <= length <= hi + DURATION_TOLERANCE_S):
        return None
    return {**clip, 'start': round(new_start, 3), 'end': round(new_end, 3)}


def snap_all(clips, words, cfg=None):
    out, warnings = [], []
    for c in clips:
        snapped = snap_to_words(c, words, cfg)
        if snapped is None:
            warnings.append(
                f"«{c['titulo']}» ({c['start']:.1f}-{c['end']:.1f}): no se pudo ajustar a "
                "bordes de palabra dentro del rango, descartado.")
        else:
            out.append(snapped)
    return out, warnings


# ------------------------------------------------------------ LLM client

def load_api_key(cfg):
    path = ((cfg or {}).get('llm') or {}).get('api_key_file') or 'config/llm_key.txt'
    if not os.path.isabs(path):
        path = os.path.join(ROOT, path)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read().strip() or None
    except OSError:
        return None


def call_llm(system, user, cfg, api_key, timeout=180):
    """POST compatible con OpenAI /chat/completions vía urllib."""
    llm = (cfg or {}).get('llm') or {}
    base = (llm.get('base_url') or '').rstrip('/')
    if not base:
        raise ClipSelectError("Falta llm.base_url en la configuración.")
    body = json.dumps({
        'model': llm.get('model'),
        'temperature': 0.3,
        'messages': [{'role': 'system', 'content': system},
                     {'role': 'user', 'content': user}],
    }).encode('utf-8')
    req = urllib.request.Request(
        f"{base}/chat/completions", data=body, method='POST',
        headers={'Content-Type': 'application/json',
                 'Authorization': f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode('utf-8'))
        return payload['choices'][0]['message']['content']
    except urllib.error.HTTPError as e:
        raise ClipSelectError(f"El LLM respondió HTTP {e.code}.")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ClipSelectError(f"No se pudo contactar al LLM: {e}")
    except (KeyError, IndexError, ValueError):
        raise ClipSelectError("Respuesta del LLM con formato inesperado.")


# ------------------------------------------------------------- pipeline

def _process_response(text, words, duration, cfg):
    data = parse_and_repair(text)
    clips, w1 = validate_clips(data, duration, cfg)
    clips, w2 = snap_all(clips, words, cfg)
    if not clips:
        raise ClipSelectError("Ningún clip válido tras validar y ajustar. " + ' '.join(w1 + w2))
    return clips, w1 + w2


def export_prompt(words, cfg=None, path=None, duration=None):
    """Texto del prompt (system + user) para pegarlo a mano; opcionalmente lo guarda."""
    system, user = build_prompt(words, cfg, duration)
    text = f"{system}\n\n{user}\n"
    if path:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
    return text


def import_response(path, words, video_id, cfg=None, duration=None, db_path=None):
    """Carga un JSON de respuesta desde archivo, lo valida y guarda propuestas."""
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    return _persist(text, words, video_id, cfg, duration, db_path)


def _persist(text, words, video_id, cfg, duration, db_path):
    _check_words(words)
    duration = duration if duration is not None else words[-1]['t1']
    clips, warnings = _process_response(text, words, duration, cfg)
    shorts_store.replace_clips(video_id, clips, db_path=db_path)  # solo con resultado válido
    shorts_store.update_video(video_id, db_path=db_path, estado='clips_listos')
    return clips, warnings


def select_clips(words, video_id, cfg=None, duration=None, db_path=None, llm_call=None):
    """Pide clips al LLM (un reintento si la respuesta no sirve) y los guarda.

    llm_call(system, user) -> str permite inyectar el transporte (tests).
    Si falla, no se modifica la tabla clips. Devuelve (clips, avisos).
    """
    _check_words(words)
    duration = duration if duration is not None else words[-1]['t1']
    if llm_call is None:
        key = load_api_key(cfg)
        if not key:
            raise ClipSelectError(
                "No hay config/llm_key.txt: usa export_prompt() y cargá la respuesta con import_response().")
        llm_call = lambda s, u: call_llm(s, u, cfg, key)  # noqa: E731

    system, user = build_prompt(words, cfg, duration)
    raw = llm_call(system, user)
    try:
        clips, warnings = _process_response(raw, words, duration, cfg)
    except ClipSelectError as first_error:
        retry_user = (f"{user}\n\nTu respuesta anterior no sirvió: {first_error}\n"
                      f"Respuesta anterior:\n{raw}\n\n"
                      "Corrígela y responde solo con el JSON.")
        raw = llm_call(system, retry_user)
        clips, warnings = _process_response(raw, words, duration, cfg)

    shorts_store.replace_clips(video_id, clips, db_path=db_path)
    shorts_store.update_video(video_id, db_path=db_path, estado='clips_listos')
    return clips, warnings
