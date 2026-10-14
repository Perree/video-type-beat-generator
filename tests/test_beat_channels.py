import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from core.beat_actions import environment, check_environment
from scripts import beat_secrets_sync as sync

class BeatChannelsTests(unittest.TestCase):
    def test_channels_use_different_environments(self):
        self.assertEqual(environment('ey-mat'), 'type-beats-ey-mat')
        self.assertEqual(environment('mattwyyre'), 'type-beats-mattwyyre')
        for slug in ('../kit-weekly', '', '$(token)', 'UPPER'):
            with self.assertRaises(ValueError): environment(slug)

    def test_policy_checks_environment_of_selected_channel(self):
        urls=[]
        class Response:
            status=200
            def __init__(self,data): self.data=data
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self,size): return json.dumps(self.data).encode()
        class Opener:
            def open(self,request,**kwargs):
                urls.append(request.full_url)
                if '/deployment-branch-policies?' in request.full_url:
                    return Response({'total_count':1,'branch_policies':[{'name':'master','type':'branch'}]})
                return Response({'deployment_branch_policy':{'protected_branches':False,'custom_branch_policies':True}})
        check_environment({'GITHUB_REPOSITORY':'Perree/video-type-beat-generator','GITHUB_REF':'refs/heads/master','GITHUB_EVENT_NAME':'schedule','BEAT_SLUG':'mattwyyre'},Opener())
        self.assertTrue(all('/environments/type-beats-mattwyyre' in url for url in urls))

    def test_add_keeps_existing_channels(self):
        writes=[]
        with patch.object(sync.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='["ey-mat"]')):
            self.assertEqual(sync.add_channel_variable('mattwyyre',runner=lambda args,body:writes.append((args,body)) or 0),['ey-mat','mattwyyre'])
        self.assertEqual(json.loads(writes[0][1]),['ey-mat','mattwyyre'])

    def test_read_failure_or_corruption_never_overwrites_channels(self):
        for result in (SimpleNamespace(returncode=1,stdout=''),SimpleNamespace(returncode=0,stdout='{bad'),SimpleNamespace(returncode=0,stdout='{}')):
            writes=[]
            with patch.object(sync.subprocess,'run',return_value=result):
                with self.assertRaises(sync.kit.SyncError): sync.add_channel_variable('mattwyyre',runner=lambda *args:writes.append(args) or 0)
            self.assertEqual(writes,[])

    def test_failed_secret_sync_does_not_enable_channel(self):
        with patch.object(sync,'values_for',return_value={'BEAT_CHANNEL_ID':'mattwyyre'}), patch.object(sync.kit,'ensure_environment',return_value=False), patch.object(sync.kit,'sync',return_value=['BEAT_YT_TOKEN_JSON']), patch.object(sync,'add_channel_variable') as add:
            self.assertEqual(sync.main(['--channel','mattwyyre','--slug','mattwyyre']),1)
            add.assert_not_called()

if __name__=='__main__': unittest.main()
