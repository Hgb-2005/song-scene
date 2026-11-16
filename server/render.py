"""Real, cancellable local FFmpeg jobs built from an explicit scene timeline."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import re
import shutil
import subprocess
import threading

from .media import HIDDEN, PROTOCOLS, FORMATS
from .store import AppError, ident, now


class Cancelled(Exception):
    pass


def ass_time(seconds):
    centiseconds=round(seconds*100)
    return f'{centiseconds//360000}:{centiseconds//6000%60:02}:{centiseconds//100%60:02}.{centiseconds%100:02}'


class Renderer:
    def __init__(self, store, media):
        self.store=store
        self.media=media
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='songscene-render')
        self.events={}
        self.processes={}
        self.lock=threading.RLock()
        for job in store.list('job'):
            if job.get('status') in ['queued','running']:
                self.update(job['id'],status='failed',stage='上次服务已停止',error='上次合成被中断，素材和方案已保留，可以重新开始。')

    def active(self, project_id):
        return next((j for j in self.store.list('job') if j.get('projectId')==project_id and j.get('status') in ['queued','running']),None)

    def update(self, job_id, **changes):
        return self.store.save('job',job_id,changes,force=True,snapshot=False)

    def start(self, project, options):
        with self.lock:
            if not self.media.ffmpeg or not self.media.ffprobe:
                raise AppError('本机合成需要FFmpeg和FFprobe，请先安装后重新启动工作台')
            if self.active(project['id']):
                raise AppError('这份需求已有合成任务，请等待完成或先取消',409)
            quality=options.get('quality','540')
            if quality not in ['540','1080']:
                raise AppError('请选择540或1080画质')
            subtitles=bool(options.get('subtitles',True))
            if subtitles and not self.media.has_subtitles:
                raise AppError('当前FFmpeg未包含字幕功能，请关闭字幕或安装带libass的版本')
            self.media.check_project(project,True)
            project=self.store.save('project',project['id'],{'status':'making'},expected=project['revision'])
            job_id=ident('j')
            job=self.store.save('job',job_id,{'projectId':project['id'],'status':'queued','progress':0,'stage':'等待本机合成','error':'','quality':quality,'subtitles':subtitles,'spec':project},snapshot=False)
            self.events[job_id]=threading.Event()
            self.executor.submit(self._render,job_id)
            return job

    def cancel(self, job_id):
        with self.lock:
            job=self.store.get('job',job_id)
            if not job or job.get('status') not in ['queued','running']:
                raise AppError('任务已结束，无需取消')
            self.events.setdefault(job_id,threading.Event()).set()
            process=self.processes.get(job_id)
            if process and process.poll() is None:
                process.terminate()
            self.update(job_id,status='cancelled',stage='已取消，方案和素材仍保留')

    def _run(self, job_id, command, folder, duration, base, span, stage):
        event=self.events[job_id]
        if event.is_set(): raise Cancelled()
        self.update(job_id,status='running',progress=round(base),stage=stage)
        log=(folder/'ffmpeg.log').open('wb')
        try:
            process=subprocess.Popen([self.media.ffmpeg,'-hide_banner','-loglevel','error','-nostdin','-progress','pipe:1','-nostats',*command],cwd=folder,stdout=subprocess.PIPE,stderr=log,**HIDDEN)
        except Exception:
            log.close(); raise
        with self.lock: self.processes[job_id]=process
        progress=-1
        try:
            for raw in iter(process.stdout.readline,b''):
                if event.is_set():
                    process.terminate(); break
                line=raw.decode('utf-8','replace').strip()
                if line.startswith('out_time_us='):
                    try:
                        current=min(1,float(line.split('=',1)[1])/1_000_000/max(duration,.001))
                        value=round(base+span*current)
                        if value!=progress:
                            self.update(job_id,progress=value); progress=value
                    except ValueError:
                        pass
            code=process.wait()
            log.flush()
            with (folder/'ffmpeg.log').open('rb') as errors:
                errors.seek(max(0,errors.seek(0,2)-2500))
                error=errors.read().decode('utf-8','replace')
            if event.is_set(): raise Cancelled()
            if code:
                raise AppError('FFmpeg合成失败：'+(error.strip() or '请检查素材文件'))
        finally:
            process.stdout.close(); log.close()
            with self.lock: self.processes.pop(job_id,None)

    def _render(self, job_id):
        folder=self.store.directory/'renders'/job_id
        folder.mkdir(parents=True,exist_ok=True)
        successful=False
        try:
            job=self.store.get('job',job_id)
            project=job['spec']
            duration=project['clipEnd']-project['clipStart']
            width=int(job['quality']); height=width*16//9
            scenes=sorted(project['scenes'],key=lambda row:row['start'])
            (folder/'project.json').write_text(json.dumps(project,ensure_ascii=False,indent=2),encoding='utf-8')
            for index,scene in enumerate(scenes):
                asset=self.media.get(scene['assetId']); path=self.media.path(asset['id'])
                length=scene['end']-scene['start']
                inputs=['-loop','1','-framerate','30',*PROTOCOLS,*FORMATS,'-i',str(path)] if asset['kind']=='image' else ['-stream_loop','-1','-ss',str(scene.get('offset',0)),*PROTOCOLS,*FORMATS,'-i',str(path)]
                filters=f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps=30,format=yuv420p'
                command=[*inputs,'-t',str(length),'-an','-vf',filters,'-c:v','libx264','-preset','veryfast','-crf','20','-threads','2','-y',f'{index:03}.mp4']
                self._run(job_id,command,folder,length,5+65*scene['start']/duration,65*length/duration,f'正在配画面 {index+1}/{len(scenes)}')
            (folder/'concat.txt').write_text('\n'.join(f"file '{index:03}.mp4'" for index in range(len(scenes))),encoding='ascii')
            self._run(job_id,['-f','concat','-safe','1','-i','concat.txt','-c','copy','-y','joined.mp4'],folder,duration,70,2,'正在连接画面')
            source=self.media.path(project['sourceId'])
            command=['-i','joined.mp4','-ss',str(project['clipStart']),*PROTOCOLS,*FORMATS,'-i',str(source),'-map','0:v:0','-map','1:a:0','-t',str(duration)]
            if job['subtitles']:
                self._subtitles(folder/'captions.ass',scenes,width,height)
                command+=['-vf','subtitles=captions.ass','-c:v','libx264','-preset','veryfast','-crf','20','-threads','2']
            else:
                command+=['-c:v','copy']
            command+=['-af',f'afade=t=in:st=0:d=0.04,afade=t=out:st={max(0,duration-.12):.3f}:d=0.12','-c:a','aac','-b:a','192k','-movflags','+faststart','-y','result.mp4']
            self._run(job_id,command,folder,duration,72,25,'正在合入音乐和歌词')
            if self.events[job_id].is_set(): raise Cancelled()
            self.update(job_id,progress=98,stage='正在保存成片')
            asset=self.media.add_file(folder/'result.mp4',project['song']+'-成片.mp4',True)
            poster=self.media.make_poster(asset['id'])
            if self.events[job_id].is_set(): raise Cancelled()
            work_id=ident('w')
            reference=next((t for t in self.media.builtin_works()+self.store.list('work') if str(t['id'])==project.get('reference')),None)
            work={'title':project['song'],'artist':project['singer'],'expression':project['feeling'],'story':f'根据已保存的{len(scenes)}段画面方案在本机合成。','videoId':asset['id'],'posterId':poster['id'] if poster else '','duration':asset['duration'],'projectId':project['id'],'group':reference.get('group','warm') if reference else 'warm','mood':reference.get('mood','我的创作') if reference else '我的创作','lyrics':[{'text':row['lyric'],'t0':row['start'],'t1':row['end']} for row in scenes if row['lyric']]}
            with self.lock:
                if self.events[job_id].is_set(): raise Cancelled()
                self.store.save_many([('work',work_id,work,None,False),('project',project['id'],{'status':'done','outputWorkId':work_id},None,True),('job',job_id,{'status':'done','progress':100,'stage':'成片已归档到片库','workId':work_id},None,True)])
            successful=True
        except Cancelled:
            self.update(job_id,status='cancelled',stage='已取消，方案和素材仍保留')
            successful=True
        except Exception as error:
            message=str(error)[:2500] or type(error).__name__
            self.update(job_id,status='failed',stage='合成未完成，可检查后重试',error=message)
            (folder/'error.txt').write_text(message,encoding='utf-8')
        finally:
            with self.lock: self.events.pop(job_id,None)
            if successful:
                resolved=folder.resolve(); owned=(self.store.directory/'renders').resolve()
                if resolved.parent==owned and resolved.is_relative_to(owned):
                    shutil.rmtree(resolved)

    @staticmethod
    def _subtitles(path,scenes,width,height):
        font_size=round(width*.047)
        header=f'''[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,{font_size},&H00FFFFFF,&H000000FF,&H90000000,&H90000000,0,0,0,0,100,100,0,0,1,1.3,0,2,{round(width*.06)},{round(width*.06)},{round(height*.1)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
        lines=[]
        for scene in scenes:
            lyric=re.sub(r'[{}]','',scene['lyric']).replace('\\','／').replace('\r',' ').replace('\n',' ')
            if lyric:
                lines.append(f'Dialogue: 0,{ass_time(scene["start"])},{ass_time(scene["end"])},Default,,0,0,0,,{lyric}')
        path.write_text(header+'\n'.join(lines),encoding='utf-8-sig')

    def close(self):
        for job in self.store.list('job'):
            if job.get('status') in ['queued','running']:
                try: self.cancel(job['id'])
                except AppError: pass
        self.executor.shutdown(wait=True,cancel_futures=True)
