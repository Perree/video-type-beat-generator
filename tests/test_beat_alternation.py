"""Alternation remains stable across weeks, retries and lost CAS responses."""
import json
import unittest
from core.beat_visual_schedule import job_options
from core.beat_assets import DropboxAssets
from core.beat_render import MediaTools
from core.beat_video import render_reserved
from core.beat_cloud import Transient
from test_beat_video import fixture, AssetsClient, Processes, HLS, Resolver

class AlternationTests(unittest.TestCase):
    def test_alternates_across_week_boundary(self):
        channel={'slots':[{'weekday':d,'hour':10,'minute':0} for d in (1,3,5)],'visual':{'mode':'alternate'}}
        dates=['2026-10-13','2026-10-15','2026-10-17','2026-10-20','2026-10-22','2026-10-24']
        modes=[job_options(channel,{'slot':d+'T10:00:00-03:00'})['mode'] for d in dates]
        self.assertTrue(all(a!=b for a,b in zip(modes,modes[1:])))
        channel['slots'].reverse()
        self.assertEqual(modes,[job_options(channel,{'slot':d+'T10:00:00-03:00'})['mode'] for d in dates])

    def test_snapshot_survives_schedule_change(self):
        self.assertEqual(job_options({'slots':[],'visual':{'mode':'alternate'}},{'visual_mode_snapshot':'video'})['mode'],'video')
        with self.assertRaises(ValueError): job_options({'visual':{'mode':'alternate'}},{'visual_mode_snapshot':'other'})
        self.assertEqual(job_options({'visual':{'mode':'image'}},{})['mode'],'image')

    def test_render_freezes_mode_even_after_lost_response(self):
        cloud,key,track,channel=fixture()
        channel.update(slots=[{'weekday':0,'hour':18,'minute':0},{'weekday':1,'hour':18,'minute':0}],visual={'mode':'alternate','plain_image':True})
        original=cloud.transport.write
        pending=[True]
        def losing(path,payload,rev):
            doc=json.loads(payload)
            result=original(path,payload,rev)
            if pending and doc['jobs'][key].get('visual_mode_snapshot'):
                pending.clear()
                raise Transient()
            return result
        cloud.transport.write=losing
        client,process=AssetsClient(),Processes()
        with render_reserved(cloud,key,track,channel,'trap','https://www.beatstars.com/fixture',DropboxAssets(client),resolver=Resolver(),http=HLS(),tools=MediaTools('fakeffmpeg','fakeprobe',process)) as result:
            self.assertEqual(result['visual_mode'],'image')
        state,_=cloud.read('state')
        self.assertEqual(state['jobs'][key]['visual_mode_snapshot'],'image')
        self.assertEqual(state['attempts'],{})
        self.assertIsNone(state['lock'])

    def test_alternate_video_branch_uses_its_thumbnail(self):
        import tempfile
        from pathlib import Path
        from test_beat_montage import MontageProcesses, MP4
        cloud,key,track,channel=fixture()
        with tempfile.TemporaryDirectory() as folder:
            Path(folder,'a.mp4').write_bytes(MP4)
            channel.update(slots=[{'weekday':0,'hour':17,'minute':0},{'weekday':0,'hour':18,'minute':0}],visual={'mode':'alternate','videos_folder':folder,'clip_min_seconds':.5,'clip_max_seconds':.5})
            client,process=AssetsClient(),MontageProcesses()
            with render_reserved(cloud,key,track,channel,'trap','https://www.beatstars.com/fixture',DropboxAssets(client),resolver=Resolver(),http=HLS(),tools=MediaTools('fakeffmpeg','fakeprobe',process)) as result:
                self.assertEqual(result['visual_mode'],'video')
                self.assertTrue(result['thumbnail'].exists())
            state,_=cloud.read('state')
            self.assertEqual(state['jobs'][key]['visual_mode_snapshot'],'video')
            self.assertEqual(state['attempts'],{})

if __name__=='__main__': unittest.main()
