"""Portable full backups and explicit, reviewed conflict resolution."""
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, BadZipFile, ZIP_DEFLATED, ZIP_STORED
import json
import os
import shutil
import threading
import time

from .store import AppError, ident, normalize, valid_id, now

KINDS={'project','work','draft','preferences','asset'}


def stamp(value):
    try:
        parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return parsed.replace(tzinfo=timezone.utc).timestamp() if parsed.tzinfo is None else parsed.timestamp()
    except (ValueError,TypeError):
        return 0


class Backups:
    def __init__(self, store, media):
        self.store=store
        self.media=media
        self.pending={}
        self.lock=threading.RLock()

    def export(self):
        target=self.store.directory/'temp'/(ident('backup')+'.zip')
        with self.store.lock:
            documents=[entry for entry in self.store.list(include_deleted=True) if entry['kind'] in KINDS]
            manifest={'format':'songscene-workspace','version':2,'exportedAt':now(),'documents':documents}
            with ZipFile(target,'w') as archive:
                archive.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2),compress_type=ZIP_DEFLATED)
                for entry in documents:
                    if entry['kind']=='asset':
                        asset=entry['value']
                        path=self.media.path(asset['id'])
                        archive.write(path,asset['file'],compress_type=ZIP_STORED if path.suffix.lower() in ['.mp4','.mov','.mp3','.m4a','.webm'] else ZIP_DEFLATED)
        return target

    def _read(self, path):
        try:
            with path.open('rb') as first:
                is_json=first.read(64).removeprefix(b'\xef\xbb\xbf').lstrip().startswith(b'{')
            if is_json:
                if path.stat().st_size>8*1024*1024:
                    raise AppError('JSON备份超过8MB，请选择完整ZIP备份')
                payload=json.loads(path.read_text(encoding='utf-8-sig'))
                if payload.get('format')=='songscene-personal-backup' and payload.get('version')==1:
                    notes=payload.get('notes',[])
                    if not isinstance(notes,list) or len(notes)>1000:
                        raise AppError('V6需求数据不正确')
                    documents=[]
                    for note in notes:
                        value=normalize('project',note)
                        value.update({'id':note.get('id') if valid_id(note.get('id')) else ident(), 'createdAt':note.get('createdAt',now()),'updatedAt':note.get('updatedAt',now())})
                        documents.append({'kind':'project','value':value})
                    if isinstance(payload.get('draft'),dict):
                        documents.append({'kind':'draft','value':{**normalize('draft',payload['draft']),'id':'main'}})
                    documents.append({'kind':'preferences','value':{**normalize('preferences',{'favorites':payload.get('favorites',[])}),'id':'main'}})
                    return documents,False
                if payload.get('format')=='songscene-disk-snapshot' and payload.get('version')==1:
                    return payload.get('documents',[]),False
                raise AppError('无法识别这份JSON备份')
            with ZipFile(path) as archive:
                infos=archive.infolist()
                if len(infos)>10000 or sum(i.file_size for i in infos)>4*1024**3 or len({i.filename for i in infos})!=len(infos):
                    raise AppError('备份文件过大或含重复条目')
                for info in infos:
                    parts=PurePosixPath(info.filename)
                    if parts.is_absolute() or '..' in parts.parts or '\\' in info.filename or info.flag_bits&1:
                        raise AppError('备份包含不安全的文件路径')
                    if info.filename!='manifest.json' and (len(parts.parts)!=2 or parts.parts[0]!='assets' or info.is_dir()):
                        raise AppError('备份包含不支持的文件')
                if archive.getinfo('manifest.json').file_size>8*1024*1024:
                    raise AppError('备份清单过大')
                manifest=json.loads(archive.read('manifest.json'))
                if manifest.get('format')!='songscene-workspace' or manifest.get('version')!=2:
                    raise AppError('不是受支持的一歌一景完整备份')
                return manifest.get('documents',[]),True
        except (BadZipFile,KeyError,UnicodeError,json.JSONDecodeError):
            raise AppError('备份损坏或格式不正确，当前数据没有更改')

    def inspect(self, path):
        path=Path(path)
        entries,zipped=self._read(path)
        if not isinstance(entries,list) or len(entries)>12000:
            raise AppError('备份记录数量或格式不正确')
        seen=set()
        cleaned=[]
        conflicts=[]
        incoming_assets={}
        with ZipFile(path) if zipped else _EmptyArchive() as archive:
            for entry in entries:
                if not isinstance(entry,dict) or entry.get('kind') not in KINDS:
                    continue
                kind,value=entry['kind'],entry.get('value')
                if not isinstance(value,dict) or not valid_id(value.get('id')) or (kind,value['id']) in seen:
                    raise AppError('备份包含无效或重复记录')
                seen.add((kind,value['id']))
                if kind=='asset':
                    relative=value.get('file','')
                    file=PurePosixPath(relative)
                    if len(file.parts)!=2 or file.parts[0]!='assets' or file.stem!=value['id'] or file.suffix.lower() not in ['.mp4','.mov','.webm','.mkv','.mp3','.wav','.m4a','.flac','.ogg','.aac','.jpg','.jpeg','.png','.webp'] or not isinstance(value.get('sha256'),str) or len(value['sha256'])!=64 or value.get('kind') not in ['audio','video','image']:
                        raise AppError('备份素材路径或信息不正确')
                    if zipped:
                        try: info=archive.getinfo(relative)
                        except KeyError: raise AppError('备份中缺少清单列出的素材文件')
                        if info.file_size!=value.get('bytes') or info.file_size>1024**3:
                            raise AppError('备份素材大小与清单不符')
                    elif not (self.store.directory/relative).is_file():
                        raise AppError('这份记录快照需要原素材文件。请改用包含素材的完整ZIP备份。')
                    incoming_assets[value['id']]=value
                else:
                    normalize(kind,value)
                old=self.store.get(kind,value['id'],True)
                if old and kind in ['project','work']:
                    conflicts.append({'kind':kind,'id':value['id'],'title':value.get('song') or value.get('title'),'localUpdated':old.get('updatedAt'),'incomingUpdated':value.get('updatedAt')})
                cleaned.append({'kind':kind,'value':value})
        for entry in cleaned:
            kind,value=entry['kind'],entry['value']
            refs=[]
            if kind=='project':
                refs=[value.get('sourceId','')]+[s.get('assetId','') for s in value.get('scenes',[])]
            elif kind=='work':
                refs=[value.get('videoId',''),value.get('posterId','')]
            for ref in filter(None,refs):
                if ref not in incoming_assets and not self.media.get(ref):
                    raise AppError('备份依赖当前包未包含的参考视频，请在完整版中导入这份备份')
        token=ident('restore')
        with self.lock:
            for key,pending in list(self.pending.items()):
                if time.time()-pending['time']>1800:
                    pending['path'].unlink(missing_ok=True)
                    del self.pending[key]
            self.pending[token]={'path':path,'entries':cleaned,'zipped':zipped,'time':time.time()}
        return {'token':token,'projects':sum(e['kind']=='project' for e in cleaned),'works':sum(e['kind']=='work' for e in cleaned),'assets':len(incoming_assets),'conflicts':conflicts[:50],'conflictCount':len(conflicts)}

    def restore(self, token, strategy):
        if strategy not in ['local','newer','incoming','copy']:
            raise AppError('请选择如何处理同编号记录')
        with self.lock,self.store.lock:
            pending=self.pending.get(token)
            if not pending or time.time()-pending['time']>1800:
                raise AppError('备份预览已过期，请重新选择文件')
            entries=json.loads(json.dumps(pending['entries']))
            remap={}
            asset_map={}
            extracted=[]
            for entry in entries:
                kind,value=entry['kind'],entry['value']
                old=self.store.get(kind,value['id'],True)
                if kind=='asset' and old and old.get('sha256')!=value['sha256']:
                    asset_map[value['id']]=ident('a')
                if strategy=='copy' and kind in ['project','work'] and old:
                    remap[value['id']]=ident('p' if kind=='project' else 'w')
            operations=[]
            try:
                with ZipFile(pending['path']) if pending['zipped'] else _EmptyArchive() as archive:
                    for entry in entries:
                        kind,value=entry['kind'],entry['value']
                        if kind=='asset':
                            old_id=value['id']; new_id=asset_map.get(old_id,old_id)
                            old_relative=value['file']
                            value['id']=new_id
                            value['file']='assets/'+new_id+Path(old_relative).suffix.lower()
                            destination=(self.store.directory/value['file']).resolve()
                            if not destination.is_relative_to(self.store.directory/'assets'):
                                raise AppError('素材目标路径不正确')
                            if pending['zipped'] and not destination.exists():
                                temporary=self.store.directory/'temp'/(ident('restore-asset')+destination.suffix)
                                with archive.open(old_relative) as source, temporary.open('wb') as output:
                                    shutil.copyfileobj(source,output,1024*1024)
                                if self.media.digest(temporary)!=value['sha256']:
                                    temporary.unlink(missing_ok=True)
                                    raise AppError('备份中的素材校验失败，当前记录没有更改')
                                os.replace(temporary,destination); extracted.append(destination)
                            elif destination.exists() and self.media.digest(destination)!=value['sha256']:
                                raise AppError('本机素材与备份不一致，已停止恢复以保护文件')
                            if value.get('posterId'):
                                value['posterId']=asset_map.get(value['posterId'],value['posterId'])
                            if not self.store.get('asset',new_id,True):
                                operations.append(entry)
                            continue
                        old=self.store.get(kind,value['id'],True)
                        if old:
                            if strategy=='local' or (strategy=='newer' and stamp(old.get('updatedAt'))>=stamp(value.get('updatedAt'))):
                                continue
                            if strategy=='copy' and kind not in ['project','work']:
                                continue
                        value['id']=remap.get(value['id'],value['id'])
                        for field in ['sourceId','videoId','posterId']:
                            if value.get(field): value[field]=asset_map.get(value[field],value[field])
                        for field in ['projectId','outputWorkId','reference']:
                            if value.get(field): value[field]=remap.get(value[field],value[field])
                        for scene in value.get('scenes',[]):
                            scene['assetId']=asset_map.get(scene.get('assetId',''),scene.get('assetId',''))
                        if kind=='preferences':
                            for key in ['favorites','recent']:
                                value[key]=[remap.get(v,v) for v in value.get(key,[])]
                        operations.append(entry)
                self.store.import_documents(operations)
            except Exception:
                for file in extracted:
                    file.unlink(missing_ok=True)
                raise
            self.pending.pop(token,None); pending['path'].unlink(missing_ok=True)
            return {'restored':sum(e['kind'] in ['project','work'] for e in operations),'message':'备份已合并到磁盘工作目录'}


class _EmptyArchive:
    def __enter__(self): return self
    def __exit__(self,*args): return False
