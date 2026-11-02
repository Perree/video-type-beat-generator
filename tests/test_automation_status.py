"""Pruebas del módulo puro de estado de conexiones (sin Qt, sin red, con gh y llavero falsos)."""
import unittest

from core import automation_status as st, cloud_login, gh_status
from core.automation_save_bar import pilot_ready, BEATS_PILOT_REQUIRED
from core.cloud_fakes import FakeGhRun, MemoryKeyring

TOKEN = 'secret_' + 'a' * 40
PAGE = 'a' * 32


class AutomationStatusTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeGhRun()
        self.gh = gh_status.GhStatus(run=self.fake)
        self.previous = cloud_login.set_backend(MemoryKeyring())
        self.addCleanup(cloud_login.set_backend, self.previous)

    def put(self, env, *names):
        self.fake.put(env, *names)
        self.gh.invalidate()

    def test_youtube_codes_come_from_secret_names(self):
        self.assertEqual(st.beat_youtube_status('', self.gh), st.UNKNOWN)
        self.assertEqual(st.beat_youtube_status('../x', self.gh), st.UNKNOWN)
        self.assertEqual(st.beat_youtube_status('ey-mat', self.gh), st.MISSING)
        self.put('kit-weekly', 'BEAT_YT_TOKEN_JSON_EY_MAT')
        self.assertEqual(st.beat_youtube_status('ey-mat', self.gh), st.OK)
        self.assertEqual(st.kit_youtube_status('kit-weekly', self.gh), st.MISSING)
        self.put('kit-weekly', 'KIT_YT_CHANNEL')
        self.assertEqual(st.kit_youtube_status('kit-weekly', self.gh), st.INVALID)
        self.put('kit-weekly', 'KIT_YT_TOKEN_JSON')
        self.assertEqual(st.kit_youtube_status('kit-weekly', self.gh), st.OK)

    def test_status_reads_only_names_and_dates(self):
        self.put(None, *st.KIT_DROPBOX_KEYS)
        self.assertEqual(st.dropbox_worker_status(gh=self.gh), st.OK)
        code, text = st.shared_badge(st.KIT_DROPBOX_KEYS, gh=self.gh)
        self.assertEqual((code, text), (st.OK, 'cargado ✓ (2026-10-13)'))
        self.assertTrue(all(a[:2] in (['secret', 'list'], ['auth', 'status'])
                            for a, _ in self.fake.calls))

    def test_unknown_without_gh_session(self):
        gh = gh_status.GhStatus(run=FakeGhRun(logged_in=False))
        self.assertEqual(st.dropbox_worker_status(gh=gh), st.UNKNOWN)
        self.assertEqual(st.gh_auth_status(gh), st.MISSING)
        with self.assertRaises(st.AutomationError):
            st.save_beat_notion(TOKEN, PAGE, gh)

    def test_notion_save_goes_to_secrets_by_stdin(self):
        self.assertEqual(st.beat_notion_status(self.gh), st.MISSING)
        st.save_beat_notion(TOKEN, PAGE, self.gh)
        self.assertEqual(st.beat_notion_status(self.gh), st.OK)
        self.assertEqual(self.fake.value('kit-weekly', 'BEAT_NOTION_TOKEN'), TOKEN)
        self.assertNotIn(TOKEN, repr([a for a, _ in self.fake.calls]))

    def test_notion_rejects_bad_values_without_leaking(self):
        for token, page in (('', PAGE), (TOKEN, 'not-a-uuid'), ('con espacio', PAGE)):
            with self.assertRaises(st.AutomationError) as ctx:
                st.save_beat_notion(token, page, self.gh)
            self.assertNotIn(token or 'x-none', str(ctx.exception))
        self.assertFalse(any(a[:2] == ['secret', 'set'] for a, _ in self.fake.calls))

    def test_gh_and_readiness(self):
        self.assertEqual(st.gh_available(lambda _: 'C:/gh.exe'), st.OK)
        self.assertEqual(st.gh_available(lambda _: None), st.MISSING)
        self.put('kit-weekly', 'BEAT_YT_TOKEN_JSON_CH')
        by_id = {i['id']: i['ok'] for i in st.readiness_beats('ch', 'ch', self.gh)}
        self.assertEqual(by_id, {'slug': True, 'youtube': True, 'dropbox': False,
                                 'gh': True, 'notion': False})
        bad = st.readiness_beats('ch', '../x', self.gh)
        self.assertFalse(bad[0]['ok'])

    def test_kit_secrets_allowlist_and_all_environments(self):
        self.fake.envs['kit-weekly-mi-canal'] = {}
        self.gh.invalidate()
        self.assertEqual(st.kit_telegram_status(gh=self.gh), st.MISSING)
        with self.assertRaises(st.AutomationError) as ctx:
            st.save_kit_keys({'NOT_A_KEY': TOKEN}, self.gh)
        self.assertNotIn(TOKEN, str(ctx.exception))
        envs = st.save_kit_keys({'KIT_TELEGRAM_TOKEN': TOKEN, 'KIT_TELEGRAM_CHAT_ID': '-1001',
                                 'KIT_LLM_API_KEY': TOKEN, 'KIT_IMAGE_API_KEY': TOKEN}, self.gh)
        st.save_kit_notion(TOKEN, PAGE, self.gh)
        self.assertEqual(envs, [st.REPO, 'kit-weekly', 'kit-weekly-mi-canal'])
        for env in envs:
            self.assertTrue(set(self.fake.envs[env or '(repo)']) <= set(st.KIT_SHARED_KEYS))
            self.assertEqual(st.kit_telegram_status(env, self.gh), st.OK)
            self.assertEqual(st.kit_llm_status(env, self.gh), st.OK)
            self.assertEqual(st.kit_image_status(env, self.gh), st.OK)
            self.assertEqual(st.kit_notion_status(env, self.gh), st.OK)
        labels = ' '.join(i['label'] for i in st.readiness_kits('ch', '', self.gh))
        self.assertNotIn(TOKEN, labels)
        self.assertEqual(st.kit_env_name(''), 'kit-weekly')
        self.assertEqual(st.kit_env_name('mi-canal'), 'kit-weekly-mi-canal')
        self.assertIsNone(st.kit_env_name('../x'))

    def test_new_channel_uses_the_shared_secrets_without_configuring_them_again(self):
        st.save_kit_keys({'KIT_TELEGRAM_TOKEN': TOKEN, 'KIT_TELEGRAM_CHAT_ID': '-1001'}, self.gh)
        self.assertFalse(set(st.KIT_TELEGRAM_KEYS) & set(self.fake.envs.get('kit-weekly', {})))
        st.save_worker_dropbox({'app_key': 'key', 'refresh_token': TOKEN}, self.gh)
        self.fake.envs['kit-weekly-nuevo'] = {}  # canal creado después: su Environment está vacío
        self.put('kit-weekly-nuevo', *st.KIT_YT_KEYS)  # solo se conectó su YouTube
        by_id = {i['id']: i['ok'] for i in st.readiness_kits('Nuevo', 'nuevo', self.gh)}
        self.assertTrue(by_id['telegram'] and by_id['dropbox'] and by_id['youtube'])
        self.assertEqual(st.shared_badge(st.KIT_TELEGRAM_KEYS, 'kit-weekly-nuevo', self.gh)[0], st.OK)
        self.assertEqual(st.kit_telegram_status(gh=self.gh), st.OK)

    def test_old_copies_only_in_kit_weekly_ask_to_save_once_more(self):
        self.put('kit-weekly', *st.KIT_TELEGRAM_KEYS)  # configurado antes, solo en kit-weekly
        self.assertEqual(st.kit_telegram_status('kit-weekly', self.gh), st.OK)  # Beats sigue andando
        self.assertEqual(st.kit_telegram_status(gh=self.gh), st.MISSING)  # Conexiones pide guardarlo

    def test_env_values_still_checked_in_memory(self):
        self.assertEqual(st.kit_telegram_status(env={}), st.MISSING)
        self.assertEqual(st.kit_telegram_status(env={'KIT_TELEGRAM_TOKEN': TOKEN,
                                                     'KIT_TELEGRAM_CHAT_ID': '1'}), st.OK)

    def test_kit_sync_blockers(self):
        gh = gh_status.GhStatus(run=FakeGhRun(logged_in=False))
        blockers = st.kit_sync_blockers('ch', '../x', gh)
        self.assertIn('GitHub', ' '.join(blockers))
        self.assertIn('Environment', ' '.join(blockers))
        self.assertEqual(st.kit_sync_blockers('ch', '', self.gh), [])

    def test_worker_dropbox_goes_to_every_environment_not_the_keyring(self):
        self.fake.envs['kit-weekly-mi-canal'] = {}
        self.gh.invalidate()
        envs = st.save_worker_dropbox({'app_key': 'key', 'refresh_token': TOKEN}, self.gh)
        self.assertEqual(envs, [st.REPO, 'kit-weekly', 'kit-weekly-mi-canal'])
        self.assertEqual(self.fake.value(None, 'KIT_DROPBOX_REFRESH_TOKEN'), TOKEN)
        self.assertEqual(self.fake.value('kit-weekly-mi-canal', 'KIT_DROPBOX_REFRESH_TOKEN'), TOKEN)
        self.assertIsNone(cloud_login.dropbox_credentials())
        with self.assertRaises(st.AutomationError):
            st.save_worker_dropbox({'app_key': 'key', 'refresh_token': ''}, self.gh)

    def test_beat_slug_belongs_to_one_channel(self):
        rows = [{'id': 'ey mat', 'actions_slug': 'ey-mat'}, {'id': 'nuevo', 'actions_slug': 'ey-mat'}]
        registry = {'canales': [{'slug': 'ey-mat', 'tipo': 'beats', 'clave': 'ey mat'}]}
        self.assertIsNone(st.beat_slug_error('ey mat', 'ey-mat', rows[:1], registry))
        self.assertIn('ey mat', st.beat_slug_error('nuevo', 'ey-mat', rows, None))
        self.assertIn('registro', st.beat_slug_error('nuevo', 'ey-mat', [], registry))
        self.assertIn('registro', st.beat_slug_error('ey mat', 'otro', [], registry))
        self.assertIsNotNone(st.beat_slug_error('ey mat', '../x'))

    def test_kit_default_channel_and_identity(self):
        registry = {'canales': [{'slug': 'w', 'tipo': 'loops', 'clave': 'W', 'legacy_default': True}]}
        self.assertEqual(st.kit_default_channel(registry, {'kit_preview': {'channel': 'X'}}), 'W')
        self.assertEqual(st.kit_default_channel(None, {'kit_preview': {'channel': 'X'}}), 'X')
        self.assertIsNone(st.kit_default_channel(None, None))
        self.assertIsNone(st.youtube_identity_error(None, 'UC1'))
        self.assertIsNone(st.youtube_identity_error('UC1', 'UC1'))
        self.assertIsNotNone(st.youtube_identity_error('UC1', 'UC2'))

    def test_pilot_ready_requires_connections_and_seo(self):
        self.put('kit-weekly', 'BEAT_YT_TOKEN_JSON_CH', *st.KIT_DROPBOX_KEYS)
        items = st.readiness_beats('ch', 'ch', self.gh)
        self.assertFalse(pilot_ready(items, BEATS_PILOT_REQUIRED, st.MISSING))
        self.assertTrue(pilot_ready(items, BEATS_PILOT_REQUIRED, st.OK))


if __name__ == '__main__':
    unittest.main()
