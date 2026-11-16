"""Same-origin, loopback-only HTTP API and portable static/media serving."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED
import json
import mimetypes
import re
import secrets
import shutil
import traceback

from .store import AppError, Store, ident, now
from .media import Media
from .backup import Backups
from .render import Renderer


def srt(scenes):
    def at(value):
        ms=round(value*1000)
        return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
    return '\n\n'.join(f'{index+1}\n{at(row["start"])} --> {at(row["end"])}\n{row["lyric"]}' for index,row in enumerate(scenes) if row.get('lyric'))+'\n'


class Workspace:
    def __init__(self, root, data):
        self.root=Path(root).resolve()
        self.store=Store(data)
        identity=self.store.get('setting','workspace-identity')
        if not identity: identity=self.store.save('setting','workspace-identity',{'key':ident('workspace')},snapshot=False)
        self.identity=identity['key']
        self.media=Media(root,self.store)
        self.backups=Backups(self.store,self.media)
        self.renderer=Renderer(self.store,self.media)
        self.token=secrets.token_urlsafe(32)

    def state(self):
        return {**self.store.state(),'workspaceId':self.identity,'stockWorks':self.media.builtin_works(),'assets':self.media.assets(),'token':self.token,'version':7,'capabilities':{'ffmpeg':bool(self.media.ffmpeg),'ffprobe':bool(self.media.ffprobe),'subtitles':self.media.has_subtitles},'snapshotCount':len(list((self.store.directory/'backups').glob('*.json')))}

    def project(self,item_id,deleted=False):
        result=self.store.get('project',item_id,deleted)
        if not result: raise AppError('找不到这份需求',404)
        return result

    def task_package(self,project):
        target=self.store.directory/'temp'/(ident('task')+'.zip')
        refs={project.get('sourceId','')} | {s.get('assetId','') for s in project['scenes']}
        assets=[]
        rows=sorted(project['scenes'],key=lambda s:s['start'])
        description=['# 一歌一景 · 制作任务包','',f'歌名：{project["song"]}',f'歌手 / 版本：{project["singer"] or "待确认"}',f'感觉：{project["feeling"] or "待沟通"}',f'歌曲片段：{project["clipStart"]}秒 — {project["clipEnd"]}秒','','画面时间从成片0秒起算；歌词时间由用户确认。','']
        with ZipFile(target,'w') as archive:
            for item_id in filter(None,refs):
                asset=self.media.get(item_id)
                if not asset: raise AppError('任务包中的素材已缺失，请重新选择')
                source=self.media.path(item_id)
                destination='media/'+item_id+source.suffix.lower()
                archive.write(source,destination,compress_type=ZIP_STORED if asset['kind']!='image' else ZIP_DEFLATED)
                assets.append({**self.media.public(asset),'packageFile':destination})
            for index,row in enumerate(rows):
                description += [f'## 画面 {index+1} · {row["start"]}—{row["end"]}秒',f'歌词：{row["lyric"] or "无"}',f'画面想法：{row["intent"] or "待补充"}',f'素材编号：{row["assetId"] or "未选择"}',f'素材起点：{row.get("offset",0)}秒','']
            spec={'format':'songscene-production-task','version':1,'exportedAt':now(),'project':project,'assets':assets,'timeUnit':'seconds','resolution':'9:16','instructions':'根据明确时间轴制作，人工确认歌词与画面对应关系。'}
            archive.writestr('制作说明.md','\n'.join(description),compress_type=ZIP_DEFLATED)
            archive.writestr('task.json',json.dumps(spec,ensure_ascii=False,indent=2),compress_type=ZIP_DEFLATED)
            archive.writestr('歌词时间轴.srt',srt(rows),compress_type=ZIP_DEFLATED)
        return target

    def close(self):
        self.renderer.close()


def make_server(workspace,port=8866):
    class Handler(BaseHTTPRequestHandler):
        server_version='SongScene/7'

        def check_origin(self,write=False):
            host=self.headers.get('Host','')
            allowed={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
            if host not in allowed:
                raise AppError('仅允许本机工作台地址访问',403)
            origin=self.headers.get('Origin')
            if origin and origin!='http://'+host:
                raise AppError('不允许其他网站访问本机工作目录',403)
            if write and not secrets.compare_digest(self.headers.get('X-Songscene-Token',''),workspace.token):
                raise AppError('工作台连接已更新，请刷新页面后重试',403)

        def send_headers(self,status,length,content_type,attachment=None):
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(length))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','same-origin')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'")
            if attachment:
                self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(attachment))

        def json(self,value,status=200):
            data=json.dumps(value,ensure_ascii=False).encode('utf-8')
            self.send_headers(status,len(data),'application/json; charset=utf-8'); self.end_headers()
            if self.command!='HEAD': self.wfile.write(data)

        def body(self,limit=8*1024*1024):
            if self.headers.get_content_type()!='application/json':
                raise AppError('请求需要JSON格式',415)
            length=self.length(limit)
            try:
                value=json.loads(self.rfile.read(length))
                if not isinstance(value,dict): raise ValueError()
                return value
            except (ValueError,UnicodeError):
                raise AppError('请求数据无法解析')

        def length(self,limit):
            try: size=int(self.headers.get('Content-Length','0'))
            except ValueError: raise AppError('文件大小不正确')
            if not 0<size<=limit: raise AppError('文件为空或超过大小限制',413)
            return size

        def upload(self,limit):
            remaining=self.length(limit)
            target=workspace.store.directory/'temp'/(ident('upload')+'.upload')
            try:
                with target.open('wb') as output:
                    while remaining:
                        chunk=self.rfile.read(min(remaining,1024*1024))
                        if not chunk: raise AppError('文件传输中断，请重试')
                        output.write(chunk); remaining-=len(chunk)
                return target
            except Exception:
                target.unlink(missing_ok=True); raise

        def file(self,path,content_type=None,attachment=None,remove=False):
            try:
                size=path.stat().st_size; start,end=0,size-1; status=200
                value=self.headers.get('Range','').strip()
                match=re.fullmatch(r'bytes=(\d*)-(\d*)',value)
                if match and any(match.groups()):
                    first,last=match.groups()
                    start=int(first) if first else max(0,size-int(last))
                    end=min(int(last),size-1) if first and last else size-1
                    if start> end or start>=size:
                        self.send_response(416); self.send_header('Content-Range',f'bytes */{size}'); self.send_header('Content-Length','0'); self.end_headers(); return
                    status=206
                content_type=content_type or mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
                if content_type.startswith('text/') or path.suffix in ['.js','.json']:
                    content_type+='; charset=utf-8'
                self.send_headers(status,max(0,end-start+1),content_type,attachment)
                self.send_header('Accept-Ranges','bytes')
                if status==206: self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
                self.end_headers()
                if self.command=='HEAD': return
                with path.open('rb') as source:
                    source.seek(start); remaining=end-start+1
                    while remaining:
                        chunk=source.read(min(remaining,256*1024))
                        if not chunk: break
                        self.wfile.write(chunk); remaining-=len(chunk)
            finally:
                if remove: path.unlink(missing_ok=True)

        def dispatch(self):
            self.check_origin(self.command in ['POST','PUT','DELETE'])
            url=urlsplit(self.path); path=unquote(url.path); query=parse_qs(url.query)
            parts=path.strip('/').split('/')
            if self.command in ['GET','HEAD']:
                if path=='/api/state': return self.json(workspace.state())
                if path=='/api/backup':
                    return self.file(workspace.backups.export(),'application/zip','一歌一景-完整备份.zip',True)
                if path=='/api/snapshots':
                    names=sorted((workspace.store.directory/'backups').glob('*.json'),reverse=True)
                    return self.json([{'name':p.name,'bytes':p.stat().st_size} for p in names])
                if len(parts)==4 and parts[:2]==['api','projects'] and parts[3]=='package':
                    return self.file(workspace.task_package(workspace.project(parts[2])),'application/zip','一歌一景-制作任务包.zip',True)
                if len(parts)==2 and parts[0]=='media':
                    asset=workspace.media.get(parts[1])
                    if not asset: raise AppError('找不到素材',404)
                    return self.file(workspace.media.path(parts[1]),asset.get('mime'),asset.get('name') if query.get('download') else None)
                if path.startswith('/api/'): raise AppError('接口不存在',404)
                relative=Path(path.lstrip('/') or 'index.html')
                allowed={'界面','封面','素材署名','视频','网页预览','分享'}
                if relative.as_posix()!='index.html' and (not relative.parts or relative.parts[0] not in allowed):
                    raise AppError('文件不可访问',404)
                target=(workspace.root/relative).resolve()
                if not target.is_relative_to(workspace.root) or not target.is_file(): raise AppError('文件不存在',404)
                return self.file(target)

            if self.command=='POST' and path=='/api/assets':
                upload=self.upload(1024**3)
                try:
                    value=workspace.media.add_file(upload,query.get('name',['素材'])[0])
                    return self.json(workspace.media.public(value),201)
                finally: upload.unlink(missing_ok=True)
            if self.command=='POST' and path=='/api/backup/inspect':
                upload=self.upload(2*1024**3)
                try: return self.json(workspace.backups.inspect(upload))
                except Exception:
                    upload.unlink(missing_ok=True); raise
            body=self.body()
            if self.command=='POST' and path=='/api/backup/restore':
                if any(j.get('status') in ['queued','running'] for j in workspace.store.list('job')):
                    raise AppError('请先完成或取消正在合成的任务，再恢复备份',409)
                return self.json(workspace.backups.restore(body.get('token',''),body.get('strategy','')))
            if self.command=='POST' and path=='/api/backup/snapshot':
                name=body.get('name','')
                if not re.fullmatch(r'\d{8}T\d{12}\.json',name): raise AppError('快照名称不正确')
                source=workspace.store.directory/'backups'/name
                if not source.is_file(): raise AppError('找不到快照',404)
                target=workspace.store.directory/'temp'/(ident('snapshot')+'.json')
                shutil.copy2(source,target)
                return self.json(workspace.backups.inspect(target))
            if self.command=='POST' and path=='/api/migrate-v6': return self.json(workspace.store.migrate_v6(body))
            if path in ['/api/draft','/api/preferences'] and self.command=='PUT':
                kind='draft' if path.endswith('draft') else 'preferences'
                return self.json(workspace.store.save(kind,'main',body,expected=body.get('revision'),snapshot=False))
            if path=='/api/projects' and self.command=='POST':
                return self.json(workspace.store.save('project',ident(),body),201)
            if len(parts)==3 and parts[:2]==['api','projects'] and self.command in ['PUT','DELETE']:
                with workspace.renderer.lock:
                    if workspace.renderer.active(parts[2]): raise AppError('本机正在使用这份方案合成，请等待完成或取消后再编辑',409)
                    previous=workspace.project(parts[2])
                    changes={'deleted':True} if self.command=='DELETE' else body
                    if body.get('outputWorkId'):
                        works=workspace.media.builtin_works()+workspace.store.list('work')
                        work=next((w for w in works if w['id']==body['outputWorkId']),None)
                        if not work or not workspace.media.get(work.get('videoId','')): raise AppError('请关联可播放的成片')
                    return self.json(workspace.store.save('project',previous['id'],changes,expected=body.get('revision')))
            if len(parts)==4 and parts[:2]==['api','projects'] and self.command=='POST':
                project=workspace.project(parts[2],parts[3]=='restore')
                if parts[3]=='restore': return self.json(workspace.store.save('project',project['id'],{'deleted':False},expected=body.get('revision')))
                if parts[3]=='render':
                    if body.get('revision')!=project['revision']: raise AppError('方案已更新，请先刷新再开始合成',409)
                    return self.json(workspace.renderer.start(project,body),202)
            if len(parts)==4 and parts[:2]==['api','jobs'] and parts[3]=='cancel' and self.command=='POST':
                workspace.renderer.cancel(parts[2]); return self.json({'cancelled':True})
            if path=='/api/works' and self.command=='POST':
                asset=workspace.media.get(body.get('videoId',''))
                if not asset or asset['kind']!='video': raise AppError('请选择有效的视频成片')
                poster=body.get('posterId') or asset.get('posterId','')
                if poster and (not workspace.media.get(poster) or workspace.media.get(poster)['kind']!='image'): raise AppError('请选择图片作为封面')
                value={**body,'duration':asset['duration'],'posterId':poster}
                work_id=ident('w')
                operations=[('work',work_id,value,None,False)]
                project_id=body.get('projectId')
                if project_id:
                    with workspace.renderer.lock:
                        if workspace.renderer.active(project_id): raise AppError('这份需求正在合成，请结束后再关联成片',409)
                        project=workspace.project(project_id)
                        operations.append(('project',project_id,{'status':'done','outputWorkId':work_id},body.get('projectRevision'),False))
                        return self.json(workspace.store.save_many(operations)[0],201)
                return self.json(workspace.store.save_many(operations)[0],201)
            raise AppError('接口不存在',404)

        def handle_request(self):
            try: self.dispatch()
            except AppError as error: self.json({'error':str(error)},error.status)
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError): pass
            except Exception:
                traceback.print_exc()
                try: self.json({'error':'操作未完成，请检查本机服务窗口；你的原始素材不会被覆盖。'},500)
                except (BrokenPipeError,ConnectionResetError): pass

        def do_GET(self): self.handle_request()
        def do_HEAD(self): self.handle_request()
        def do_POST(self): self.handle_request()
        def do_PUT(self): self.handle_request()
        def do_DELETE(self): self.handle_request()
        def do_OPTIONS(self): self.json({'error':'仅支持同源本机访问'},405)
        def log_message(self,fmt,*args):
            if len(args)>1 and str(args[1]) not in ['200','201','202','206','304']:
                super().log_message(fmt,*args)

    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.daemon_threads=True
    return server
