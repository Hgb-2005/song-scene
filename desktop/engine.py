"""Fetch an unchanged, pinned upstream tool; do not redistribute third-party binaries."""
from pathlib import Path
from urllib.request import Request,urlopen
from zipfile import ZipFile
import hashlib
import json
import os
import shutil
import subprocess
import tempfile

from .runtime import user_directory

ENGINE_VERSION='9.0.2'
ENGINE_URL='https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip'
ENGINE_SHA256='60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba'
HIDDEN={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}


def engine_directory():
    return user_directory()/'engine'/ENGINE_VERSION


def find_tools():
    cached=engine_directory()/f'ffmpeg-{ENGINE_VERSION}-essentials_build'/'bin'
    if all((cached/name).is_file() for name in ['ffmpeg.exe','ffprobe.exe']):
        return str(cached/'ffmpeg.exe'),str(cached/'ffprobe.exe')
    return shutil.which('ffmpeg'),shutil.which('ffprobe')


def usable_tools():
    ffmpeg,ffprobe=find_tools()
    if not ffmpeg or not ffprobe:return False
    try:
        filters=subprocess.run([ffmpeg,'-hide_banner','-filters'],capture_output=True,timeout=15,**HIDDEN)
        encoders=subprocess.run([ffmpeg,'-hide_banner','-encoders'],capture_output=True,timeout=15,**HIDDEN)
        probe=subprocess.run([ffprobe,'-version'],capture_output=True,timeout=15,**HIDDEN)
        return probe.returncode==0 and b' subtitles ' in filters.stdout and b'libx264' in encoders.stdout
    except (OSError,subprocess.TimeoutExpired):return False


def provision(progress,cancel,opener=urlopen):
    destination=engine_directory();destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists():
        raise RuntimeError('现有引擎无法使用，请将引擎文件夹改名后重试：'+str(destination))
    # TemporaryDirectory owns cleanup, including partial downloads after a cancellation.
    with tempfile.TemporaryDirectory(prefix='setup-',dir=destination.parent) as directory:
        staging=Path(directory);archive_path=staging/'engine.zip';digest=hashlib.sha256();received=0
        request=Request(ENGINE_URL,headers={'User-Agent':'SongScene/8 desktop setup'})
        with opener(request,timeout=30) as response,archive_path.open('wb') as output:
            total=int(response.headers.get('Content-Length',0))
            if total>1024**3:raise RuntimeError('引擎下载大小异常')
            while True:
                if cancel.is_set():raise InterruptedError('已取消引擎准备')
                chunk=response.read(1024*1024)
                if not chunk:break
                received+=len(chunk)
                if received>1024**3:raise RuntimeError('引擎下载大小异常')
                digest.update(chunk);output.write(chunk)
                progress(f'首次准备视频引擎 · {received//1024//1024} MB'+(f' / {total//1024//1024} MB' if total else ''),received/total*90 if total else 5)
        if digest.hexdigest()!=ENGINE_SHA256:raise RuntimeError('下载校验未通过，文件已丢弃。请稍后重试。')
        progress('校验通过，正在解压视频引擎……',92)
        unpacked=staging/'unpacked';unpacked.mkdir()
        with ZipFile(archive_path) as archive:
            members=archive.infolist()
            if len(members)>5000 or sum(m.file_size for m in members)>2*1024**3:raise RuntimeError('引擎压缩包大小异常')
            for item in members:
                target=(unpacked/item.filename.replace('\\','/')).resolve()
                if not target.is_relative_to(unpacked.resolve()) or item.external_attr>>16&0o170000==0o120000:
                    raise RuntimeError('引擎压缩包路径不安全')
                if cancel.is_set():raise InterruptedError('已取消引擎准备')
                archive.extract(item,unpacked)
        expected=unpacked/f'ffmpeg-{ENGINE_VERSION}-essentials_build'/'bin'
        if not all((expected/name).is_file() for name in ['ffmpeg.exe','ffprobe.exe']):raise RuntimeError('引擎压缩包缺少程序文件')
        (unpacked/'download-receipt.json').write_text(json.dumps({'url':ENGINE_URL,'sha256':ENGINE_SHA256,'version':ENGINE_VERSION},indent=2),encoding='utf-8')
        os.replace(unpacked,destination)
        progress('视频引擎已就绪',100)
    return find_tools()
