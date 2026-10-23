import copy
import os
import random
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication, QDialog
from core.beat_distribution import distribute, recommend_counts
from core.beat_distribution_dialog import DistributionDialog, open_distribution
from core.beat_schema import migrate

APP = QApplication.instance() or QApplication([])


def channel(cid, days=(0, 3), active=True, priority=0):
    return dict(id=cid, active=active, priority=priority,
                slots=[dict(weekday=d, hour=20, minute=15) for d in days],
                selection_tags=['rock'], custom={'keep': True})


class DistributionTests(unittest.TestCase):
    def setUp(self):
        from core import gh_status, cloud_login
        self.offline = patch.object(gh_status.DEFAULT, '_run', return_value=(127, ''))
        self.offline.start()
        self.addCleanup(self.offline.stop)
        keyring = patch.object(cloud_login, '_get', return_value=None)
        keyring.start()
        self.addCleanup(keyring.stop)
        gh_status.DEFAULT.invalidate()

    def test_fifteen_channels_fixed_daily_and_priorities(self):
        config = migrate({'channels': [channel('ey mat'), channel('daily', priority=10)] +
                          [channel(str(i)) for i in range(13)]}, 'config')
        before = copy.deepcopy(config)
        counts = recommend_counts(config, {'ey mat'})
        self.assertEqual(counts['daily'], 7)
        result, loads = distribute(config, counts, {'ey mat'})
        self.assertEqual(sum(loads), 35)
        self.assertLessEqual(max(loads), 6)
        self.assertEqual(result['channels'][0], config['channels'][0])
        self.assertEqual(config, before)
        for ch in result['channels']:
            self.assertEqual(ch['custom'], {'keep': True})
            self.assertTrue(all(s['hour'] == 20 and s['minute'] == 15 for s in ch['slots']))

    def test_38_video_requested_mix(self):
        config = {'channels': [channel('ey mat'), channel('daily'), channel('four'), channel('three')] +
                  [channel(str(i)) for i in range(11)]}
        counts = dict(daily=7, four=4, three=3, **{str(i): 2 for i in range(11)})
        result, loads = distribute(config, counts, {'ey mat'})
        self.assertEqual(sum(loads), 38)
        self.assertLessEqual(max(loads), 6)
        self.assertEqual(len(result['channels'][1]['slots']), 7)

    def test_external_and_paused_are_preserved(self):
        config = {'channels': [channel('on'), channel('off', active=False)]}
        result, loads = distribute(config, {'on': 7}, external=[1, 0, 0, 1, 0, 0, 0])
        self.assertEqual(loads, [2, 1, 1, 2, 1, 1, 1])
        self.assertEqual(result['channels'][1], config['channels'][1])

    def test_impossible_daily_and_invalid_inputs(self):
        config = {'channels': [channel('on')]}
        for counts, external, ceiling in [({'on': 7}, [6, 0, 0, 0, 0, 0, 0], 6),
                                           ({'on': True}, [0]*7, 6),
                                           ({}, [0]*7, 6),
                                           ({'on': 2}, [0]*6, 6),
                                           ({'on': 2}, [0]*7, 100)]:
            with self.assertRaises(ValueError):
                distribute(config, counts, external=external, ceiling=ceiling)
        with self.assertRaises(ValueError):
            distribute(config, {}, fixed={'on'}, external=[6]*7)

    def test_recommendation_handles_concentrated_capacity(self):
        counts = recommend_counts({'channels': [channel('a'), channel('b')]},
                                  external=[4, 6, 6, 6, 6, 6, 6])
        self.assertEqual(counts, {'a': 1, 'b': 1})

    def test_random_feasibility_against_bipartite_degree_criterion(self):
        rng = random.Random(92)
        for _ in range(400):
            n, ceiling = rng.randint(1, 18), rng.randint(1, 6)
            external = [rng.randint(0, ceiling) for _ in range(7)]
            config = {'channels': [channel(str(i)) for i in range(n)]}
            counts = {str(i): rng.randint(1, 7) for i in range(n)}
            degrees = sorted(counts.values(), reverse=True)
            feasible = all(sum(degrees[:k]) <= sum(min(k, ceiling-v) for v in external)
                           for k in range(1, n+1))
            try:
                result, loads = distribute(config, counts, external=external, ceiling=ceiling)
            except ValueError:
                self.assertFalse(feasible, (counts, external, ceiling))
            else:
                self.assertTrue(feasible)
                self.assertLessEqual(max(loads), ceiling)
                for ch in result['channels']:
                    self.assertEqual(len(ch['slots']), counts[ch['id']])
                    self.assertEqual(len({s['weekday'] for s in ch['slots']}), counts[ch['id']])

    def test_dialog_back_cancel_and_apply(self):
        config = migrate({'channels': [channel('ey mat'), channel('other')]}, 'config')
        dialog = DistributionDialog(config)
        self.addCleanup(dialog.deleteLater)
        self.assertTrue(all(check.isChecked() for check, _ in dialog.rows.values()))
        dialog.rows['other'][0].setChecked(False)
        dialog.rows['other'][1].setValue(7)
        dialog.wizard.next()
        self.assertEqual(dialog.wizard.index, 1)
        self.assertIn('ey mat (fijo)', dialog.preview.toPlainText())
        dialog.wizard.back()
        dialog.rows['other'][1].setValue(3)
        dialog.wizard.next()
        dialog.wizard.next()
        self.assertEqual(dialog.result(), QDialog.Accepted)
        self.assertEqual(len(dialog.result_config['channels'][1]['slots']), 3)
        self.assertEqual(len(config['channels'][1]['slots']), 2)

    def test_panel_application_cancel_and_stale_draft(self):
        from core.beat_panel import BeatPanel
        panel = BeatPanel(autoload=False)
        self.addCleanup(panel.deleteLater)
        panel.config = migrate({'channels': [channel('ey mat'), channel('other')]}, 'config')
        panel.config_readable = True
        panel._refresh_list()
        panel._store_editor()
        before = copy.deepcopy(panel.config)

        def accept(dialog):
            dialog.rows['other'][0].setChecked(False)
            dialog.rows['other'][1].setValue(7)
            dialog.calculate()
            return QDialog.Accepted

        with patch.object(DistributionDialog, 'exec_', accept):
            open_distribution(panel)
        self.assertEqual(len(panel.config['channels'][1]['slots']), 7)
        self.assertEqual(panel.config['channels'][0], before['channels'][0])
        after = copy.deepcopy(panel.config)
        with patch.object(DistributionDialog, 'exec_', return_value=QDialog.Rejected):
            open_distribution(panel)
        self.assertEqual(panel.config, after)

        def stale(dialog):
            value = accept(dialog)
            panel.config['channels'][0]['priority'] = 99
            return value

        with patch.object(DistributionDialog, 'exec_', stale):
            open_distribution(panel)
        self.assertEqual(panel.config['channels'][0]['priority'], 99)
        self.assertIn('cambió', panel.status.text())

    def test_my_channels_distribution_save_round_trip(self):
        import json
        from core.beat_fakes import MemoryDropbox
        from core.beat_panel import BeatPanel
        from core.my_channels import MyChannelsView
        from tests.test_my_channels import seed, pump, FakeKits, CONFIG_PATH
        memory = seed(MemoryDropbox())
        panel = BeatPanel(cloud_provider=lambda: memory)
        self.addCleanup(panel.deleteLater)
        self.assertTrue(pump(lambda: panel.task is None))
        view = MyChannelsView(panel, FakeKits())
        self.addCleanup(view.deleteLater)
        original_remote = memory.files[CONFIG_PATH]

        def accept(dialog):
            dialog.rows['beat-a'][0].setChecked(False)
            dialog.rows['beat-a'][1].setValue(7)
            self.assertTrue(dialog.calculate())
            return QDialog.Accepted

        with patch.object(DistributionDialog, 'exec_', accept):
            view.distribute_beats()
        self.assertTrue(view.dirty)
        self.assertEqual(memory.files[CONFIG_PATH], original_remote)
        view.save()
        self.assertTrue(pump(lambda: panel.task is None))
        view.tick()
        persisted = json.loads(memory.files[CONFIG_PATH][0])
        self.assertEqual(len(persisted['channels'][0]['slots']), 7)
        self.assertFalse(persisted['channels'][1]['active'])


if __name__ == '__main__':
    unittest.main()
