"""Qt acquisition workflow using a fake backend, without network or real settings."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import Qt, QThread, QTimer
from PyQt5.QtGui import QCloseEvent, QFont, QFontDatabase
from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtTest import QTest

from core import channel_profile as cp, manual_render as mr
from core.beat_http import BeatError
from core.beat_source import Track
from core.local_view import LocalView
from core.manual_beatstars import BatchResult, Candidate, SearchResult, filter_tags
from core.manual_beatstars_dialog import ManualBeatStarsDialog, initial_preferences
from core.manual_beatstars_store import HistoryError
from ui_theme import APPLICATION_STYLESHEET

APP = QApplication.instance() or QApplication([])
# Qt's Windows offscreen plugin may expose no system fonts, even outside sandbox.
# Load the actual UI font for meaningful geometry and screenshot checks.
if not QFontDatabase().families() and os.name == 'nt':
    font_id = QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/segoeui.ttf'))
    if font_id >= 0:
        APP.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
PROFILE = 'https://www.beatstars.com/fixtureproducer'


def pump_until(predicate, seconds=5):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        APP.processEvents()
        time.sleep(.005)
    APP.processEvents()
    if not predicate():
        raise AssertionError('Qt operation did not settle')


def candidate(number, downloaded=False):
    track = Track(f'TK{number}', f'Fixture {number}', f'https://www.beatstars.com/beat/fixture-{number}',
                  ('trap', 'dark') if number % 2 else ('trap',), 2,
                  {'provider': 'beatstars', 'track_id': f'TK{number}', 'v2_id': str(number)})
    return Candidate(track, downloaded)


class FakeBackend:
    def __init__(self):
        self.candidates = [candidate(101), candidate(102), candidate(103, downloaded=True), candidate(104)]
        self.calls = []
        self.threads = []
        self.gate = Event()
        self.gate.set()
        self.started = Event()
        self.first_completed = Event()
        self.pause_after_first = False
        self.search_error = None
        self.errors = {}
        self.fatal_after_first = False

    def factory(self, cancelled):
        backend = self
        class Service:
            def search(self, **kwargs):
                backend.calls.append(('search', kwargs))
                backend.threads.append(QThread.currentThread())
                backend.started.set()
                backend.gate.wait(4)
                if backend.search_error:
                    raise backend.search_error
                tracks = set(t.id for t in filter_tags([c.track for c in backend.candidates], kwargs['tags'], kwargs['match']))
                return SearchResult(kwargs['profile_url'], 'MR100', tuple(c for c in backend.candidates
                    if c.track.id in tracks and (not c.downloaded or kwargs['include_downloaded'])))

            def download(self, search, track_ids, destination, include_downloaded, progress):
                backend.calls.append(('download', dict(destination=destination, track_ids=track_ids,
                                                        include_downloaded=include_downloaded)))
                backend.threads.append(QThread.currentThread())
                result = BatchResult()
                for done, tid in enumerate(track_ids):
                    if cancelled():
                        result.cancelled = True
                        break
                    progress(done, len(track_ids), tid)
                    if tid in backend.errors:
                        result.errors.append((tid, backend.errors[tid]))
                        continue
                    folder = Path(destination)
                    folder.mkdir(parents=True, exist_ok=True)
                    path = folder / f'{tid} - Fixture.m4a'
                    path.write_bytes(b'complete fake audio')
                    Path(str(path) + '.beatstars.json').write_text(json.dumps({'track_id': tid}))
                    Path(str(path) + '.beatstars.txt').write_text('https://www.beatstars.com/beat/fixture-' + tid[2:])
                    result.downloads.append(path)
                    backend.first_completed.set()
                    if backend.fatal_after_first:
                        error = HistoryError('history_write_failed')
                        error.result = result
                        raise error
                    if backend.pause_after_first:
                        backend.gate.wait(4)
                return result
        return Service()


class DialogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.backend = FakeBackend()
        self.dialogs = []
        self.preferences = initial_preferences({}, self.root / 'absent.json')
        self.preferences['profile_url'] = PROFILE
        self.parent = QWidget()
        self.parent.setStyleSheet(APPLICATION_STYLESHEET)

    def tearDown(self):
        self.backend.gate.set()
        for dialog in self.dialogs:
            dialog.reject()
            pump_until(lambda: dialog.task is None)
            dialog.deleteLater()
        APP.processEvents()
        self.parent.deleteLater()
        self.tmp.cleanup()

    def dialog(self, **overrides):
        prefs = dict(self.preferences, **overrides)
        dialog = ManualBeatStarsDialog('Canal', self.root / 'entrada/Canal', prefs,
                                      self.parent, service_factory=self.backend.factory)
        dialog.show()
        self.dialogs.append(dialog)
        APP.processEvents()
        return dialog

    def search(self, dialog):
        dialog.search_button.click()
        pump_until(lambda: dialog.task is None)

    def test_defaults_and_initial_profile_from_config_without_changing_it(self):
        config = self.root / 'app_config.json'
        config.write_text(json.dumps({'beat_automation': {'beatstars_profile_url': PROFILE}}))
        before = config.read_bytes()
        prefs = initial_preferences({}, config)
        self.assertEqual((prefs['profile_url'], prefs['quantity'], prefs['match']), (PROFILE, 10, 'any'))
        self.assertFalse(prefs['include_downloaded'])
        remembered = initial_preferences({'beatstars': {'profile_url': '', 'quantity': 500}}, config)
        self.assertEqual((remembered['profile_url'], remembered['quantity']), ('', 100))
        invalid = initial_preferences({'beatstars': ['bad']}, config)
        self.assertEqual(invalid['profile_url'], PROFILE)
        self.assertEqual(config.read_bytes(), before)

    def test_search_preselects_quantity_in_catalogue_order_and_shows_links(self):
        dialog = self.dialog(quantity=2)
        self.search(dialog)
        self.assertEqual(dialog.table.rowCount(), 3)
        self.assertEqual(dialog.selected_ids(), ['TK101', 'TK102'])
        self.assertEqual(dialog.table.item(0, 3).text(), candidate(101).track.url)
        self.assertIn('3 beats encontrados', dialog.selection_label.text())
        self.assertTrue(dialog.download_button.isEnabled())
        self.assertTrue(all(thread is not APP.thread() for thread in self.backend.threads))

    def test_selection_cap_and_quantity_changes(self):
        dialog = self.dialog(quantity=1)
        self.search(dialog)
        dialog.table.item(1, 0).setCheckState(Qt.Checked)
        self.assertEqual(dialog.selected_ids(), ['TK101'])
        self.assertIn('hasta 1 beats', dialog.status.text())
        dialog.table.item(0, 0).setCheckState(Qt.Unchecked)
        self.assertFalse(dialog.download_button.isEnabled())
        dialog.table.item(1, 0).setCheckState(Qt.Checked)
        self.assertEqual(dialog.selected_ids(), ['TK102'])
        dialog.quantity.setValue(100)
        self.assertEqual(dialog.selected_ids(), ['TK101', 'TK102', 'TK104'])

    def test_filters_invalidate_results_and_all_mode_matches(self):
        dialog = self.dialog()
        self.search(dialog)
        dialog.tags_edit.setText('TRAP, dark')
        dialog.match.setCurrentIndex(1)
        self.assertIsNone(dialog.search_result)
        self.assertFalse(dialog.download_button.isEnabled())
        self.search(dialog)
        self.assertEqual(dialog.selected_ids(), ['TK101'])
        dialog.include_downloaded.setChecked(True)
        self.search(dialog)
        self.assertEqual(dialog.selected_ids(), ['TK101', 'TK103'])
        self.assertEqual(dialog.table.item(1, 4).text(), 'Ya descargado')

    def test_empty_results_are_explained_without_enabling_download(self):
        self.backend.candidates = []
        dialog = self.dialog()
        self.search(dialog)
        self.assertIn('No hay beats disponibles', dialog.status.text())
        self.assertFalse(dialog.download_button.isEnabled())

    def test_invalid_profile_or_tags_never_start_backend(self):
        dialog = self.dialog(profile_url='https://evil.example/profile')
        self.search(dialog)
        self.assertFalse(self.backend.calls)
        self.assertIn('HTTPS de beatstars.com', dialog.status.text())
        dialog.profile_edit.setText(PROFILE)
        dialog.tags_edit.setText('x' * 101)
        self.search(dialog)
        self.assertIn('hasta 40 tags', dialog.status.text())
        self.assertFalse(self.backend.calls)

    def test_partial_download_emits_only_complete_paths_and_explains_errors(self):
        self.backend.errors['TK102'] = 'preview_unavailable'
        dialog = self.dialog()
        ready = []
        dialog.packages_ready.connect(ready.extend)
        self.search(dialog)
        dialog.download_button.click()
        pump_until(lambda: dialog.task is None)
        self.assertEqual(len(ready), 2)
        self.assertTrue(all(Path(p).exists() for p in ready))
        self.assertIn('2 descargados, 1 con error', dialog.status.text())
        self.assertIn('preview público', dialog.status.text())
        self.assertEqual(dialog.table.item(0, 4).text(), 'Descargado')
        self.assertFalse(dialog.table.item(0, 0).flags() & Qt.ItemIsEnabled)
        self.assertEqual(dialog.selected_ids(), ['TK102'])
        self.assertTrue(all(thread is not APP.thread() for thread in self.backend.threads))
        dialog.resize(650, 500)
        APP.processEvents()
        for field in (dialog.profile_edit, dialog.tags_edit, dialog.quantity, dialog.match):
            self.assertGreaterEqual(field.height(), field.minimumSizeHint().height())

    def test_explicit_repeat_is_forwarded_and_keeps_success_selectable(self):
        dialog = self.dialog(include_downloaded=True, quantity=1)
        self.search(dialog)
        dialog.download_button.click()
        pump_until(lambda: dialog.task is None)
        self.assertTrue(self.backend.calls[-1][1]['include_downloaded'])
        self.assertTrue(dialog.table.item(0, 0).flags() & Qt.ItemIsEnabled)
        self.assertEqual(dialog.selected_ids(), [])

    def test_fatal_history_error_retains_successes_and_stops(self):
        self.backend.fatal_after_first = True
        dialog = self.dialog()
        ready = []
        dialog.packages_ready.connect(ready.extend)
        self.search(dialog)
        dialog.download_button.click()
        pump_until(lambda: dialog.task is None)
        self.assertEqual(len(ready), 1)
        self.assertIn('No se pudo guardar el historial', dialog.status.text())
        self.assertEqual(dialog.table.item(0, 4).text(), 'Descargado')

    def test_search_failure_is_translated_and_does_not_leak_raw_exception(self):
        self.backend.search_error = RuntimeError('PRIVATE PATH OR SECRET')
        dialog = self.dialog()
        self.search(dialog)
        self.assertNotIn('PRIVATE', dialog.status.text())
        self.assertIn('no pudo completarse', dialog.status.text())
        self.assertFalse(dialog.download_button.isEnabled())

    def test_worker_keeps_event_loop_responsive_and_cancel_discards_late_search(self):
        self.backend.gate.clear()
        dialog = self.dialog()
        dialog.search()
        pump_until(self.backend.started.is_set)
        ticks = []
        QTimer.singleShot(0, lambda: ticks.append(True))
        pump_until(lambda: bool(ticks))
        self.assertFalse(dialog.profile_edit.isEnabled())
        self.assertFalse(dialog.search_button.isEnabled())
        dialog.cancel_button.click()
        self.assertFalse(dialog.cancel_button.isEnabled())
        self.backend.gate.set()
        pump_until(lambda: dialog.task is None)
        self.assertIsNone(dialog.search_result)
        self.assertIn('cancelada', dialog.status.text())
        self.assertTrue(dialog.search_button.isEnabled())

    def test_close_search_waits_for_thread_exit(self):
        self.backend.gate.clear()
        dialog = self.dialog()
        closed = []
        dialog.finished.connect(closed.append)
        dialog.search()
        pump_until(self.backend.started.is_set)
        dialog.close()
        self.assertTrue(dialog.isVisible())
        self.assertFalse(closed)
        self.assertIsNotNone(dialog.task)
        self.backend.gate.set()
        pump_until(lambda: bool(closed))
        self.assertIsNone(dialog.task)
        self.assertFalse(dialog.isVisible())

    def test_escape_reject_defers_and_keeps_completed_downloads(self):
        dialog = self.dialog()
        self.search(dialog)
        self.backend.pause_after_first = True
        self.backend.gate.clear()
        ready, closed = [], []
        dialog.packages_ready.connect(ready.extend)
        dialog.finished.connect(closed.append)
        dialog.download()
        pump_until(self.backend.first_completed.is_set)
        QTest.keyClick(dialog, Qt.Key_Escape)
        self.assertFalse(closed)
        self.backend.gate.set()
        pump_until(lambda: bool(closed))
        self.assertEqual(len(ready), 1)
        self.assertTrue(dialog.last_batch.cancelled)

    def test_cancel_download_keeps_dialog_open_and_completed_packages(self):
        dialog = self.dialog()
        self.search(dialog)
        self.backend.pause_after_first = True
        self.backend.gate.clear()
        ready = []
        dialog.packages_ready.connect(ready.extend)
        dialog.download()
        pump_until(self.backend.first_completed.is_set)
        dialog.cancel_button.click()
        self.backend.gate.set()
        pump_until(lambda: dialog.task is None)
        self.assertTrue(dialog.isVisible())
        self.assertEqual(len(ready), 1)
        self.assertTrue(dialog.last_batch.cancelled)
        self.assertIn('Cancelado: 1 descargados', dialog.status.text())

    def test_open_link_requires_user_action(self):
        dialog = self.dialog()
        with patch('core.manual_beatstars_dialog.QDesktopServices.openUrl') as opener:
            self.search(dialog)
            opener.assert_not_called()
            dialog._open_link(0, 1)
            opener.assert_not_called()
            dialog._open_link(0, 3)
            self.assertEqual(opener.call_args.args[0].toString(), candidate(101).track.url)

    def test_actions_fit_at_minimum_dialog_size(self):
        dialog = self.dialog()
        dialog.resize(650, 500)
        APP.processEvents()
        for button in (dialog.search_button, dialog.download_button, dialog.close_button):
            self.assertTrue(dialog.rect().contains(button.geometry()))
            self.assertGreaterEqual(button.width(), button.minimumSizeHint().width())


class LocalIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.backend = FakeBackend()
        cp.create(str(self.root / 'local'), 'Canal')
        cp.create(str(self.root / 'local'), 'Otro')
        config = self.root / 'config'
        config.mkdir()
        (config / 'app_config.json').write_text(json.dumps({'beat_automation': {'beatstars_profile_url': PROFILE}}))
        self.settings = str(config / 'manual_mode.json')
        self.view = LocalView(settings_path=self.settings, local_root=str(self.root / 'local'),
                              legacy_root=str(self.root), beatstars_service_factory=self.backend.factory)
        self.view.reload_channels(select='Canal')

    def tearDown(self):
        self.backend.gate.set()
        if self.view.beatstars_dialog is not None:
            self.view.beatstars_dialog.reject()
            pump_until(lambda: self.view.beatstars_dialog is None)
        self.view.deleteLater()
        APP.processEvents()
        self.tmp.cleanup()

    def open_and_search(self):
        self.view.btn_beatstars.click()
        dialog = self.view.beatstars_dialog
        dialog.search()
        pump_until(lambda: dialog.task is None)
        return dialog

    def test_channel_required_and_download_is_disabled_during_render(self):
        view = self.view
        self.assertTrue(view.btn_beatstars.isEnabled())  # backgrounds are not required to download
        view.worker = object()
        view._update_buttons()
        self.assertFalse(view.btn_beatstars.isEnabled())
        view.open_beatstars()
        self.assertIsNone(view.beatstars_dialog)
        view.worker = None
        view.channel_combo.clear()
        view._update_buttons()
        self.assertFalse(view.btn_beatstars.isEnabled())

    def test_completed_audio_joins_inbox_without_generating_and_preferences_survive(self):
        dialog = self.open_and_search()
        dialog.quantity.setValue(2)
        with patch.object(self.view, '_run') as render:
            dialog.download()
            pump_until(lambda: dialog.task is None)
            self.assertEqual(len(self.view.inbox), 2)
            self.assertEqual(len(self.view.beats), 2)
            self.assertFalse(self.view.dropped)
            self.assertEqual(self.view.generated, 0)
            render.assert_not_called()
        dialog.reject()
        self.assertIsNone(self.view.beatstars_dialog)
        prefs = mr.load_settings(self.settings)['beatstars']
        self.assertEqual((prefs['profile_url'], prefs['quantity']), (PROFILE, 2))
        self.view.open_beatstars()
        self.assertEqual(self.view.beatstars_dialog.quantity.value(), 2)

    def test_dialog_freezes_destination_and_blocks_manual_actions(self):
        dialog = self.open_and_search()
        self.assertFalse(self.view.channel_combo.isEnabled())
        self.assertFalse(self.view.btn_settings.isEnabled())
        self.assertFalse(self.view.btn_add.isEnabled())
        self.assertFalse(self.view.btn_generate.isEnabled())
        with patch.object(self.view, '_run') as render:
            self.view.start()
            self.view.start_all()
            render.assert_not_called()
        # Even a programmatic channel change cannot redirect the frozen download.
        self.view.channel_combo.setCurrentText('Otro')
        dialog.download()
        pump_until(lambda: dialog.task is None)
        self.assertEqual(Path(self.backend.calls[-1][1]['destination']), self.root / 'local/entrada/Canal')
        self.assertEqual(self.view.beats, [])
        self.assertEqual(self.view.other_inbox, {'Canal': 3})
        dialog.reject()
        self.assertTrue(self.view.channel_combo.isEnabled())

    def test_shutdown_during_operation_is_nonblocking_and_retries_only_after_finish(self):
        self.view.open_beatstars()
        dialog = self.view.beatstars_dialog
        self.backend.gate.clear()
        dialog.search()
        pump_until(self.backend.started.is_set)
        ready = []
        self.view.shutdown_ready.connect(lambda: ready.append(True))
        started = time.monotonic()
        self.assertFalse(self.view.shutdown())
        self.assertLess(time.monotonic() - started, .5)
        self.assertFalse(ready)
        self.assertIsNotNone(dialog.task)
        self.backend.gate.set()
        pump_until(lambda: bool(ready))
        self.assertIsNone(self.view.beatstars_dialog)
        self.assertTrue(self.view.shutdown())

    def test_shutdown_idle_dialog_does_not_emit_reentrant_close(self):
        self.view.open_beatstars()
        ready = []
        self.view.shutdown_ready.connect(lambda: ready.append(True))
        self.assertTrue(self.view.shutdown())
        self.assertIsNone(self.view.beatstars_dialog)
        self.assertFalse(ready)

    def test_local_actions_scroll_at_small_sizes_without_forcing_window_growth(self):
        view = self.view
        view.setStyleSheet(APPLICATION_STYLESHEET)
        view.resize(580, 570)
        view.show()
        for _ in range(3):
            APP.processEvents()
        self.assertEqual((view.width(), view.height()), (580, 570))
        self.assertGreater(view.scroll.verticalScrollBar().maximum(), 0)
        self.assertEqual(view.scroll.horizontalScrollBar().maximum(), 0)
        self.assertGreaterEqual(view.btn_beatstars.width(), view.btn_beatstars.minimumSizeHint().width())
        view.scroll.ensureWidgetVisible(view.btn_beatstars)
        APP.processEvents()
        self.assertTrue(view.btn_beatstars.isVisible())

    def test_actual_engine_with_fake_http_excludes_download_after_reopening(self):
        from test_manual_beatstars import Source, Resolver, HLS, Tools
        from core.manual_beatstars import ManualBeatStars
        from core.manual_beatstars_store import HistoryStore
        def factory(cancelled):
            return ManualBeatStars(store=HistoryStore(self.root / 'history.json'), source=Source(),
                                   resolver=Resolver(), http=HLS(), tools=Tools(), cancelled=cancelled)
        self.view._beatstars_service_factory = factory
        dialog = self.open_and_search()
        dialog.quantity.setValue(1)
        dialog.download()
        pump_until(lambda: dialog.task is None)
        self.assertEqual(len(self.view.beats), 1)
        dialog.reject()
        # A new dialog and service instance use the same installation history.
        dialog = self.open_and_search()
        self.assertEqual(dialog.selected_ids(), ['TK102'])
        self.assertEqual(dialog.table.rowCount(), 1)

    def test_main_window_ignores_close_while_local_download_is_running(self):
        from core.main_window import MainWindow
        window = SimpleNamespace(beat_panel=SimpleNamespace(task=None), local_view=Mock(),
                                 loop_kit_panel=Mock(), assistant=Mock())
        window.local_view.shutdown.return_value = False
        event = QCloseEvent()
        MainWindow.closeEvent(window, event)
        self.assertFalse(event.isAccepted())
        window.loop_kit_panel.shutdown.assert_not_called()
        window.assistant.shutdown.assert_not_called()


if __name__ == '__main__':
    unittest.main()
