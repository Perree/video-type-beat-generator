"""Beat parts (Intro/Verse/Pre-Chorus/Chorus/Outro) from per-bar energy -> YouTube chapters.

Energy only: a type beat's hook is where the drums/808 hit hardest, the verse relaxes.
Every failure returns no sections; chapters are optional.
"""
import math
import numpy as np

RATE = 11025
PHRASE_BARS = 4
FALLBACK_BAR = 2.0          # seconds per "bar" when BeatStars has no BPM
SILENCE_DB = 40             # below the loudest 50 ms frame: leading silence
CHORUS_RANGE_DB = 2.5       # a chorus phrase is within this of the loud level (90th percentile)
MIN_CONTRAST_DB = 1.5       # chorus vs rest; below that the beat is flat -> no chapters
PRE_CHORUS_DB = 1.5         # a pre-chorus must differ this much from the part before it
MIN_CHAPTER = 10            # YouTube rule
MIN_CHAPTERS = 3            # YouTube rule


def decode(audio, tools, seconds=None):
    """Mono float32 PCM at RATE Hz through ffmpeg (stdout)."""
    raw = tools._call([tools.ffmpeg, '-nostdin', '-v', 'error', '-protocol_whitelist', 'file',
                       '-i', str(audio), '-vn', '-ac', '1', '-ar', str(RATE),
                       *(['-t', str(seconds)] if seconds else []), '-f', 'f32le', '-'], 120, True)
    return np.frombuffer(raw or b'', dtype='<f4')


def bar_seconds(bpm):
    if type(bpm) in (int, float) and math.isfinite(bpm) and 40 <= bpm <= 250:
        return 240.0 / bpm
    return FALLBACK_BAR


def _db(values):
    return 10 * np.log10(np.maximum(values, 1e-10))


def _start_offset(samples, bar):
    """First non-silent 50 ms frame; the bar grid starts there (leading silence is common)."""
    size = RATE // 20
    frames = len(samples) // size
    if not frames:
        return 0.0
    power = _db(np.mean(samples[:frames * size].astype(np.float64).reshape(frames, size) ** 2, axis=1))
    audible = np.flatnonzero(power > power.max() - SILENCE_DB)
    offset = audible[0] * size / RATE if len(audible) else 0.0
    return offset if offset < bar * 2 else 0.0


def phrases(samples, bpm=None):
    """[(start_seconds, end_seconds, energy_db)] per 4-bar phrase; energy = median bar level,
    so a bar bleeding into the next part does not move the whole phrase."""
    total = len(samples) / RATE
    bar = bar_seconds(bpm)
    start = _start_offset(samples, bar)
    bars = []
    while start < total - 1e-6:
        end = min(start + bar, total)
        chunk = samples[int(start * RATE):int(end * RATE)]
        if len(chunk) and (end - start >= bar / 2 or not bars):
            bars.append([start, end, float(_db(np.mean(chunk.astype(np.float64) ** 2)))])
        elif bars:
            bars[-1][1] = end  # short tail joins the last bar
        start = end
    result = []
    for index in range(0, len(bars), PHRASE_BARS):
        group = bars[index:index + PHRASE_BARS]
        if result and len(group) < PHRASE_BARS / 2:
            result[-1] = (result[-1][0], group[-1][1], result[-1][2])
            continue
        result.append((group[0][0], group[-1][1], float(np.median([row[2] for row in group]))))
    if result:
        result[0] = (0.0,) + result[0][1:]
    return result


def label(rows):
    """Labels per phrase from its energy; None when the beat has no clear hook."""
    if len(rows) < MIN_CHAPTERS:
        return None
    energy = np.array([row[2] for row in rows])
    # Hooks sit near the loudest level; verses with lighter drums fall a few dB below it.
    high = energy >= np.percentile(energy, 90) - CHORUS_RANGE_DB
    if high.all() or energy[high].mean() - energy[~high].mean() < MIN_CONTRAST_DB:
        return None
    hooks = np.flatnonzero(high)
    first, last = hooks[0], hooks[-1]
    names = []
    for index, loud in enumerate(high):
        if loud:
            names.append('Chorus')
        elif index < first:
            names.append('Intro')
        elif index > last:
            names.append('Outro')
        else:
            names.append('Verse')
    # Pre-chorus: the phrase right before a chorus that stands apart (build-up or drop)
    # from the low part it closes.
    index = 0
    while index < len(rows):
        if high[index]:
            index += 1
            continue
        end = index
        while end < len(rows) and not high[end]:
            end += 1
        run = list(range(index, end))
        if end < len(rows) and len(run) >= 2:
            # The pre-chorus grows back over phrases that sound like its last one.
            size = 1
            while size < len(run) - 1 and abs(energy[run[-size - 1]] - energy[run[-1]]) < PRE_CHORUS_DB / 2:
                size += 1
            before = energy[run[:-size]].mean()
            if abs(energy[run[-size:]].mean() - before) >= PRE_CHORUS_DB:
                for position in run[-size:]:
                    names[position] = 'Pre-Chorus'
        index = end
    return names


def merge(rows, names, total):
    """Consecutive equal parts become one; [{'start', 'label'}]."""
    result = []
    for (start, _, _), name in zip(rows, names):
        if not result or result[-1]['label'] != name:
            result.append({'start': float(start), 'label': name})
    result[0]['start'] = 0.0
    return [row for row in result if row['start'] < total]


def youtube_rules(sections, total):
    """Whole-second starts, first at 0, each >= 10 s, at least 3; else []."""
    rows = [dict(row, start=math.floor(row['start'])) for row in sections]
    changed = True
    while changed and len(rows) > 1:
        changed = False
        for index, row in enumerate(rows):
            end = rows[index + 1]['start'] if index + 1 < len(rows) else math.floor(total)
            if end - row['start'] < MIN_CHAPTER:
                # A short part joins its neighbour: the previous one, or the next for the first.
                if index == 0:
                    rows[1] = dict(rows[1], start=0)
                del rows[index]
                changed = True
                break
        merged = []
        for row in rows:
            if merged and merged[-1]['label'] == row['label']:
                changed = True
                continue
            merged.append(row)
        rows = merged
    if len(rows) < MIN_CHAPTERS or rows[0]['start'] != 0:
        return []
    return rows


def detect(samples, bpm=None):
    total = len(samples) / RATE
    if total < MIN_CHAPTER * MIN_CHAPTERS:
        return []
    rows = phrases(samples, bpm)
    names = label(rows)
    if not names:
        return []
    return youtube_rules(merge(rows, names, total), total)


def wants_sections(channel, spec):
    """Only channels that use them pay the extra decode: {chapters} in the SEO or section cuts."""
    seo = channel.get('seo') if isinstance(channel.get('seo'), dict) else {}
    text = seo.get('description')
    return bool(spec.get('section_cuts')) or (isinstance(text, str) and '{chapters}' in text)


def sections(audio, tools, bpm=None, seconds=None):
    try:
        return detect(decode(audio, tools, seconds), bpm)
    except Exception:
        return []


def stamp(second):
    second = int(second)
    hours, rest = divmod(second, 3600)
    minutes, secs = divmod(rest, 60)
    return f'{hours}:{minutes:02d}:{secs:02d}' if hours else f'{minutes}:{secs:02d}'


def chapters_text(rows):
    """'0:00 Intro\\n0:21 Chorus...' or '' (fill_chapters then drops the token)."""
    if not rows or len(rows) < MIN_CHAPTERS or rows[0]['start'] != 0:
        return ''
    return '\n'.join(f"{stamp(row['start'])} {row['label']}" for row in rows)
