"""Pruebas del módulo puro de estado de conexiones (sin Qt, sin red, sin gh)."""
import json
import os
import tempfile
import unittest

from core import automation_status as st
from core.automation_save_bar import pilot_ready, BEATS_PILOT_REQUIRED

TOKEN = 'secret_' + 'a' * 40
PAGE = 'a' * 32


def write(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(data if isinstance(data, str) else json.dumps(data))


class AutomationStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.addCleanup(self.tmp.cleanup)

    def path(self, name):
        return os.path.join(self.dir, name)

    def test_youtube_codes(self):
        self.assertEqual(st.youtube_token_status('', self.dir), st.UNKNOWN)
        self.assertEqual(st.youtube_token_status('ey mat', self.dir), st.MISSING)
        write(self.path('ey mat.json'), '{bad')
        self.assertEqual(st.youtube_token_status('ey mat', self.dir), st.INVALID)
        write(self.path('ey mat.json'), {'client_id': 'x'})
        self.assertEqual(st.youtube_token_status('ey mat', self.dir), st.INVALID)
        write(self.path('ey mat.json'), {'refresh_token': 'r'})
        self.assertEqual(st.youtube_token_status('ey mat', self.dir), st.OK)

    def test_youtube_path_traversal_stays_inside(self):
        # Los separadores se sanean: nunca debe leer fuera de tokens_dir.
        self.assertEqual(st.youtube_token_status('../../etc/passwd', self.dir), st.MISSING)

    def test_dropbox_codes(self):
        p = self.path('dbx.json')
        self.assertEqual(st.dropbox_worker_status(p), st.MISSING)
        write(p, {'refresh_token': 'r'})
        self.assertEqual(st.dropbox_worker_status(p), st.INVALID)
        write(p, {'refresh_token': 'r', 'app_key': 'k'})
        self.assertEqual(st.dropbox_worker_status(p), st.OK)

    def test_notion_save_and_status(self):
        p = self.path('beat_secrets.json')
        self.assertEqual(st.beat_notion_status(p), st.MISSING)
        write(p, {'OTHER': 'keep'})
        st.save_beat_notion(TOKEN, PAGE, p)
        self.assertEqual(st.beat_notion_status(p), st.OK)
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
        self.assertEqual(data['OTHER'], 'keep')
        self.assertEqual(st.read_beat_notion(p)['BEAT_NOTION_PAGE_ID'], PAGE)

    def test_notion_rejects_bad_values_without_leaking(self):
        p = self.path('beat_secrets.json')
        for token, page in (('', PAGE), (TOKEN, 'not-a-uuid'), ('con espacio', PAGE)):
            with self.assertRaises(st.AutomationError) as ctx:
                st.save_beat_notion(token, page, p)
            self.assertNotIn(token or 'x-none', str(ctx.exception))
        self.assertFalse(os.path.exists(p))
        write(p, {'BEAT_NOTION_TOKEN': TOKEN, 'BEAT_NOTION_PAGE_ID': 'bad'})
        self.assertEqual(st.beat_notion_status(p), st.INVALID)
        write(p, '[1]')
        self.assertEqual(st.beat_notion_status(p), st.INVALID)

    def test_gh_and_readiness(self):
        self.assertEqual(st.gh_available(lambda _: 'C:/gh.exe'), st.OK)
        self.assertEqual(st.gh_available(lambda _: None), st.MISSING)
        write(self.path('ch.json'), {'refresh_token': 'r'})
        items = st.readiness_beats('ch', 'ch', self.dir, self.path('no.json'),
                                   self.path('no2.json'), which=lambda _: None)
        by_id = {i['id']: i['ok'] for i in items}
        self.assertEqual(by_id, {'slug': True, 'youtube': True, 'dropbox': False,
                                 'gh': False, 'notion': False})
        bad = st.readiness_beats('ch', '../x', self.dir, which=lambda _: None)
        self.assertFalse(bad[0]['ok'])

    def test_kit_secrets_allowlist_and_status(self):
        p = self.path('kit_secrets.json')
        self.assertEqual(st.kit_telegram_status(p, {}), st.MISSING)
        self.assertEqual(st.kit_llm_status(p, {}), st.MISSING)
        with self.assertRaises(st.AutomationError) as ctx:
            st.save_kit_keys({'NOT_A_KEY': TOKEN}, p)
        self.assertNotIn(TOKEN, str(ctx.exception))
        self.assertFalse(os.path.exists(p))
        st.save_kit_keys({'KIT_TELEGRAM_TOKEN': TOKEN, 'KIT_TELEGRAM_CHAT_ID': '-1001',
                          'KIT_LLM_API_KEY': TOKEN, 'KIT_IMAGE_API_KEY': TOKEN}, p)
        st.save_kit_notion(TOKEN, PAGE, p)
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
        self.assertTrue(set(data) <= set(st.KIT_SHARED_KEYS))
        self.assertEqual(st.kit_telegram_status(p, {}), st.OK)
        self.assertEqual(st.kit_llm_status(p, {}), st.OK)
        self.assertEqual(st.kit_image_status(p, {}), st.OK)
        self.assertEqual(st.kit_notion_status(p, {}), st.OK)
        labels = ' '.join(i['label'] for i in st.readiness_kits(
            'ch', '', self.dir, self.path('no.json'), p, which=lambda _: None, env={}))
        self.assertNotIn(TOKEN, labels)
        self.assertEqual(st.kit_env_name(''), 'kit-weekly')
        self.assertEqual(st.kit_env_name('mi-canal'), 'kit-weekly-mi-canal')
        self.assertIsNone(st.kit_env_name('../x'))

    def test_kit_sync_blockers(self):
        write(self.path('ch.json'), {'refresh_token': 'r'})
        blockers = st.kit_sync_blockers('ch', '', self.dir, self.path('no.json'),
                                        self.path('no2.json'), which=lambda _: None, env={})
        self.assertIn('Telegram', ' '.join(blockers))
        self.assertIn('Dropbox', ' '.join(blockers))

    def test_pilot_ready_requires_connections_and_seo(self):
        write(self.path('ch.json'), {'refresh_token': 'r'})
        write(self.path('dbx.json'), {'refresh_token': 'r', 'app_key': 'k'})
        items = st.readiness_beats('ch', 'ch', self.dir, self.path('dbx.json'),
                                   which=lambda _: 'gh')
        self.assertFalse(pilot_ready(items, BEATS_PILOT_REQUIRED, st.MISSING))
        self.assertTrue(pilot_ready(items, BEATS_PILOT_REQUIRED, st.OK))


if __name__ == '__main__':
    unittest.main()
