"""Regression cases from the October application/security review. No live services."""
import io
import csv
import json
import os
import tempfile
import unittest
import urllib.request
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.response import addinfourl

from core import bulk_queue as bq, channel_profile as cp, channel_templates as ct
from core import kit_art, kit_http, kit_llm, kit_spend, manual_render as mr, youtube


class HttpTests(unittest.TestCase):
    def test_redirect_cannot_forward_authorization_or_body(self):
        seen = []

        class Server(urllib.request.HTTPSHandler):
            def https_open(self, req):
                seen.append(req)
                headers = Message()
                headers['Location'] = 'https://untrusted.invalid/capture'
                response = addinfourl(io.BytesIO(b''), headers, req.full_url, 302)
                response.msg = 'Found'
                return response

        real_build = urllib.request.build_opener
        def build(*handlers):
            self.assertTrue(any(isinstance(h, urllib.request.ProxyHandler) and h.proxies == {}
                                for h in handlers))
            return real_build(*handlers, Server())

        request = urllib.request.Request('https://api.openai.com/v1/images/edits',
                                         data=b'private-image', headers={'Authorization': 'Bearer fixture'})
        with patch('urllib.request.build_opener', side_effect=build):
            with self.assertRaisesRegex(kit_http.HttpRejected, 'redirect_rejected'):
                kit_http.open_request(request)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].full_url, request.full_url)

    def test_destination_and_response_limits(self):
        for url in ('https://127.0.0.1/a', 'https://localhost/a', 'https://evil.invalid/a',
                    'http://api.openai.com/a', 'https://api.openai.com:444/a',
                    'https://api.openai.com@evil.invalid/a', 'https://api.openai.com/a#fragment'):
            with self.subTest(url=url), self.assertRaises(kit_http.HttpRejected):
                kit_http.image_url(url, 'https://api.openai.com/v1')
        url = 'https://oaidalleapiprodscus.blob.core.windows.net/private/image?sig=fixture'
        self.assertEqual(kit_http.image_url(url, 'https://api.openai.com/v1'), url)
        with patch.dict(os.environ, {kit_http.DOWNLOAD_HOSTS_ENV: 'cdn.example'}):
            self.assertEqual(kit_http.image_url('https://cdn.example/a', 'https://api.openai.com'),
                             'https://cdn.example/a')
        with self.assertRaisesRegex(kit_http.HttpRejected, 'response_limit'):
            kit_http.read_response(io.BytesIO(b'12345'), limit=4)
        response = SimpleNamespace(headers={'Content-Length': '999'}, read=Mock())
        with self.assertRaises(kit_http.HttpRejected):
            kit_http.read_response(response, limit=4)
        response.read.assert_not_called()
        self.assertEqual(kit_http.read_response(io.BytesIO(b'ok'), limit=4), b'ok')

    def test_invalid_timeout_never_opens_network(self):
        for seconds in (float('inf'), float('nan'), -1, 0, 181, True):
            with patch('urllib.request.build_opener') as opener:
                with self.assertRaisesRegex(kit_http.HttpRejected, 'timeout_rejected'):
                    kit_http.open_request(urllib.request.Request('https://api.openai.com'), seconds)
                opener.assert_not_called()

    def test_base_url_rejects_query_and_fragment(self):
        for suffix in ('?secret=x', '#ignored', '/v1?ignored=x'):
            with self.assertRaises(kit_llm.KitLlmError):
                kit_llm.check_base_url('https://api.openai.com' + suffix)

    def test_provider_image_url_cannot_trigger_ssrf(self):
        with tempfile.TemporaryDirectory() as tmp:
            from PIL import Image
            image = Path(tmp) / 'ref.png'
            Image.new('RGB', (8, 8)).save(image)
            response = io.BytesIO(json.dumps({'data': [{'url': 'https://127.0.0.1/private'}]}).encode())
            with patch.object(kit_http, 'open_request', return_value=response) as opener:
                with self.assertRaises(kit_art.KitArtError):
                    kit_art.api_client('background', [str(image)], key='fixture')
            self.assertEqual(opener.call_count, 1)

    def test_image_download_does_not_receive_api_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            from PIL import Image
            image = Path(tmp) / 'ref.png'
            Image.new('RGB', (8, 8)).save(image)
            url = 'https://oaidalleapiprodscus.blob.core.windows.net/i?sig=fixture'
            responses = [io.BytesIO(json.dumps({'data': [{'url': url}]}).encode()), io.BytesIO(b'image')]
            with patch.object(kit_http, 'open_request', side_effect=responses) as opener:
                self.assertEqual(kit_art.api_client('background', [str(image)], key='fixture'), b'image')
            self.assertEqual(opener.call_args_list[0].args[0].get_header('Authorization'), 'Bearer fixture')
            self.assertIsNone(opener.call_args_list[1].args[0].get_header('Authorization'))


class LocalTests(unittest.TestCase):
    def test_csv_titles_are_text_without_changing_exported_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = dict(title='=HYPERLINK("https://invalid")', folder=tmp)
            mr.add_pending(tmp, '+channel', result)
            with open(Path(tmp) / mr.PENDING_CSV, encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.reader(stream))
            self.assertTrue(rows[1][0].startswith("'+"))
            self.assertTrue(rows[1][1].startswith("'="))
            self.assertTrue(result['title'].startswith('='))

    def test_probe_has_timeout_and_rejects_nonfinite_duration(self):
        from core import ffmpeg_util as ff
        for value in ('nan', 'inf', '-1', '0', '3.5'):
            response = SimpleNamespace(returncode=0, stdout=value)
            with patch.object(ff, 'resolve_tool', return_value='ffprobe'), \
                    patch.object(ff.subprocess, 'run', return_value=response) as run:
                self.assertEqual(ff.get_media_duration('audio.mp3'), 3.5 if value == '3.5' else None)
                self.assertEqual(run.call_args.kwargs['timeout'], 30)

    def test_reserved_windows_names_are_safe_or_explained(self):
        for name in ('CON', 'con.txt', 'LPT1', 'aux.wav', 'COM¹'):
            with self.subTest(name=name):
                self.assertFalse(ct.reserved_filename(ct.sanitize_filename(name)))
                with self.assertRaises(cp.ProfileError):
                    cp.check_name(name)
        self.assertEqual(ct.sanitize_filename('Title\x00\n'), 'Title__')
        self.assertEqual(cp.check_name('Console'), 'Console')

    def test_nonfinite_cache_size_cannot_crash_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'settings.json'
            for value in ('Infinity', '-Infinity', 'NaN', '1e309'):
                path.write_text('{"cache_max_gb":' + value + '}', encoding='utf-8')
                self.assertEqual(mr.load_settings(str(path))['cache_max_gb'], 5)

    def test_bulk_archive_or_log_failure_keeps_summary_and_other_channels(self):
        def batch(paths, *args, on_done, on_error, **kwargs):
            for audio in paths:
                on_done(audio, {'video': 'generated'})
            return [], []

        with patch.object(cp, 'load', return_value=cp.default_profile('x')), \
                patch.object(mr, 'run_batch', side_effect=batch), \
                patch.object(bq, 'mark_done', side_effect=PermissionError), \
                patch.object(bq, 'log_error', side_effect=PermissionError):
            summary = bq.run_bulk('root', 'out', [{'channel': c, 'path': c+'.mp3'} for c in ('A', 'B')],
                                  tools=object())
        self.assertEqual({c: v['ok'] for c, v in summary.items()}, {'A': 1, 'B': 1})
        self.assertTrue(all(len(v['errores']) == 2 for v in summary.values()))

    def test_pending_csv_failure_preserves_success_and_continues(self):
        with tempfile.TemporaryDirectory() as tmp:
            done, errors = [], []
            result = dict(title='generated', folder=tmp)
            with patch.object(cp, 'media', return_value=(['image.png'], [])), \
                    patch.object(mr, 'render_beat', return_value=result), \
                    patch.object(mr, 'add_pending', side_effect=PermissionError):
                results, failures = mr.run_batch(['a.mp3', 'b.mp3'], 'C', tmp, tmp,
                    profile=cp.default_profile('C'), tools=object(),
                    on_done=lambda audio, _: done.append(audio),
                    on_error=lambda audio, msg: errors.append((audio, msg)))
            self.assertEqual(done, ['a.mp3', 'b.mp3'])
            self.assertEqual(len(results), 2)
            self.assertEqual(len(failures), 2)
            self.assertTrue(all('pendientes.csv' in message for _, message in errors))

    def test_render_permission_failure_does_not_abort_next_beat(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = dict(title='second', folder=tmp)
            with patch.object(cp, 'media', return_value=(['image.png'], [])), \
                    patch.object(mr, 'render_beat', side_effect=[PermissionError(), result]), \
                    patch.object(mr, 'add_pending'):
                results, failures = mr.run_batch(['a.mp3', 'b.mp3'], 'C', tmp, tmp,
                    profile=cp.default_profile('C'), tools=object())
            self.assertEqual(results, [result])
            self.assertEqual(len(failures), 1)


class UploadAndBudgetTests(unittest.TestCase):
    def test_worker_suite_excludes_qt_dependencies(self):
        import ast
        from scripts.smoke_beat_hardening import test_paths
        for path in test_paths(worker_only=True):
            tree = ast.parse(path.read_text(encoding='utf-8-sig'))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertFalse((node.module or '').startswith('PyQt'), path.name)
                elif isinstance(node, ast.Import):
                    self.assertFalse(any(n.name.startswith('PyQt') for n in node.names), path.name)

    def test_thumbnail_timeout_retains_successful_video_id(self):
        media = Mock()
        media.stream.return_value = io.BytesIO()
        service = Mock()
        insert = service.videos.return_value.insert.return_value
        insert.next_chunk.return_value = (None, {'id': 'Abcdefghijk', 'status': {'privacyStatus': 'private'}})
        service.thumbnails.return_value.set.return_value.execute.side_effect = TimeoutError('private-body')
        with patch.object(youtube, '_load_credentials'), patch.object(youtube, '_service', return_value=service), \
                patch('googleapiclient.http.MediaFileUpload', return_value=media), \
                patch.object(os.path, 'exists', return_value=True):
            result = youtube.upload('channel', 'video.mp4', 'title', thumbnail='thumb.jpg')
        self.assertEqual(result['youtube_id'], 'Abcdefghijk')
        self.assertTrue(result['thumbnail_error'])
        self.assertNotIn('private-body', result['thumbnail_error'])
        self.assertEqual(service.videos.return_value.insert.call_count, 1)

    def test_nonfinite_and_negative_budget_values_fail_closed(self):
        for value in (float('inf'), float('nan'), -1):
            self.assertFalse(kit_spend.check(0, value, 0.25))
            store = SimpleNamespace(spend_month=lambda month, value=value: value)
            self.assertEqual(kit_spend.Budget(store=store).blocked(0.25), kit_spend.REASON_STATE)
        for key in kit_spend.DEFAULTS:
            cfg = kit_spend.settings({'spend': {key: float('inf')}})
            self.assertEqual(cfg[key], kit_spend.DEFAULTS[key])
        for value in (float('inf'), float('nan'), -10, 'invalid'):
            store = SimpleNamespace(spend_month=lambda month, value=value:
                                    kit_spend.spent({'spend': {month: {'usd': value}}}, month))
            self.assertEqual(kit_spend.Budget(store=store).blocked(0.25), kit_spend.REASON_STATE)


if __name__ == '__main__':
    unittest.main()
