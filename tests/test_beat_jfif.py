import io
import unittest
from PIL import Image
from core.beat_assets import DropboxAssets
from core.beat_render import MediaTools
from core.beat_video import render_reserved
from test_beat_video import fixture, AssetsClient, Processes, Resolver, HLS

class JfifTests(unittest.TestCase):
    def test_jfif_catalog_render_and_thumbnail(self):
        cloud,key,track,channel=fixture()
        channel['visual']={'mode':'image','plain_image':True}
        client=AssetsClient()
        stream=io.BytesIO()
        Image.new('RGB',(640,360),'blue').save(stream,'JPEG')
        client.files={'/images/trap/cover.jfif':stream.getvalue()}
        assets=DropboxAssets(client)
        self.assertEqual([r['path'] for r in assets.list_images('/images/trap')],['/images/trap/cover.jfif'])
        with render_reserved(cloud,key,track,channel,'trap','https://www.beatstars.com/fixture',assets,resolver=Resolver(),http=HLS(),tools=MediaTools('fakeffmpeg','fakeprobe',Processes())) as result:
            self.assertTrue(result['video'].exists())
            with Image.open(result['thumbnail']) as thumb:
                self.assertEqual(thumb.format,'JPEG')
                self.assertEqual(thumb.size,(1280,720))
        state,_=cloud.read('state')
        self.assertEqual(state['jobs'][key]['visual_snapshot']['path'],'/images/trap/cover.jfif')
        self.assertEqual(state['attempts'],{})

if __name__=='__main__': unittest.main()
