"""Untrusted JSON boundary for the Claude Code / vidIQ / Analytics report."""
from datetime import datetime, timedelta, timezone
import math
import unicodedata
from core.beat_cloud import decode_document

MAX_BYTES = 128 * 1024


def text(value, limit=100):
    if (type(value) is not str or not value.strip() or len(value) > limit
            or value != value.strip() or any(unicodedata.category(c).startswith('C') for c in value)
            or any(c in value for c in '<>{}')):
        raise ValueError('seo_text_invalid')
    return value


def texts(value, count=40, limit=100):
    if type(value) is not list or len(value) > count:
        raise ValueError('seo_list_invalid')
    result = [text(v, limit) for v in value]
    if len({v.casefold() for v in result}) != len(result):
        raise ValueError('seo_duplicate')
    return result


def fields(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        raise ValueError('seo_schema_invalid')


def moment(value):
    text(value, 40)
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError()
        return result.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise ValueError('seo_date_invalid') from None


def validate_report(report, channel, now, max_age_days=14):
    fields(report, ('schema_version', 'generated_at', 'channel_id', 'sources', 'keywords'))
    if type(report['schema_version']) is not int or report['schema_version'] != 1:
        raise ValueError('seo_version_invalid')
    if text(report['channel_id'], 200) != channel:
        raise ValueError('seo_channel_mismatch')
    date = moment(report['generated_at'])
    now = moment(now)
    if not now - timedelta(days=max_age_days) <= date <= now:
        raise ValueError('seo_report_expired')
    if report['sources'] != ['claude_code', 'vidiq', 'youtube_analytics']:
        raise ValueError('seo_sources_invalid')
    rows = report['keywords']
    if type(rows) is not list or len(rows) > 100:
        raise ValueError('seo_keywords_invalid')
    seen = set()
    for row in rows:
        fields(row, ('tag', 'score', 'views', 'ctr', 'average_view_percentage'))
        tag = text(row['tag']).casefold()
        if tag in seen:
            raise ValueError('seo_duplicate')
        seen.add(tag)
        if type(row['views']) is not int or not 0 <= row['views'] <= 10**12:
            raise ValueError('seo_metric_invalid')
        for key, upper in (('score', 100), ('ctr', 100), ('average_view_percentage', 100)):
            value = row[key]
            if type(value) not in (int, float) or not 0 <= value <= upper or not math.isfinite(value):
                raise ValueError('seo_metric_invalid')
    return report


def parse_report(payload, channel, now):
    try:
        if type(payload) is str:
            payload = payload.encode('utf-8')
        if type(payload) is not bytes or len(payload) > MAX_BYTES:
            raise ValueError()
        # json.loads(bytes) auto-detects UTF-16/32. Our boundary is UTF-8 only.
        return validate_report(decode_document(payload.decode('utf-8')), channel, now)
    except Exception:
        # Never echo input, parser errors, paths, or report instructions.
        raise ValueError('seo_report_rejected') from None
