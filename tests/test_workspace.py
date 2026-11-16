"""Integration contracts: persistence, lost-update protection, portable media and real rendering."""
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from urllib.parse import quote
from zipfile import ZipFile
import base64
import io
import json
import shutil
import struct
import subprocess
import tempfile
import threading
import time
import unittest
import wave
from unittest.mock import patch

from server.http import Workspace,make_server
from server.store import AppError,Store,ident

ROOT=Path(__file__).resolve().parents[1]


class DiskTests(unittest.TestCase):
    def test_restart_conflict_and_atomic_import(self):
        with tempfile.TemporaryDirectory() as folder:
            first=Store(folder)
            project=first.save('project','p-first',{'song':'第一首歌'})
            second=Store(folder)
            self.assertEqual(second.get('project','p-first')['song'],'第一首歌')
            updated=second.save('project','p-first',{'feeling':'另一个窗口的修改'},expected=project['revision'])
            with self.assertRaises(AppError) as raised:
                first.save('project','p-first',{'song':'不应覆盖'},expected=project['revision'])
            self.assertEqual(raised.exception.status,409)
            self.assertEqual(first.get('project','p-first')['song'],'第一首歌')
            with self.assertRaises(AppError):
                first.import_documents([{'kind':'project','value':{'id':'p-new','song':'不能部分导入'}},{'kind':'project','value':{'id':'p-invalid','song':''}}])
            self.assertIsNone(first.get('project','p-new'))
            self.assertGreater(len(list((Path(folder)/'backups').glob('*.json'))),0)
            with self.assertRaises(AppError):
                first.save('project','p-first',{'status':'done'},expected=updated['revision'])


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.app=Workspace(ROOT,Path(cls.temp.name)/'workspace')
        cls.server=make_server(cls.app,0)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.app.close();cls.thread.join();cls.temp.cleanup()

    def request(self,method,path,value=None,raw=None,headers=None,expected=200):
        data=raw if raw is not None else json.dumps(value,ensure_ascii=False).encode() if value is not None else None
        request_headers={'Content-Type':'application/octet-stream' if raw is not None else 'application/json','X-Songscene-Token':self.app.token,**(headers or {})}
        try:
            response=urlopen(Request(self.base+quote(path,safe='/?=&:%'),data=data,method=method,headers=request_headers),timeout=90)
            content=response.read();status=response.status
            result=json.loads(content) if 'application/json' in response.headers.get('Content-Type','') else content
        except HTTPError as error:
            status=error.code;content=error.read();result=json.loads(content)
        self.assertEqual(status,expected,result if isinstance(result,dict) else str(result)[:100])
        return result

    def project(self,**values):
        return self.request('POST','/api/projects',{'song':'集成验收歌曲',**values},expected=201)

    def fixture_assets(self):
        if not self.app.media.ffprobe:self.skipTest('ffprobe unavailable')
        data=io.BytesIO()
        with wave.open(data,'wb') as output:
            output.setnchannels(1);output.setsampwidth(2);output.setframerate(16000)
            output.writeframes(struct.pack('<h',0)*16000*3)
        audio=self.request('POST','/api/assets?name=验收音乐.wav',raw=data.getvalue(),expected=201)
        image=self.request('POST','/api/assets?name=验收画面.jpg',raw=(ROOT/'界面/artwork/49.jpg').read_bytes(),expected=201)
        return audio,image

    def test_01_state_origin_and_private_paths(self):
        state=self.request('GET','/api/state')
        self.assertEqual(state['version'],8);self.assertEqual(len(state['stockWorks']),10)
        self.request('POST','/api/projects',{'song':'不应保存'},headers={'Origin':'https://other.example'},expected=403)
        self.request('POST','/api/projects',{'song':'不应保存'},headers={'X-Songscene-Token':''},expected=403)
        self.request('GET','/data/workspace.sqlite3',expected=404)
        self.request('GET','/界面/../../data/workspace.sqlite3',expected=404)
        with patch('sys.stderr',None):
            self.request('POST','/api/projects',{'song':''},expected=400)
            self.request('GET','/data/workspace.sqlite3',expected=404)

    def test_02_edit_archive_restore_and_revision(self):
        project=self.project()
        changed=self.request('PUT','/api/projects/'+project['id'],{'revision':project['revision'],'status':'planning'})
        self.request('PUT','/api/projects/'+project['id'],{'revision':project['revision'],'feeling':'旧窗口'},expected=409)
        archived=self.request('DELETE','/api/projects/'+project['id'],{'revision':changed['revision']})
        self.assertTrue(archived['deleted'])
        state=self.request('GET','/api/state');self.assertNotIn(project['id'],[p['id'] for p in state['projects']])
        restored=self.request('POST','/api/projects/'+project['id']+'/restore',{'revision':archived['revision']})
        self.assertFalse(restored['deleted'])

    def test_03_upload_backup_conflicts_and_traversal(self):
        audio,image=self.fixture_assets()
        project=self.project(sourceId=audio['id'],clipEnd=2,scenes=[{'start':0,'end':2,'lyric':'把心事交给晚风','assetId':image['id']}])
        backup=self.request('GET','/api/backup')
        with ZipFile(io.BytesIO(backup)) as archive:
            self.assertIn('manifest.json',archive.namelist());self.assertGreater(len(archive.namelist()),2)
        self.request('PUT','/api/projects/'+project['id'],{'revision':project['revision'],'song':'本机新版本'})
        preview=self.request('POST','/api/backup/inspect',raw=backup)
        self.assertGreater(preview['conflictCount'],0)
        self.request('POST','/api/backup/restore',{'token':preview['token'],'strategy':'newer'})
        self.assertEqual(self.app.store.get('project',project['id'])['song'],'本机新版本')
        preview=self.request('POST','/api/backup/inspect',raw=backup)
        self.request('POST','/api/backup/restore',{'token':preview['token'],'strategy':'incoming'})
        self.assertEqual(self.app.store.get('project',project['id'])['song'],'集成验收歌曲')
        count=len(self.app.store.list('project'))
        preview=self.request('POST','/api/backup/inspect',raw=backup)
        self.request('POST','/api/backup/restore',{'token':preview['token'],'strategy':'copy'})
        self.assertGreater(len(self.app.store.list('project')),count)
        corrupt=io.BytesIO()
        with ZipFile(corrupt,'w') as archive:
            archive.writestr('../outside.txt','not allowed');archive.writestr('manifest.json','{}')
        self.request('POST','/api/backup/inspect',raw=corrupt.getvalue(),expected=400)

    def test_04_v6_migration_is_repeatable_without_duplicates(self):
        payload={'notes':[{'id':'note-v6','song':'旧版歌名','singer':'歌手','feeling':'一些感觉','reference':'49','createdAt':'2026-11-13T03:00:00Z','updatedAt':'2026-11-13T04:00:00Z'}],'favorites':['49'],'draft':{'song':'旧版草稿'}}
        self.assertEqual(self.request('POST','/api/migrate-v6',payload)['migrated'],1)
        self.assertTrue(self.request('POST','/api/migrate-v6',payload)['alreadyMigrated'])
        self.assertEqual(len([p for p in self.app.store.list('project') if p['id']=='note-v6']),1)
        self.assertEqual(self.app.store.get('project','note-v6')['createdAt'],'2026-11-13T03:00:00Z')

    def wait_job(self,job_id):
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            job=self.app.store.get('job',job_id)
            if job['status'] not in ['queued','running']: return job
            threading.Event().wait(.1)
        self.fail('Render did not finish in 90 seconds')

    def test_05_real_render_registers_work_and_task_package(self):
        if not self.app.media.ffmpeg:self.skipTest('ffmpeg unavailable')
        audio,image=self.fixture_assets()
        project=self.project(song='本机合成验收',sourceId=audio['id'],clipStart=.1,clipEnd=1.5,scenes=[{'start':0,'end':.7,'lyric':'沿着山路向远处走','assetId':image['id']},{'start':.7,'end':1.4,'lyric':'把心事交给晚风','assetId':image['id']}])
        package=self.request('GET','/api/projects/'+project['id']+'/package')
        with ZipFile(io.BytesIO(package)) as archive:
            self.assertIn('task.json',archive.namelist());self.assertIn('歌词时间轴.srt',archive.namelist())
            self.assertEqual(len([n for n in archive.namelist() if n.startswith('media/')]),2)
        job=self.request('POST','/api/projects/'+project['id']+'/render',{'revision':project['revision'],'quality':'540','subtitles':self.app.media.has_subtitles},expected=202)
        self.request('PUT','/api/projects/'+project['id'],{'revision':project['revision'],'song':'合成时不应修改'},expected=409)
        completed=self.wait_job(job['id'])
        self.assertEqual(completed['status'],'done',completed.get('error'))
        saved=self.app.store.get('project',project['id']);self.assertEqual(saved['status'],'done');self.assertEqual(saved['outputWorkId'],completed['workId'])
        work=self.app.store.get('work',completed['workId']);path=self.app.media.path(work['videoId'])
        info=self.app.media.probe(path);self.assertEqual((info['width'],info['height']),(540,960));self.assertTrue(info['hasAudio']);self.assertAlmostEqual(info['duration'],1.4,delta=.15)
        self.assertEqual(len(work['lyrics']),2)
        video=self.request('GET','/media/'+work['videoId'],headers={'Range':'bytes=0-31'},expected=206)
        self.assertEqual(len(video),32)

    def test_06_cancel_and_plan_validation(self):
        if not self.app.media.ffmpeg:self.skipTest('ffmpeg unavailable')
        audio,image=self.fixture_assets()
        project=self.project(sourceId=audio['id'],clipEnd=2,scenes=[{'start':.5,'end':2,'assetId':image['id']}])
        self.request('POST','/api/projects/'+project['id']+'/render',{'revision':project['revision']},expected=400)
        project=self.request('PUT','/api/projects/'+project['id'],{'revision':project['revision'],'scenes':[{'start':0,'end':2,'assetId':image['id']}]})
        job=self.request('POST','/api/projects/'+project['id']+'/render',{'revision':project['revision'],'subtitles':False},expected=202)
        self.request('POST','/api/jobs/'+job['id']+'/cancel',{})
        self.assertEqual(self.wait_job(job['id'])['status'],'cancelled')
        self.assertFalse(self.app.store.get('project',project['id'])['outputWorkId'])

    def test_07_portable_backup_into_fresh_directory(self):
        if not self.app.store.list('asset'): self.skipTest('No uploaded assets')
        backup=self.request('GET','/api/backup')
        with tempfile.TemporaryDirectory() as folder:
            fresh=Workspace(ROOT,Path(folder)/'restored')
            try:
                path=fresh.store.directory/'temp'/'portable.zip';path.write_bytes(backup)
                preview=fresh.backups.inspect(path)
                self.assertEqual(preview['conflictCount'],0)
                fresh.backups.restore(preview['token'],'newer')
                for asset in fresh.store.list('asset'):
                    self.assertEqual(fresh.media.digest(fresh.media.path(asset['id'])),asset['sha256'])
                for project in fresh.store.list('project'):
                    self.assertEqual(project['history'],self.app.store.get('project',project['id'])['history'])
                    if project.get('outputWorkId'):
                        work=fresh.store.get('work',project['outputWorkId'])
                        self.assertIsNotNone(work);self.assertTrue(fresh.media.path(work['videoId']).is_file())
                self.assertFalse(any(j['status'] in ['queued','running'] for j in fresh.store.list('job')))
            finally: fresh.close()

    def test_08_video_visual_loop_and_hd_output(self):
        if not self.app.media.ffmpeg:self.skipTest('ffmpeg unavailable')
        works=self.app.store.list('work')
        visual=next((w for w in works if w['title']=='本机合成验收'),None)
        if not visual:self.skipTest('Render fixture unavailable')
        audio,_=self.fixture_assets()
        project=self.project(song='视频画面循环与高清验收',sourceId=audio['id'],clipEnd=2,scenes=[{'start':0,'end':2,'assetId':visual['videoId'],'offset':.4}])
        job=self.request('POST','/api/projects/'+project['id']+'/render',{'revision':project['revision'],'quality':'1080','subtitles':False},expected=202)
        completed=self.wait_job(job['id']);self.assertEqual(completed['status'],'done',completed.get('error'))
        work=self.app.store.get('work',completed['workId']);info=self.app.media.probe(self.app.media.path(work['videoId']))
        self.assertEqual((info['width'],info['height']),(1080,1920));self.assertTrue(info['hasAudio']);self.assertAlmostEqual(info['duration'],2,delta=.15)


if __name__=='__main__': unittest.main()
