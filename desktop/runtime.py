from pathlib import Path
import json
import os
import sys

VERSION='8.0.0'


def resource_root():
    return Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1])).resolve()


def user_directory():
    base=Path(os.environ.get('LOCALAPPDATA') or Path.home()/'.local/share')
    return base/'SongScene'


def data_directory():
    return user_directory()/'data'


class InstanceLock:
    """OS releases the lock after a crash; the endpoint file never controls a process."""
    def __init__(self,directory):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.file=None

    def acquire(self):
        self.file=(self.directory/'desktop.lock').open('a+b')
        self.file.seek(0);self.file.write(b'0');self.file.flush();self.file.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file,fcntl.LOCK_EX|fcntl.LOCK_NB)
            return True
        except OSError:
            self.file.close();self.file=None;return False

    def publish(self,port):
        if not self.file:raise RuntimeError('Instance lock is not owned')
        target=self.directory/'desktop-endpoint.json'
        temp=target.with_suffix('.tmp')
        temp.write_text(json.dumps({'port':port}),encoding='utf-8');os.replace(temp,target)

    def existing_url(self):
        from urllib.request import urlopen
        try:
            port=json.loads((self.directory/'desktop-endpoint.json').read_text(encoding='utf-8')).get('port')
            if isinstance(port,bool) or not isinstance(port,int) or not 1024<=port<=65535:return None
            base=f'http://127.0.0.1:{port}'
            with urlopen(base+'/api/state',timeout=2) as response:
                state=json.load(response)
            if state.get('application')=='songscene' and Path(state.get('dataDirectory','')).resolve()==self.directory.resolve():
                return base+'/index.html'
        except (OSError,ValueError,TypeError):pass
        return None

    def close(self):
        if self.file:
            (self.directory/'desktop-endpoint.json').unlink(missing_ok=True)
            self.file.close();self.file=None
