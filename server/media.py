"""Owned local assets and the bundled sample catalog; no remote fetching."""
from pathlib import Path
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess

from .store import AppError, ident

PROTOCOLS = ['-protocol_whitelist', 'file,pipe']
FORMATS = ['-format_whitelist', 'mov,mp3,wav,flac,ogg,matroska,avi,aac,image2,jpeg_pipe,png_pipe,webp_pipe']
HIDDEN = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
GROUPS = {3:'warm', 5:'warm', 6:'memory', 7:'quiet', 15:'warm', 17:'memory', 19:'quiet', 28:'travel', 37:'memory', 49:'travel'}


def run(command, **kwargs):
    return subprocess.run(command, capture_output=True, timeout=90, **HIDDEN, **kwargs)


class Media:
    def __init__(self, root, store):
        self.root = Path(root).resolve()
        self.store = store
        self.ffmpeg = shutil.which('ffmpeg')
        self.ffprobe = shutil.which('ffprobe')
        self.has_subtitles = False
        if self.ffmpeg:
            try:
                self.has_subtitles = ' subtitles ' in run([self.ffmpeg, '-hide_banner', '-filters']).stdout.decode('utf-8', 'replace')
            except (OSError, subprocess.TimeoutExpired):
                pass
        raw = (self.root / '界面/songs.js').read_text(encoding='utf-8')
        match = re.fullmatch(r'\s*window\.SONGSCENE_TRACKS\s*=\s*(\[.*\])\s*;?\s*', raw, re.S)
        self.tracks = json.loads(match[1]) if match else []
        self.stock = {}
        for track in self.tracks:
            work_id = str(track['id'])
            art = (self.root / track['artwork']).resolve()
            if art.is_relative_to(self.root) and art.is_file():
                self.stock[f'cover-{work_id}'] = {'id': f'cover-{work_id}', 'kind':'image', 'name':track['title']+' · 参考封面', 'file':str(art), 'width':600, 'height':600, 'duration':0, 'hasAudio':False, 'stock':True, 'bytes':art.stat().st_size, 'mime':'image/jpeg'}
            for key in ['hdVideo', 'video']:
                if not track.get(key):
                    continue
                path = (self.root / track[key]).resolve()
                if path.is_relative_to(self.root) and path.is_file():
                    self.stock[f'stock-{work_id}'] = {'id':f'stock-{work_id}', 'kind':'video', 'name':f'{track["title"]} · {track["artist"]}', 'file':str(path), 'width':1080 if key=='hdVideo' else 540, 'height':1920 if key=='hdVideo' else 960, 'duration':track['duration'], 'hasAudio':True, 'posterId':f'cover-{work_id}', 'stock':True, 'bytes':path.stat().st_size, 'mime':'video/mp4'}
                    break

    def public(self, asset):
        return {**{k:v for k,v in asset.items() if k!='file'}, 'url':f'/media/{asset["id"]}'}

    def assets(self):
        return [self.public(value) for value in self.stock.values()] + [self.public(value) for value in self.store.list('asset')]

    def get(self, item_id):
        return self.stock.get(item_id) or self.store.get('asset', item_id)

    def path(self, item_id):
        asset = self.get(item_id)
        if not asset:
            raise AppError('找不到这份素材，请重新导入或从完整备份恢复', 404)
        if asset.get('stock'):
            path = Path(asset['file']).resolve()
            safe = path.is_relative_to(self.root)
        else:
            path = (self.store.directory / asset['file']).resolve()
            safe = path.is_relative_to(self.store.directory / 'assets')
        if not safe or not path.is_file():
            raise AppError('素材文件不在工作目录中，请从完整备份恢复', 404)
        return path

    def probe(self, path):
        if not self.ffprobe:
            raise AppError('未找到FFprobe。请先安装FFmpeg并加入PATH，再导入音视频；需求管理仍可使用。')
        result = run([self.ffprobe, '-v', 'error', *PROTOCOLS, *FORMATS, '-show_entries', 'format=duration,format_name:stream=codec_type,width,height,duration', '-of', 'json', str(path)])
        if result.returncode:
            raise AppError('这份文件无法识别，请使用完整的MP4、MOV、WebM、MP3、WAV或图片文件')
        try:
            raw = json.loads(result.stdout)
            streams = raw.get('streams', [])
            visual = next((s for s in streams if s.get('codec_type')=='video'), {})
            duration = float(raw.get('format', {}).get('duration') or visual.get('duration') or 0)
            return {'width':int(visual.get('width',0)), 'height':int(visual.get('height',0)), 'duration':round(duration,3), 'hasAudio':any(s.get('codec_type')=='audio' for s in streams)}
        except (ValueError, TypeError, KeyError):
            raise AppError('素材信息无法读取，请换一个文件')

    def add_file(self, source, name, generated=False):
        source = Path(source).resolve()
        if not source.is_relative_to(self.store.directory):
            raise AppError('素材必须先复制到工作目录')
        name = Path(name.replace('\\','/')).name[:180]
        suffix = Path(name).suffix.lower()
        image = suffix in ['.jpg','.jpeg','.png','.webp']
        if suffix not in ['.mp4','.mov','.webm','.mkv','.mp3','.wav','.m4a','.flac','.ogg','.aac','.jpg','.jpeg','.png','.webp']:
            raise AppError('暂不支持这种文件，请导入音频、视频或JPG/PNG/WebP图片')
        if image:
            with source.open('rb') as image_file:
                header=image_file.read(16)
            if not (header.startswith(b'\xff\xd8\xff') or header.startswith(b'\x89PNG\r\n\x1a\n') or (header.startswith(b'RIFF') and header[8:12]==b'WEBP')):
                raise AppError('图片内容与文件格式不符')
        info = self.probe(source)
        if image and (not info['width'] or max(info['width'],info['height']) > 10000):
            raise AppError('图片尺寸不支持，请使用宽高均不超过10000像素的图片')
        if not image and not 0 < info['duration'] <= 7200:
            raise AppError('音视频需要有有效时长，且不超过两小时')
        digest = self.digest(source)
        for asset in self.store.list('asset'):
            if asset.get('sha256') == digest and (self.store.directory / asset['file']).is_file():
                return asset
        item_id = ident('a')
        target = self.store.directory / 'assets' / (item_id + suffix)
        shutil.copyfile(source, target)
        kind = 'image' if image else 'video' if info['width'] else 'audio'
        record = {'name':name, 'file':target.relative_to(self.store.directory).as_posix(), 'kind':kind, **info, 'duration':0 if image else info['duration'], 'bytes':target.stat().st_size, 'sha256':digest, 'mime':mimetypes.guess_type(name)[0] or 'application/octet-stream', 'stock':False}
        asset = self.store.save('asset',item_id,record, snapshot=False)
        if kind=='video' and self.ffmpeg and not generated:
            poster = self.make_poster(item_id)
            if poster:
                asset = self.store.save('asset',item_id,{'posterId':poster['id']},force=True,snapshot=False)
        return asset

    @staticmethod
    def digest(path):
        result=hashlib.sha256()
        with Path(path).open('rb') as file:
            for chunk in iter(lambda:file.read(1024*1024),b''):
                result.update(chunk)
        return result.hexdigest()

    def make_poster(self, item_id):
        if not self.ffmpeg:
            return None
        source=self.path(item_id)
        destination=self.store.directory/'temp'/(ident('poster')+'.jpg')
        result=run([self.ffmpeg,'-v','error',*PROTOCOLS,*FORMATS,'-i',str(source),'-frames:v','1','-vf','scale=640:-2','-q:v','3','-y',str(destination)])
        try:
            return self.add_file(destination, '自动封面.jpg', True) if result.returncode==0 and destination.is_file() else None
        finally:
            destination.unlink(missing_ok=True)

    def check_project(self, project, require_plan=False):
        source=self.get(project.get('sourceId',''))
        if not source or not source.get('hasAudio'):
            raise AppError('请先选择带声音的歌曲或视频素材')
        self.path(source['id'])
        if project['clipEnd'] > source['duration'] + .02:
            raise AppError('所选片段超过歌曲时长，请调整结束时间')
        if not require_plan:
            return
        duration=project['clipEnd']-project['clipStart']
        rows=sorted(project['scenes'],key=lambda x:x['start'])
        if not rows:
            raise AppError('请先为歌词安排画面')
        cursor=0
        for index,row in enumerate(rows):
            if abs(row['start']-cursor) > .04:
                raise AppError(f'第{index+1}段画面与上一段之间有空隙或重叠，请对齐时间')
            asset=self.get(row['assetId'])
            if not asset or asset['kind'] not in ['image','video']:
                raise AppError(f'请给第{index+1}段选择图片或视频')
            self.path(asset['id'])
            if asset['kind']=='video' and row.get('offset',0) >= asset['duration']:
                raise AppError(f'第{index+1}段素材起点超出了视频时长')
            cursor=row['end']
        if abs(cursor-duration) > .04:
            raise AppError('画面方案总时长需要与所选歌曲片段一致')

    def builtin_works(self):
        result=[]
        for track in self.tracks:
            item_id=str(track['id'])
            result.append({**track,'id':item_id,'group':GROUPS.get(track['id'],'warm'),'videoId':f'stock-{item_id}' if f'stock-{item_id}' in self.stock else '', 'posterId':f'cover-{item_id}','stock':True})
        return result
