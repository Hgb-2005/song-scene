from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
import hashlib
import io
import os
import tempfile
import threading
import unittest

from desktop.runtime import InstanceLock,data_directory,resource_root
from desktop import engine


class Response(io.BytesIO):
    def __init__(self,data):super().__init__(data);self.headers={'Content-Length':str(len(data))}


class DesktopTests(unittest.TestCase):
    def test_data_survives_install_location_change_and_instance_lock_recovers(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'LOCALAPPDATA':directory}):
            data=data_directory();self.assertEqual(data,Path(directory)/'SongScene/data')
            self.assertFalse(data.is_relative_to(resource_root()))
            first=InstanceLock(data);second=InstanceLock(data)
            try:
                self.assertTrue(first.acquire());self.assertFalse(second.acquire())
                first.close();self.assertTrue(second.acquire())
                (data/'saved-work.txt').write_text('keep',encoding='utf-8')
            finally:first.close();second.close()
            self.assertEqual((data/'saved-work.txt').read_text(encoding='utf-8'),'keep')

    def test_engine_hash_failure_and_cancel_leave_no_partial_engine(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'LOCALAPPDATA':directory}):
            with self.assertRaisesRegex(RuntimeError,'校验'):
                engine.provision(lambda *args:None,threading.Event(),opener=lambda *a,**k:Response(b'corrupt'))
            self.assertFalse(engine.engine_directory().exists())
            cancel=threading.Event();cancel.set()
            with self.assertRaises(InterruptedError):engine.provision(lambda *args:None,cancel,opener=lambda *a,**k:Response(b'cancelled'))
            self.assertEqual(list(engine.engine_directory().parent.glob('setup-*')),[])

    def test_verified_engine_extracts_atomically_and_rejects_traversal(self):
        for traversal in [False,True]:
            data=io.BytesIO()
            with ZipFile(data,'w') as archive:
                for name in ['ffmpeg.exe','ffprobe.exe']:
                    archive.writestr(f'ffmpeg-{engine.ENGINE_VERSION}-essentials_build/bin/{name}',b'fixture-not-executable')
                archive.writestr('../outside.txt' if traversal else 'LICENSE.txt',b'fixture')
            raw=data.getvalue()
            with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'LOCALAPPDATA':directory}),patch.object(engine,'ENGINE_SHA256',hashlib.sha256(raw).hexdigest()):
                if traversal:
                    with self.assertRaisesRegex(RuntimeError,'路径'):engine.provision(lambda *a:None,threading.Event(),opener=lambda *a,**k:Response(raw))
                    self.assertFalse(engine.engine_directory().exists())
                else:
                    tools=engine.provision(lambda *a:None,threading.Event(),opener=lambda *a,**k:Response(raw))
                    self.assertTrue(all(Path(f).is_file() for f in tools))
                    self.assertTrue((engine.engine_directory()/'download-receipt.json').is_file())


if __name__=='__main__':unittest.main()
