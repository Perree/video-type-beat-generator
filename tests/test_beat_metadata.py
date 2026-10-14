import unittest
from copy import deepcopy
from core.beat_metadata import refresh_pending_seo

class MetadataRefreshTests(unittest.TestCase):
    def test_refresh_archives_only_unattempted_jobs_and_preserves_ledger(self):
        old={'manual':{'tags':[],'description':''},'sha256':'old'}
        def job(channel='latin',status='planned',**extra):return dict(channel=channel,status=status,seo_snapshot=deepcopy(old),**extra)
        state={'lock':None,'attempts':{'2026-10-14':{'token':{'job_id':'ambiguous'}}},
          'jobs':{'pending':job(),'ambiguous':job(),'uploaded':job(status='uploaded',youtube_id='video'),
                  'other':job(channel='other'),'failed':job(status='failed')}}
        original=deepcopy(state)
        channel={'id':'latin','seo':{'tags':[],'description':'New description','title_template':'Model {name}'}}
        self.assertEqual(refresh_pending_seo(state,channel),['pending','failed'])
        for key in ('ambiguous','uploaded','other'):self.assertEqual(state['jobs'][key],original['jobs'][key])
        self.assertEqual(state['attempts'],original['attempts'])
        self.assertEqual(state['jobs']['pending']['seo_snapshot_history'],[old])
        self.assertNotIn('seo_snapshot',state['jobs']['pending'])
        self.assertEqual(refresh_pending_seo(state,channel),[])

    def test_running_render_cannot_be_modified(self):
        state={'lock':{'owner':'worker'},'jobs':{},'attempts':{}}
        before=deepcopy(state)
        with self.assertRaises(ValueError):refresh_pending_seo(state,{'id':'latin'})
        self.assertEqual(state,before)

if __name__=='__main__':unittest.main()
