"""Offline desktop Dropbox regression: app root, CAS and immutable remote state."""
import json
import os
from pathlib import Path
from threading import Event, get_ident
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import Qt
from dropbox.files import FolderMetadata, FileMetadata
from core.beat_cloud import BeatCloud, CloudError, Conflict
from core.beat_fakes import MemoryDropbox
from core.beat_panel_cloud import local_transport, PanelCloud
from core.beat_tasks import Cancelled, load_state
from core.beat_dropbox_picker import DropboxPicker
import test_beat_panel as panel_tests
from test_beat_panel import pump


SECRET = 'secret-fixture-never-display'


def folder(path):
    return FolderMetadata(name=path.rsplit('/', 1)[-1], id='id:folder', path_display=path)


def file(path):
    from datetime import datetime
    return FileMetadata(name=path.rsplit('/', 1)[-1], id='id:file', path_display=path,
                        client_modified=datetime(2026, 1, 1), server_modified=datetime(2026, 1, 1),
                        rev='0123456789abcdef', size=10)


class BrowseTransport:
    def __init__(self):
        self.client = self
        self.calls = []
        self.pages = [SimpleNamespace(entries=[folder('/Videos'), folder('/Art')], has_more=False)]

    def _call(self, fn):
        return fn()

    def files_list_folder(self, path, **kwargs):
        self.calls.append((path, kwargs, get_ident()))
        return self.pages[0]

    def files_list_folder_continue(self, cursor):
        self.calls.append(cursor)
        return self.pages[-1]


class CloudTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'token.json'

    def test_missing_token_falls_back_to_beat_environment_only(self):
        with patch('core.beat_cloud.DropboxTransport.from_env', return_value='env') as factory:
            self.assertEqual(local_transport(self.path), 'env')
            factory.assert_called_once_with()

    def test_missing_all_credentials_is_sanitized(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(CloudError) as caught:
                local_transport(self.path)
        self.assertNotIn(SECRET, str(caught.exception))

    def test_local_connection_reuses_credentials_without_mutation(self):
        raw = json.dumps(dict(app_key=SECRET, refresh_token=SECRET))
        self.path.write_text(raw, encoding='utf-8')
        with patch('dropbox.Dropbox', return_value='client') as factory, \
                patch('core.beat_cloud.DropboxTransport.from_env') as env:
            self.assertEqual(local_transport(self.path).client, 'client')
            self.assertEqual(factory.call_args.kwargs['app_key'], SECRET)
            self.assertEqual(factory.call_args.kwargs['oauth2_refresh_token'], SECRET)
            self.assertEqual(factory.call_args.kwargs['max_retries_on_error'], 0)
            env.assert_not_called()
        self.assertEqual(self.path.read_text(encoding='utf-8'), raw)

    def test_invalid_token_never_falls_back_or_exposes_contents(self):
        for raw in ('invalid-' + SECRET, '[]', '{}',
                    json.dumps(dict(app_key=123, refresh_token=SECRET)),
                    json.dumps(dict(app_key=SECRET, refresh_token='')), 'x' * 16385):
            with self.subTest(raw=raw[:10]), patch('core.beat_cloud.DropboxTransport.from_env') as env:
                self.path.write_text(raw, encoding='utf-8')
                with self.assertRaises(CloudError) as caught:
                    local_transport(self.path)
                self.assertNotIn(SECRET, str(caught.exception))
                env.assert_not_called()

    def test_client_failure_is_sanitized(self):
        self.path.write_text(json.dumps(dict(app_key=SECRET, refresh_token=SECRET)), encoding='utf-8')
        with patch('dropbox.Dropbox', side_effect=RuntimeError(SECRET)):
            with self.assertRaises(CloudError) as caught:
                local_transport(self.path)
        self.assertNotIn(SECRET, str(caught.exception))

    def test_navigation_pages_and_relative_app_paths(self):
        transport = BrowseTransport()
        transport.pages = [SimpleNamespace(entries=[folder('/Art/trap')], has_more=True, cursor='next'),
                           SimpleNamespace(entries=[file('/Art/thumb.png')], has_more=False)]
        rows = PanelCloud(transport).list_folder('/Art', Event())
        self.assertEqual([row['path'] for row in rows], ['/Art/trap', '/Art/thumb.png'])
        self.assertFalse(transport.calls[0][1]['recursive'])
        self.assertEqual(transport.calls[-1], 'next')

    def test_page_and_entry_limits_no_partial_results(self):
        for entries in ([], [folder('/Art')] * 2001):
            transport = BrowseTransport()
            transport.pages = [SimpleNamespace(entries=entries, has_more=True, cursor='next')]
            with self.assertRaises(CloudError):
                PanelCloud(transport).list_folder('', Event())
            self.assertLessEqual(len(transport.calls), 10)

    def test_deadline_and_non_child_paths_rejected(self):
        transport = BrowseTransport()
        with patch('core.beat_panel_cloud.time.monotonic', side_effect=[0, 121]):
            with self.assertRaises(CloudError):
                PanelCloud(transport).list_folder('', Event())
        transport.pages = [SimpleNamespace(entries=[folder('/Other/trap')], has_more=False)]
        with self.assertRaises(CloudError):
            PanelCloud(transport).list_folder('/Art', Event())

    def test_cancel_stops_next_page(self):
        transport, event = BrowseTransport(), Event()
        transport.pages[0].has_more = True
        transport.pages[0].cursor = 'next'
        def call(fn):
            result = fn()
            event.set()
            return result
        transport._call = call
        with self.assertRaises(Cancelled):
            PanelCloud(transport).list_folder('', event)
        self.assertEqual(len(transport.calls), 1)

    def test_secret_in_errors_is_sanitized(self):
        transport = BrowseTransport()
        transport._call = lambda fn: (_ for _ in ()).throw(CloudError(SECRET))
        with self.assertRaises(CloudError) as caught:
            PanelCloud(transport).list_folder('', Event())
        self.assertNotIn(SECRET, str(caught.exception))
        memory = MemoryDropbox()
        for operation, fn in [('read', lambda: PanelCloud(memory).read_config(Event())),
                              ('write', lambda: PanelCloud(memory).save_config({}, None, Event()))]:
            memory.faults = [(operation, CloudError(SECRET))]
            with self.assertRaises(CloudError) as caught:
                fn()
            self.assertNotIn(SECRET, str(caught.exception))

    def test_config_creation_and_cas_conflict_never_modify_state(self):
        memory = MemoryDropbox()
        memory.files['/type-beats/state.json'] = (b'opaque-state-do-not-rebuild', 'state-rev')
        original = memory.files['/type-beats/state.json']
        service = PanelCloud(memory)
        config, rev = service.read_config(Event())
        self.assertIsNone(rev)
        first = service.save_config(config, rev, Event())
        config['beatstars_profile_url'] = 'https://www.beatstars.com/example'
        newer = service.save_config(config, first, Event())
        for stale in (None, first):
            with self.assertRaises(Conflict):
                service.save_config({}, stale, Event())
        self.assertEqual(memory.files['/type-beats/config.json'][1], newer)
        self.assertEqual(memory.files['/type-beats/state.json'], original)
        self.assertTrue(all(call[1] == '/type-beats/config.json' for call in memory.calls))

    def test_absent_state_stays_absent(self):
        memory = MemoryDropbox()
        service = PanelCloud(memory)
        config, rev = service.read_config(Event())
        service.save_config(config, rev, Event())
        with self.assertRaises(CloudError):
            load_state(Event(), memory)
        self.assertNotIn('/type-beats/state.json', memory.files)

    def test_canceled_save_does_not_write(self):
        event, memory = Event(), MemoryDropbox()
        event.set()
        with self.assertRaises(Cancelled):
            PanelCloud(memory).save_config({}, None, event)
        self.assertEqual(memory.calls, [])

    def test_invalid_remote_config_is_never_replaced(self):
        memory = MemoryDropbox()
        original = (b'{invalid-private-document', 'bad-rev')
        memory.files['/type-beats/config.json'] = original
        with self.assertRaises(CloudError):
            PanelCloud(memory).read_config(Event())
        self.assertEqual(memory.files['/type-beats/config.json'], original)
        self.assertEqual(memory.calls, [('read', '/type-beats/config.json')])


class RemotePanelTests(unittest.TestCase):
    setUp = panel_tests.PanelTests.setUp
    cleanup_panel = panel_tests.PanelTests.cleanup_panel
    configure = panel_tests.PanelTests.configure

    def test_selection_persists_local_without_credentials(self):
        self.configure()
        self.panel._apply_remote_selection('videos', '/Videos')
        self.panel._apply_remote_selection('thumbnail', '/Art/thumb.png')
        self.panel._apply_remote_selection('images', '/Art/trap', 'trap')
        self.panel._apply_remote_selection('images', '/Art/new', 'trap')
        self.panel.save()
        config = json.loads(self.path.read_text(encoding='utf-8'))['beat_automation']['channels'][0]
        self.assertEqual(config['visual']['videos_folder'], '/Videos')
        self.assertEqual(config['visual']['thumbnail_path'], '/Art/thumb.png')
        self.assertEqual(config['dropbox_images'], {'trap': '/Art/new'})
        self.assertNotIn(SECRET, self.path.read_text(encoding='utf-8'))

    def test_save_and_publish_keeps_local_draft_when_remote_exists(self):
        self.configure()
        memory = MemoryDropbox()
        self.panel.cloud_provider = lambda: memory
        stale = self.panel.draft()
        stale['channels'][0]['tags'] = ['stale-remote']
        BeatCloud(memory).write('config', stale, None)
        self.panel.tags.setText('local-draft')
        self.panel.save_and_publish()
        for _ in range(5):
            pump(lambda: self.panel.task is None)
            if '/type-beats/config.json' in memory.files:
                remote = json.loads(memory.files['/type-beats/config.json'][0].decode())
                if remote['channels'][0]['tags'] == ['local-draft']:
                    break
        self.assertEqual(self.panel.tags.text(), 'local-draft')
        remote = json.loads(memory.files['/type-beats/config.json'][0].decode())
        self.assertEqual(remote['channels'][0]['tags'], ['local-draft'])
        saved = json.loads(self.path.read_text(encoding='utf-8'))['beat_automation']
        self.assertEqual(saved['channels'][0]['tags'], ['local-draft'])

    def test_save_and_publish_chains_local_cas_and_conflict(self):
        self.configure()
        memory = MemoryDropbox()
        self.panel.cloud_provider = lambda: memory
        local_before = self.path.read_bytes()
        self.panel.tags.setText('published-tag')
        self.panel.save_and_publish()
        for _ in range(5):
            pump(lambda: self.panel.task is None)
            if self.panel.cloud_loaded:
                break
        self.assertTrue(self.panel.cloud_loaded)
        self.assertNotEqual(self.path.read_bytes(), local_before)
        remote = json.loads(memory.files['/type-beats/config.json'][0].decode())
        self.assertEqual(remote['channels'][0]['tags'], ['published-tag'])
        BeatCloud(memory).write('config', self.panel.draft(), self.panel.cloud_rev)
        self.panel.tags.setText('keep-draft')
        self.panel.save_and_publish()
        for _ in range(5):
            pump(lambda: self.panel.task is None)
            if 'Conflicto' in self.panel.status.text():
                break
        self.assertIn('Conflicto', self.panel.status.text())
        self.assertFalse(self.panel.cloud_loaded)
        self.assertEqual(self.panel.tags.text(), 'keep-draft')
        self.assertEqual(json.loads(memory.files['/type-beats/config.json'][0].decode())['channels'][0]['tags'],
                         ['published-tag'])

    def test_panel_cas_requires_reload_and_preserves_local_and_state(self):
        self.configure()
        memory = MemoryDropbox()
        self.panel.cloud_provider = lambda: memory
        local_before = self.path.read_bytes()
        self.panel.save_cloud_config()
        self.assertIsNone(self.panel.task)
        self.assertIn('Recargá', self.panel.status.text())
        self.panel.reload_cloud_config()
        pump(lambda: self.panel.task is None)
        self.panel.save_cloud_config()
        pump(lambda: self.panel.task is None)
        self.assertTrue(self.panel.cloud_loaded)
        BeatCloud(memory).write('config', self.panel.draft(), self.panel.cloud_rev)
        self.panel.tags.setText('keep-my-draft')
        self.panel.save_cloud_config()
        pump(lambda: self.panel.task is None)
        self.assertIn('Conflicto', self.panel.status.text())
        self.assertFalse(self.panel.cloud_loaded)
        self.assertEqual(self.panel.tags.text(), 'keep-my-draft')
        self.assertEqual(self.path.read_bytes(), local_before)
        self.assertNotIn('/type-beats/state.json', memory.files)
        self.panel.reload_cloud_config()
        pump(lambda: self.panel.task is None)
        self.assertTrue(self.panel.cloud_loaded)

    def test_picker_folder_file_selection_and_worker_thread(self):
        transport = BrowseTransport()
        picker = DropboxPicker(file=False, provider=lambda: transport)
        pump(lambda: picker.task is None)
        self.assertNotEqual(transport.calls[0][2], get_ident())
        self.assertFalse(picker.choose.isEnabled())  # root is navigation only
        transport.pages = [SimpleNamespace(entries=[], has_more=False)]
        picker.enter(picker.entries.item(0))
        pump(lambda: picker.task is None)
        picker.select()
        self.assertEqual(picker.selected_path, '/Art')
        picker.deleteLater()
        transport.pages = [SimpleNamespace(entries=[folder('/Art'), file('/thumb.png'), file('/audio.mp3')], has_more=False)]
        picker = DropboxPicker(file=True, provider=lambda: transport)
        pump(lambda: picker.task is None)
        self.assertEqual(picker.entries.count(), 2)
        picker.entries.setCurrentRow(0)
        self.assertFalse(picker.choose.isEnabled())
        picker.entries.setCurrentRow(1)
        picker.select()
        self.assertEqual(picker.selected_path, '/thumb.png')
        picker.deleteLater()

    def test_picker_close_defers_and_discards_results(self):
        entered, release = Event(), Event()
        transport = BrowseTransport()
        def blocked(fn):
            entered.set()
            release.wait(2)
            return fn()
        transport._call = blocked
        picker = DropboxPicker(provider=lambda: transport)
        pump(entered.is_set)
        picker.reject()
        self.assertTrue(picker.close_pending)
        self.assertIsNotNone(picker.task)
        release.set()
        pump(lambda: picker.task is None)
        self.assertIsNone(picker.selected_path)
        self.assertEqual(picker.entries.count(), 0)
        picker.deleteLater()

    def test_lost_save_response_requires_reload_without_retry(self):
        self.configure()
        memory = MemoryDropbox()
        self.panel.cloud_provider = lambda: memory
        self.panel.reload_cloud_config()
        pump(lambda: self.panel.task is None)
        memory.faults = [('after_write', CloudError(SECRET))]
        self.panel.save_cloud_config()
        pump(lambda: self.panel.task is None)
        self.assertFalse(self.panel.cloud_loaded)
        self.assertNotIn(SECRET, self.panel.status.text())
        self.assertIn('Recargá', self.panel.status.text())
        self.assertEqual(len([call for call in memory.calls if call[0] == 'write']), 1)
        self.panel.save_cloud_config()
        self.assertIsNone(self.panel.task)
        self.assertNotIn('/type-beats/state.json', memory.files)

    def test_config_read_write_and_state_read_are_off_ui_thread(self):
        self.configure()
        memory, threads = MemoryDropbox(), []
        class ThreadTransport:
            def read(self, path):
                threads.append(get_ident())
                return memory.read(path)
            def write(self, path, payload, rev):
                threads.append(get_ident())
                return memory.write(path, payload, rev)
        self.panel.cloud_provider = ThreadTransport
        self.panel.reload_cloud_config()
        pump(lambda: self.panel.task is None)
        self.panel.save_cloud_config()
        pump(lambda: self.panel.task is None)
        self.panel.read_state()
        pump(lambda: self.panel.task is None)
        self.assertEqual(len(threads), 3)
        self.assertTrue(all(thread != get_ident() for thread in threads))
        self.assertNotIn('/type-beats/state.json', memory.files)

    def test_cancelled_config_reload_preserves_draft(self):
        self.configure()
        entered, release = Event(), Event()
        memory = MemoryDropbox()
        class BlockingTransport:
            def read(self, path):
                entered.set()
                release.wait(2)
                return memory.read(path)
        self.panel.cloud_provider = BlockingTransport
        self.panel.reload_cloud_config()
        pump(entered.is_set)
        self.panel.cancel()
        release.set()
        pump(lambda: self.panel.task is None)
        self.assertFalse(self.panel.cloud_loaded)
        self.assertEqual(self.panel.tags.text(), 'trap, dark')
        self.assertTrue(all(call[0] == 'read' for call in memory.calls))


if __name__ == '__main__':
    unittest.main()
