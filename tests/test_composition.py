from pathlib import Path
import io
import struct
import subprocess
import tempfile
import time
import unittest
import wave
import zlib

from server.http import Workspace
from server.store import AppError,Store
from server.render import Renderer
from server.media import HIDDEN

ROOT=Path(__file__).resolve().parents[1]


def png(width,height):
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    row=b'\x00'+bytes([255,0,0])*(width//2)+bytes([0,0,255])*(width-width//2)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(row*height))+chunk(b'IEND',b'')


class CompositionTests(unittest.TestCase):
    def test_old_projects_and_backups_keep_defaults_and_reject_invalid_crop(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory)
            p=store.save('project','p-old',{'song':'V7旧方案','clipEnd':2,'scenes':[{'start':0,'end':2}]})
            self.assertEqual(p['caption'],{'enabled':True,'size':4.7,'bottom':10})
            self.assertEqual(p['scenes'][0]['cropX'],.5)
            for bad in [float('nan'),-1,2,'0.5',True]:
                with self.assertRaises(AppError):store.save('project','p-old',{'scenes':[{'start':0,'end':2,'cropX':bad}]},expected=p['revision'])
            changed=store.save('project','p-old',{'caption':{'enabled':False,'size':6,'bottom':25}},expected=p['revision'])
            self.assertEqual(Store(directory).get('project','p-old')['caption'],changed['caption'])

    def test_actual_video_obeys_left_and_right_crop_and_caption_placement(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace=Workspace(ROOT,directory)
            try:
                if not workspace.media.ffmpeg or not workspace.media.ffprobe:self.skipTest('FFmpeg unavailable')
                folder=workspace.store.directory/'temp'
                audio_path=folder/'fixture.wav'
                with wave.open(str(audio_path),'wb') as output:
                    output.setnchannels(1);output.setsampwidth(2);output.setframerate(16000);output.writeframes(b'\0\0'*32000)
                image_path=folder/'regions.png';image_path.write_bytes(png(1000,400))
                audio=workspace.media.add_file(audio_path,'fixture.wav');image=workspace.media.add_file(image_path,'regions.png')
                scenes=[{'id':'s-left','start':0,'end':1,'assetId':image['id'],'cropX':0,'lyric':'PREVIEW'}, {'id':'s-right','start':1,'end':2,'assetId':image['id'],'cropX':1,'lyric':'PREVIEW'}]
                project=workspace.store.save('project','p-crop',{'song':'取景输出验收','sourceId':audio['id'],'clipEnd':2,'scenes':scenes,'caption':{'enabled':True,'size':6,'bottom':75}})
                job=workspace.renderer.start(project,{'quality':'540','subtitles':workspace.media.has_subtitles})
                deadline=time.monotonic()+60
                while time.monotonic()<deadline:
                    result=workspace.store.get('job',job['id'])
                    if result['status'] not in ['queued','running']:break
                    time.sleep(.1)
                self.assertEqual(result['status'],'done',result.get('error'))
                work=workspace.store.get('work',result['workId']);video=workspace.media.path(work['videoId'])
                for seconds,red in [(.3,True),(1.3,False)]:
                    command=[workspace.media.ffmpeg,'-v','error','-ss',str(seconds),'-i',str(video),'-vf','crop=2:2:270:480','-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1']
                    frame=subprocess.run(command,capture_output=True,check=True,**HIDDEN).stdout
                    self.assertEqual(len(frame),12)
                    self.assertGreater(frame[0] if red else frame[2],200)
                    self.assertLess(frame[2] if red else frame[0],30)
                # Subtitle positioning is additionally checked at the generated ASS boundary.
                path=folder/'captions.ass';Renderer._subtitles(path,project['scenes'],540,960,project['caption'])
                ass=path.read_text(encoding='utf-8-sig');self.assertIn('Microsoft YaHei,32',ass);self.assertIn(',32,32,720,1',ass)
            finally:workspace.close()


if __name__=='__main__':unittest.main()
