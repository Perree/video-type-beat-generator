import unittest
from copy import deepcopy
from core import beat_settings
from core.beat_templates import apply_channel_templates
from core.beat_seo import build_snapshot,render

TITLE='Bad Bunny x Omar Courtz Type Beat - "{name}" | Reggaeton Type Beat 2026'
DESCRIPTION='🎹 Get the License + Untagged Audio:\n➔ {beatstars_url}\n\nCredit: Prod. MatWyre'

def registry_fixture():
    return {'schema_version':1,'namespace':'automatizacion','canales':[
        {'slug':'latin','tipo':'beats','clave':'latin','nombre':'latin','activo':True,
         'plantillas':{'title_template':TITLE,'description_template':DESCRIPTION}}]}

def config_fixture():
    return {'beatstars_profile_url':'https://www.beatstars.com/fixture','channels':[
            {'id':'latin','active':False,'priority':0,'slots':[{'weekday':1,'hour':10,'minute':0}],
             'use_channel_templates':True,'seo':{'tags':['reggaeton'],'description':''}}]}

class ChannelTemplateTests(unittest.TestCase):
    def test_model_is_compiled_without_mutating_input(self):
        config,registry=config_fixture(),registry_fixture();original=deepcopy((config,registry))
        settings=beat_settings.settings(config,registry)
        self.assertEqual((config,registry),original)
        self.assertEqual(settings['channels'][0]['seo']['title_template'],TITLE)
        self.assertEqual(settings['channels'][0]['seo']['description'],DESCRIPTION.replace('{beatstars_url}','{url}'))

    def test_registry_edits_refresh_the_worker_profile(self):
        config,registry=config_fixture(),registry_fixture()
        compiled=beat_settings.settings(config,registry)
        registry['canales'][0]['plantillas']['title_template']='New model "{name}"'
        self.assertEqual(beat_settings.validate(compiled,registry)['channels'][0]['seo']['title_template'],'New model "{name}"')
        self.assertFalse(hasattr(beat_settings,'save'))

    def test_channel_outside_registry_is_rejected(self):
        with self.assertRaises(ValueError):
            beat_settings.validate(config_fixture(),{'canales':[]})

    def test_snapshot_renders_name_and_beat_link(self):
        channel=beat_settings.settings(config_fixture(),registry_fixture())['channels'][0]
        job={'id':'fixture','track_id':'TK101','channel':'latin'}
        track={'id':'TK101','title':'Emboscada','tags':['reggaeton']}
        snapshot,_=build_snapshot(job,track,channel,'2026-10-14T01:00:00-03:00')
        self.assertEqual(snapshot['selected']['title'],TITLE.replace('{name}','Emboscada'))
        self.assertEqual(render(snapshot['selected']['description'],track,'https://www.beatstars.com/beat/emboscada-101'),DESCRIPTION.replace('{beatstars_url}','https://www.beatstars.com/beat/emboscada-101'))

    def test_other_channels_and_invalid_placeholders(self):
        channel={'id':'other','seo':{'tags':[],'description':'Existing profile'}}
        original=deepcopy(channel)
        apply_channel_templates(channel,{'title_template':TITLE,'description_template':DESCRIPTION})
        self.assertEqual(channel,original)
        channel['use_channel_templates']=True
        with self.assertRaises(ValueError):apply_channel_templates(channel,{'title_template':'{name}','description_template':'{bpm}'})

if __name__=='__main__':unittest.main()
