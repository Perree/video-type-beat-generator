"""Metadata identity, upload text, archiving and failure recovery without network."""
import errno
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import bulk_queue as bq, channel_profile as cp, manual_render as mr
from core.manual_beatstars_files import MetadataError, move_package, read_metadata
from core.manual_beatstars_store import HistoryStore, LINK, SIDECAR, digest, metadata_bytes

URL = 'https://www.beatstars.com/beat/fixture-101'
TITLE = '(BEAT PRO-527) [juice wrld, sad] Night - 140bpm - key A Minor'


def write_package(audio, title=TITLE, track_id='TK101'):
    audio = Path(audio)
    audio.parent.mkdir(parents=True, exist_ok=True)
    if not audio.exists():
        audio.write_bytes(b'fixture-audio')
    metadata = dict(version=1, member_id='MR100', track_id=track_id, title=title,
                    tags=['juice wrld', 'sad'], url='https://www.beatstars.com/beat/fixture-' + track_id[2:],
                    downloaded_at='2026-10-24T10:00:00+00:00', size=audio.stat().st_size, sha256=digest(audio))
    Path(str(audio) + SIDECAR).write_bytes(metadata_bytes(metadata))
    Path(str(audio) + LINK).write_text(metadata['url'] + '\n', encoding='utf-8', newline='')
    return metadata


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.audio = self.root / 'entrada/Canal/TK101 - truncated.m4a'
        self.done = self.audio.parent / 'hechos'

    def assert_package(self, audio, metadata):
        self.assertEqual(read_metadata(audio, verify=True), metadata)
        self.assertEqual(Path(str(audio) + LINK).read_text(), metadata['url'] + '\n')

    def test_absent_metadata_keeps_local_audio_contract(self):
        self.audio.parent.mkdir(parents=True)
        self.audio.write_bytes(b'local')
        self.assertIsNone(read_metadata(self.audio, verify=True))
        self.assertEqual(mr.beat_name(self.audio), 'TK101 - truncated')
        expected = 'TÍTULO\nT\n\nDESCRIPCIÓN\nDesc\n\nTAGS\na, b\n'
        self.assertEqual(mr.upload_text('T', 'Desc\n', ['a', 'b']), expected)

    def test_valid_metadata_is_bound_to_audio_and_not_filename(self):
        metadata = write_package(self.audio)
        self.assert_package(self.audio, metadata)
        self.assertEqual(mr.beat_name(self.audio, metadata), TITLE)
        renamed = self.audio.parent / 'renamed by hand.m4a'
        self.audio.rename(renamed)
        for suffix in (SIDECAR, LINK):
            Path(str(self.audio) + suffix).rename(str(renamed) + suffix)
        self.assert_package(renamed, metadata)

    def test_same_size_modified_audio_is_rejected_only_by_worker_hash_check(self):
        metadata = write_package(self.audio)
        self.audio.write_bytes(b'x' * metadata['size'])
        self.assertEqual(read_metadata(self.audio), metadata)
        with self.assertRaisesRegex(MetadataError, 'no coincide'):
            read_metadata(self.audio, verify=True)

    def test_invalid_json_schema_or_url_never_supplies_a_link(self):
        metadata = write_package(self.audio)
        bad = [b'{broken', b'x' * (16 * 1024 + 1), json.dumps({}).encode(),
               metadata_bytes(dict(metadata, version=2)),
               metadata_bytes(dict(metadata, url='https://evil.example/beat/fixture-101')),
               metadata_bytes(dict(metadata, track_id='TK999'))]
        for raw in bad:
            with self.subTest(raw=raw[:35]):
                Path(str(self.audio) + SIDECAR).write_bytes(raw)
                with self.assertRaises(MetadataError):
                    read_metadata(self.audio)

    def test_link_without_json_reports_broken_package_but_missing_link_can_use_json(self):
        metadata = write_package(self.audio)
        Path(str(self.audio) + LINK).unlink()
        self.assertEqual(read_metadata(self.audio, verify=True), metadata)
        Path(str(self.audio) + SIDECAR).unlink()
        Path(str(self.audio) + LINK).write_text(URL)
        with self.assertRaisesRegex(MetadataError, 'Falta la metadata'):
            read_metadata(self.audio)

    def test_move_all_components_to_same_final_basename(self):
        metadata = write_package(self.audio)
        moved = bq.mark_done(str(self.root), 'Canal', str(self.audio))
        self.assertEqual(Path(moved), self.done / self.audio.name)
        self.assert_package(moved, metadata)
        for suffix in ('', SIDECAR, LINK):
            self.assertFalse(Path(str(self.audio) + suffix).exists())
        self.assertEqual(bq.scan(str(self.root))[0], [])

    def test_audio_or_sidecar_only_collision_preserves_both_packages(self):
        metadata = write_package(self.audio)
        self.done.mkdir()
        # Reserve three basenames using different components, including orphan sidecars.
        (self.done / self.audio.name).write_bytes(b'existing audio')
        second = self.done / f'{self.audio.stem} (2){self.audio.suffix}'
        third = self.done / f'{self.audio.stem} (3){self.audio.suffix}'
        Path(str(second) + SIDECAR).write_text('existing metadata')
        Path(str(third) + LINK).write_text('existing link')
        moved = Path(move_package(self.audio, self.done))
        self.assertEqual(moved.name, f'{self.audio.stem} (4).m4a')
        self.assert_package(moved, metadata)
        self.assertEqual((self.done / self.audio.name).read_bytes(), b'existing audio')
        self.assertEqual(Path(str(second) + SIDECAR).read_text(), 'existing metadata')
        self.assertEqual(Path(str(third) + LINK).read_text(), 'existing link')

    def test_each_move_failure_rolls_back_without_losing_association(self):
        from core.manual_beatstars_files import _move_one
        metadata = write_package(self.audio)
        for fail_at in (1, 2, 3):
            calls = []
            def move(source, final):
                calls.append(1)
                if len(calls) == fail_at:
                    raise PermissionError('busy file')
                _move_one(source, final)
            with patch('core.manual_beatstars_files._move_one', side_effect=move):
                with self.assertRaises(OSError):
                    move_package(self.audio, self.done)
            self.assert_package(self.audio, metadata)
            self.assertEqual(list(self.done.iterdir()), [])

    def test_rollback_failure_reports_split_package_without_deleting_files(self):
        from core.manual_beatstars_files import _move_one
        write_package(self.audio)
        calls = []
        def move(source, final):
            calls.append(1)
            if len(calls) in (2, 3):
                raise PermissionError('busy file')
            _move_one(source, final)
        with patch('core.manual_beatstars_files._move_one', side_effect=move):
            with self.assertRaisesRegex(OSError, 'ni revertir'):
                move_package(self.audio, self.done)
        self.assertTrue(self.audio.exists())
        self.assertTrue(Path(str(self.audio) + LINK).exists())
        self.assertTrue(Path(str(self.done / self.audio.name) + SIDECAR).exists())

    def test_concurrent_collision_is_not_overwritten_or_deleted(self):
        from core.manual_beatstars_files import _move_one
        metadata = write_package(self.audio)
        external = self.done / (self.audio.name + LINK)
        def move(source, final):
            if final == external:
                external.write_text('external link')
            _move_one(source, final)
        with patch('core.manual_beatstars_files._move_one', side_effect=move):
            with self.assertRaises(OSError):
                move_package(self.audio, self.done)
        self.assert_package(self.audio, metadata)
        self.assertEqual(external.read_text(), 'external link')

    def test_missing_audio_restores_sidecars_after_failed_move(self):
        write_package(self.audio)
        self.audio.unlink()
        with self.assertRaises(OSError):
            move_package(self.audio, self.done)
        self.assertTrue(Path(str(self.audio) + SIDECAR).exists())
        self.assertTrue(Path(str(self.audio) + LINK).exists())
        self.assertEqual(list(self.done.iterdir()), [])

    def test_local_audio_without_sidecars_still_moves(self):
        self.audio.parent.mkdir(parents=True)
        self.audio.write_bytes(b'local audio')
        moved = move_package(self.audio, self.done)
        self.assertEqual(Path(moved).read_bytes(), b'local audio')
        self.assertEqual(len(list(self.done.iterdir())), 1)

    def test_cross_volume_move_copies_complete_package_before_removing_sources(self):
        from core.manual_beatstars_files import _move_same_volume
        metadata = write_package(self.audio)
        def different_volume(source, target):
            if source.parent == self.audio.parent:
                raise OSError(errno.EXDEV, 'different volume')
            _move_same_volume(source, target)
        with patch('core.manual_beatstars_files._move_same_volume', side_effect=different_volume):
            moved = move_package(self.audio, self.done)
        self.assert_package(moved, metadata)
        self.assertFalse(self.audio.exists())
        self.assertFalse(list(self.done.glob('*.part')))

    def test_cross_volume_copy_failure_keeps_original_and_removes_own_temporary(self):
        metadata = write_package(self.audio)
        def bad_copy(source, target):
            target.write_bytes(b'partial')
            raise OSError('copy failure')
        with patch('core.manual_beatstars_files._move_same_volume', side_effect=OSError(errno.EXDEV, 'different volume')), \
                patch('core.manual_beatstars_files.shutil.copy2', side_effect=bad_copy):
            with self.assertRaises(OSError):
                move_package(self.audio, self.done)
        self.assert_package(self.audio, metadata)
        self.assertEqual(list(self.done.iterdir()), [])

    def test_pending_history_recovers_after_archiving_with_collision(self):
        from core.manual_beatstars import ManualBeatStars
        from core.manual_beatstars_store import HistoryError
        from test_manual_beatstars import HLS, Resolver, Source, Tools, PROFILE
        store = HistoryStore(self.root / 'config/history.json')
        service = ManualBeatStars(store, Source(), Resolver(), HLS(), Tools())
        search = service.search(PROFILE)
        save = store.save
        def fail_completion(state):
            if state['pending'] is None:
                raise HistoryError('history_write_failed')
            save(state)
        with patch.object(store, 'save', side_effect=fail_completion):
            with self.assertRaises(HistoryError):
                service.download(search, ['TK101'], self.audio.parent)
        pending_audio = Path(store.load()['pending']['audio'])
        metadata = read_metadata(pending_audio, verify=True)
        self.done.mkdir()
        (self.done / pending_audio.name).write_bytes(b'older audio with same name')
        moved = move_package(pending_audio, self.done)
        self.assert_package(moved, metadata)
        restarted = ManualBeatStars(HistoryStore(store.path), Source(), Resolver(), HLS(), Tools())
        self.assertEqual([c.track.id for c in restarted.search(PROFILE).candidates], ['TK102'])
        self.assertIsNone(store.load()['pending'])

    def test_modified_archive_is_not_registered_and_keeps_pending_intent(self):
        from core.manual_beatstars_store import HistoryError
        metadata = write_package(self.audio)
        store = HistoryStore(self.root / 'history.json')
        with store.locked():
            state = dict(version=1, downloads={}, pending={'audio': str(self.audio), 'metadata': metadata})
            store.save(state)
            moved = Path(move_package(self.audio, self.done))
            moved.write_bytes(b'x' * metadata['size'])
            with self.assertRaisesRegex(HistoryError, 'package_recovery_conflict'):
                store.recover(store.load())
        self.assertIsNotNone(store.load()['pending'])
        self.assertEqual(moved.read_bytes(), b'x' * metadata['size'])

    def test_split_archive_does_not_delete_original_audio_during_history_recovery(self):
        from core.manual_beatstars_store import HistoryError
        metadata = write_package(self.audio)
        store = HistoryStore(self.root / 'history.json')
        with store.locked():
            store.save(dict(version=1, downloads={}, pending={'audio': str(self.audio), 'metadata': metadata}))
            self.done.mkdir()
            Path(str(self.audio) + SIDECAR).rename(str(self.done / self.audio.name) + SIDECAR)
            with self.assertRaisesRegex(HistoryError, 'package_recovery_conflict'):
                store.recover(store.load())
        self.assertTrue(self.audio.exists())
        self.assertTrue(Path(str(self.audio) + LINK).exists())


class RenderMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.audio = self.root / 'TK101 - wrong filename (2).m4a'
        self.metadata = write_package(self.audio)
        self.profile = dict(cp.default_profile('Canal'), titulo='{artist} - {name}',
                            artistas=['Juice WRLD'], descripcion='Buy: {beatstars_url}\n{name} | {bpm} BPM',
                            tags=['{name} type beat', '{artist}'])

    def test_metadata_title_supplies_name_artist_bpm_key_and_link(self):
        values = mr.beat_values(self.profile, 'wrong filename', 'Canal', self.metadata)
        self.assertEqual((values['name'], values['artist'], values['bpm'], values['key']),
                         ('Night', 'Juice WRLD', '140', 'A Minor'))
        self.assertEqual(mr.beat_title(self.profile, 'wrong filename', 'Canal', self.metadata), 'Juice WRLD - Night')
        self.assertEqual(mr.beat_tags(self.profile, 'wrong filename', 'Canal', self.metadata),
                         ['Night type beat', 'Juice WRLD'])
        self.assertIn('Buy: ' + URL, mr.beat_text(self.profile, 'wrong filename', 'Canal', self.metadata))

    def test_url_is_not_inserted_into_existing_description_without_placeholder(self):
        profile = dict(self.profile, descripcion='Fixed description\n{name}')
        self.assertEqual(mr.beat_text(profile, 'wrong', 'Canal', self.metadata), 'Fixed description\nNight')
        output = mr.upload_text('Edited title', 'Fixed description', ['trap'], URL)
        self.assertEqual(output.count('\nBEATSTARS\n'), 1)
        self.assertTrue(output.endswith('\nBEATSTARS\n' + URL + '\n'))
        self.assertEqual(profile['descripcion'], 'Fixed description\n{name}')

    def test_title_override_does_not_change_url_or_description_identity(self):
        result = dict(title='Edited', folder=str(self.root))
        with patch.object(cp, 'media', return_value=(['image.png'], [])), \
                patch.object(mr, 'render_beat', return_value=result) as render, patch.object(mr, 'add_pending'):
            outputs, errors = mr.run_batch([str(self.audio)], 'Canal', str(self.root), str(self.root),
                profile=self.profile, tools=object(), titles={str(self.audio): 'Edited'})
        self.assertEqual(errors, [])
        self.assertEqual(outputs, [result])
        self.assertEqual(render.call_args.args[3], 'Edited')
        self.assertIn('Buy: ' + URL, render.call_args.args[8])
        self.assertIn('Night | 140 BPM', render.call_args.args[8])
        self.assertEqual(render.call_args.kwargs['beatstars_url'], URL)

    def test_corrupt_metadata_skips_only_affected_beat(self):
        Path(str(self.audio) + SIDECAR).write_text('{broken')
        local = self.root / 'ordinary.mp3'
        local.write_bytes(b'ordinary audio')
        result = dict(title='ordinary', folder=str(self.root))
        with patch.object(cp, 'media', return_value=(['image.png'], [])), \
                patch.object(mr, 'render_beat', return_value=result) as render, patch.object(mr, 'add_pending'):
            outputs, errors = mr.run_batch([str(self.audio), str(local)], 'Canal', str(self.root), str(self.root),
                                          profile=self.profile, tools=object())
        self.assertEqual(outputs, [result])
        self.assertEqual(len(errors), 1)
        self.assertIn('metadata de BeatStars', errors[0][1])
        self.assertEqual(render.call_args.args[0], str(local))
        self.assertEqual(render.call_args.kwargs['beatstars_url'], '')

    def test_modified_audio_is_not_rendered_with_an_unrelated_link(self):
        self.audio.write_bytes(b'changed audio')
        with patch.object(cp, 'media', return_value=(['image.png'], [])), \
                patch.object(mr, 'render_beat') as render:
            outputs, errors = mr.run_batch([str(self.audio)], 'Canal', str(self.root), str(self.root),
                                          profile=self.profile, tools=object())
        self.assertEqual(outputs, [])
        self.assertIn('no coincide', errors[0][1])
        render.assert_not_called()


if __name__ == '__main__':
    unittest.main()
