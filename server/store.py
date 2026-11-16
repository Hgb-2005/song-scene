"""Validated documents, optimistic updates and recoverable disk snapshots."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import json
import math
import os
import re
import sqlite3
import threading
import uuid


class AppError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def ident(prefix='p'):
    return f'{prefix}-{uuid.uuid4().hex}'


def text(value, limit=300, required=False):
    if not isinstance(value, str) or len(value) > limit:
        raise AppError(f'文字内容需在{limit}字以内')
    value = value.strip()
    if required and not value:
        raise AppError('请先填写歌名或作品名称')
    return value


def number(value, low=0, high=86400):
    try: finite=math.isfinite(value) if isinstance(value,(int,float)) else False
    except OverflowError: finite=False
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not finite or not low <= value <= high:
        raise AppError('时间或数值不在有效范围内')
    return round(value, 3)


def valid_id(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value) is not None


def normalize(kind, data, previous=None):
    previous = previous or {}
    if not isinstance(data, dict):
        raise AppError('数据格式不正确')
    if kind == 'project':
        status = data.get('status', 'idea')
        if status not in ['idea', 'planning', 'making', 'done']:
            raise AppError('制作状态不正确')
        start = number(data.get('clipStart', 0))
        end = number(data.get('clipEnd', 30))
        if not 0.2 <= end - start <= 120:
            raise AppError('请选择0.2至120秒的歌曲片段')
        rows = data.get('scenes', [])
        if not isinstance(rows, list) or len(rows) > 60:
            raise AppError('每个项目最多60段画面')
        scenes = []
        for row in rows:
            if not isinstance(row, dict):
                raise AppError('画面方案格式不正确')
            a, b = number(row.get('start', 0), high=120), number(row.get('end', 5), high=120)
            if b <= a:
                raise AppError('每段画面的结束时间必须晚于开始时间')
            scenes.append({'id': row.get('id') if valid_id(row.get('id')) else ident('s'), 'start': a, 'end': b, 'lyric': text(row.get('lyric', ''), 120), 'intent': text(row.get('intent', ''), 500), 'assetId': text(row.get('assetId', ''), 100), 'offset': number(row.get('offset', 0)), 'cropX':number(row.get('cropX', .5),0,1), 'cropY':number(row.get('cropY', .5),0,1)})
        from .composition import caption_settings
        caption = caption_settings(data.get('caption'))
        output = text(data.get('outputWorkId', ''), 100)
        if status == 'done' and not output:
            raise AppError('请先关联或导入成片，再标记完成')
        history = previous.get('history', [])[:]
        if not previous or status != previous.get('status'):
            history.append({'at': now(), 'status': status})
        return {'song': text(data.get('song', ''), 80, True), 'singer': text(data.get('singer', ''), 80), 'feeling': text(data.get('feeling', ''), 300), 'reference': text(data.get('reference', ''), 100), 'status': status, 'sourceId': text(data.get('sourceId', ''), 100), 'clipStart': start, 'clipEnd': end, 'scenes': scenes, 'caption':caption, 'lyricDraft':text(data.get('lyricDraft',''),6000), 'outputWorkId': output, 'history': history[-100:]}
    if kind == 'work':
        group = data.get('group', 'warm')
        if group not in ['warm', 'travel', 'memory', 'quiet']:
            raise AppError('作品分类不正确')
        lyrics = data.get('lyrics', [])
        if not isinstance(lyrics, list) or len(lyrics) > 100:
            raise AppError('歌词数据不正确')
        duration = number(data.get('duration', 0))
        cleaned = []
        for line in lyrics:
            a, b = number(line.get('t0', 0)), number(line.get('t1', 0))
            if b <= a or b > duration + .1:
                raise AppError('歌词时间超出作品范围')
            cleaned.append({'text': text(line.get('text', ''), 120), 't0': a, 't1': b})
        return {'title': text(data.get('title', ''), 80, True), 'artist': text(data.get('artist', ''), 80), 'requestedArtist': text(data.get('requestedArtist', ''), 80), 'isCover': bool(data.get('isCover', False)), 'group': group, 'mood': text(data.get('mood', ''), 40), 'expression': text(data.get('expression', ''), 300), 'story': text(data.get('story', ''), 1000), 'videoId': text(data.get('videoId', ''), 100, True), 'posterId': text(data.get('posterId', ''), 100), 'duration': duration, 'projectId': text(data.get('projectId', ''), 100), 'lyrics': cleaned}
    if kind == 'draft':
        return {'song': text(data.get('song', ''), 80), 'singer': text(data.get('singer', ''), 80), 'feeling': text(data.get('feeling', ''), 300), 'reference': text(data.get('reference', ''), 100)}
    if kind == 'preferences':
        result = {}
        for key in ['favorites', 'recent']:
            values = data.get(key, [])
            if not isinstance(values, list) or len(values) > 10000 or not all(isinstance(v, str) and len(v) <= 100 for v in values):
                raise AppError('收藏或观看记录格式不正确')
            result[key] = list(dict.fromkeys(values))
        return result
    if kind in ['asset', 'job', 'setting']:
        return {k: v for k, v in data.items() if k not in ['id', 'revision', 'updatedAt', 'createdAt', 'deleted']}
    raise AppError('不支持的数据类型')


class Store:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        for child in ['assets', 'backups', 'temp', 'renders']:
            (self.directory / child).mkdir(exist_ok=True)
        self.path = self.directory / 'workspace.sqlite3'
        self.lock = threading.RLock()
        self.last_backup_error = ''
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS documents(kind TEXT NOT NULL,id TEXT NOT NULL,body TEXT NOT NULL,revision INTEGER NOT NULL,PRIMARY KEY(kind,id))')
            db.execute('PRAGMA user_version=1')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _get(db, kind, item_id):
        row = db.execute('SELECT body FROM documents WHERE kind=? AND id=?', (kind, item_id)).fetchone()
        return json.loads(row[0]) if row else None

    def get(self, kind, item_id, include_deleted=False):
        with self.connection() as db:
            value = self._get(db, kind, item_id)
        return value if value and (include_deleted or not value.get('deleted')) else None

    def list(self, kind=None, include_deleted=False):
        with self.connection() as db:
            rows = db.execute('SELECT kind,body FROM documents' + (' WHERE kind=?' if kind else ''), (kind,) if kind else ()).fetchall()
        values = []
        for row_kind, body in rows:
            value = json.loads(body)
            if include_deleted or not value.get('deleted'):
                values.append(value if kind else {'kind': row_kind, 'value': value})
        return values

    def _save(self, db, kind, item_id, changes, expected=None, force=False):
        if not valid_id(item_id):
            raise AppError('记录编号不正确')
        old = self._get(db, kind, item_id)
        if old and not force and expected != old['revision']:
            raise AppError('这份内容已在另一个窗口更新。请刷新后重新编辑，当前修改不会覆盖磁盘记录。', 409)
        if not old and expected not in [None, 0] and not force:
            raise AppError('这份记录已不存在，请重新加载', 409)
        merged = {**(old or {}), **changes}
        value = normalize(kind, merged, old)
        value.update({'id': item_id, 'revision': (old or {}).get('revision', 0) + 1, 'createdAt': (old or {}).get('createdAt', now()), 'updatedAt': now(), 'deleted': bool(merged.get('deleted', False))})
        db.execute('INSERT INTO documents(kind,id,body,revision) VALUES(?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body,revision=excluded.revision', (kind, item_id, json.dumps(value, ensure_ascii=False), value['revision']))
        return value

    def save(self, kind, item_id, changes, expected=None, force=False, snapshot=True):
        return self.save_many([(kind, item_id, changes, expected, force)], snapshot)[0]

    def save_many(self, operations, snapshot=True):
        with self.lock:
            with self.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                results = [self._save(db, *operation) for operation in operations]
            if snapshot:
                try:
                    self.snapshot()
                    self.last_backup_error = ''
                except OSError:
                    self.last_backup_error = '记录已保存，但自动快照失败。请检查磁盘空间并导出完整备份。'
        return results

    def snapshot(self):
        """Records only; a full export also includes uploaded media."""
        payload = {'format': 'songscene-disk-snapshot', 'version': 1, 'at': now(), 'documents': self.list(include_deleted=True)}
        name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
        folder = self.directory / 'backups'
        temp = folder / f'{name}.tmp'
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temp, folder / f'{name}.json')
        for old in sorted(folder.glob('*.json'))[:-30]:
            if old.resolve().parent == folder.resolve():
                old.unlink()

    def state(self):
        return {'projects': self.list('project'), 'works': self.list('work'), 'draft': self.get('draft', 'main'), 'preferences': self.get('preferences', 'main'), 'jobs': sorted(self.list('job'), key=lambda x: x['createdAt'], reverse=True)[:30], 'trash': [p for p in self.list('project', True) if p.get('deleted')], 'backupWarning':self.last_backup_error}

    def import_documents(self, entries):
        with self.lock:
            with self.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                for entry in entries:
                    kind, incoming = entry['kind'], entry['value']
                    value = self._save(db,kind,incoming['id'],incoming,None,True)
                    for key in ['createdAt','updatedAt']:
                        stamp=incoming.get(key)
                        if isinstance(stamp,str):
                            try:
                                datetime.fromisoformat(stamp.replace('Z','+00:00'))
                                value[key]=stamp
                            except ValueError:
                                pass
                    if kind=='project' and 'history' in incoming:
                        history=incoming['history']
                        if not isinstance(history,list) or len(history)>100:
                            raise AppError('备份中的制作记录格式不正确')
                        for event in history:
                            if not isinstance(event,dict) or event.get('status') not in ['idea','planning','making','done'] or not isinstance(event.get('at'),str):
                                raise AppError('备份中的制作记录格式不正确')
                            try: datetime.fromisoformat(event['at'].replace('Z','+00:00'))
                            except ValueError: raise AppError('备份中的制作记录时间不正确')
                        value['history']=history
                    db.execute('UPDATE documents SET body=? WHERE kind=? AND id=?',(json.dumps(value,ensure_ascii=False),kind,value['id']))
            try:
                self.snapshot()
            except OSError:
                self.last_backup_error='导入已保存，但自动快照失败，请检查磁盘空间'

    def migrate_v6(self, payload):
        with self.lock:
            if self.get('setting', 'v6-migration'):
                return {'migrated': 0, 'alreadyMigrated': True}
            notes=payload.get('notes',[])
            if not isinstance(notes,list) or len(notes)>1000:
                raise AppError('V6备份格式不正确')
            entries=[]
            for note in notes:
                if not isinstance(note,dict): raise AppError('V6需求格式不正确')
                item_id=note.get('id') if valid_id(note.get('id')) else ident()
                if not self.get('project',item_id,True):
                    value={**note,'id':item_id,'reference':str(note.get('reference',''))}
                    entries.append({'kind':'project','value':value})
            if payload.get('draft') and not self.get('draft','main'):
                entries.append({'kind':'draft','value':{**payload['draft'],'id':'main'}})
            if not self.get('preferences','main'):
                entries.append({'kind':'preferences','value':{'id':'main','favorites':payload.get('favorites',[]),'recent':payload.get('recent',[])}})
            entries.append({'kind':'setting','value':{'id':'v6-migration','completed':True}})
            self.import_documents(entries)
            return {'migrated':sum(entry['kind']=='project' for entry in entries)}
