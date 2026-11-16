import {$,esc,icon,time,imageUrl,api,upload,busy,toast,confirmAction,downloadApi,downloadBlob} from './client.mjs';
import {statuses,splitScenes,planIssues,projectContent} from './core.mjs';
import {initPreview} from './preview.mjs';
import {captionSettings} from './composition.mjs';

export function initEditor(app){
  let working=null,baseline='',dirty=false,sourceElement=$('sourceVideo'),previewing=false,sceneUploadId='';
  const composition=initPreview(app,()=>working,changed,()=>{sourceElement.pause();previewing=false;});
  const clone=value=>JSON.parse(JSON.stringify(value));
  const activeJob=()=>working&&app.data.jobs.find(j=>j.projectId===working.id&&['queued','running'].includes(j.status));
  const key=id=>`songscene.v7.editor.${app.data.workspaceId}.${id}`;
  function changed(){
    if(!working)return;dirty=projectContent(working)!==baseline;$('editorSaveState').textContent=dirty?'有修改尚未保存':'方案已保存到工作目录';
    try{if(dirty)localStorage.setItem(key(working.id),JSON.stringify({baseRevision:working.revision,value:working}));}catch{$('editorSaveState').textContent='有修改尚未保存，请点击保存方案';}
    validation();composition.refresh();
  }
  function validation(){
    if(!working)return;const issues=planIssues(working,app.data.assets),duration=working.clipEnd-working.clipStart;
    $('clipDuration').textContent=Number.isFinite(duration)?`已选 ${duration.toFixed(2)} 秒`:'请填写有效时间';
    $('planValidation').classList.toggle('invalid',!!issues.length);
    $('planValidation').textContent=issues.length?issues.slice(0,3).join('；')+(issues.length>3?`，另有${issues.length-3}项待补充`:''):`已安排 ${working.scenes.length} 段画面，覆盖 ${duration.toFixed(2)} 秒，可以试听后合成。`;
  }
  function sourceOptions(){
    const sourceId=working.sourceId;
    const sources=app.data.assets.filter(a=>a.hasAudio&&!a.deleted).sort((a,b)=>Number(a.stock)-Number(b.stock));
    $('sourceSelect').innerHTML='<option value="">请选择歌曲或带声音的视频</option>'+sources.map(a=>`<option value="${esc(a.id)}">${esc(a.name)} · ${time(a.duration)}${a.stock?' · 内置参考':''}</option>`).join('');$('sourceSelect').value=sourceId;
  }
  function drawSource(){
    const asset=app.asset(working.sourceId);$('sourceEmpty').hidden=!!asset;$('sourcePlayer').hidden=!asset;
    for(const element of [$('sourceVideo'),$('sourceAudio')]){element.pause();element.removeAttribute('src');element.load();element.hidden=true;}
    previewing=false;
    if(asset){sourceElement=asset.kind==='audio'?$('sourceAudio'):$('sourceVideo');sourceElement.hidden=false;sourceElement.src=asset.url;if(asset.kind==='video')sourceElement.poster=imageUrl(app,asset.posterId);sourceElement.load();}
    $('clipStart').value=working.clipStart;$('clipEnd').value=working.clipEnd;
    for(const id of ['startRange','endRange'])$(id).max=asset?.duration||120;
    $('startRange').value=working.clipStart;$('endRange').value=working.clipEnd;validation();
  }
  function drawScenes(){
    const options=app.data.assets.filter(a=>['image','video'].includes(a.kind)).sort((a,b)=>Number(a.stock)-Number(b.stock)).map(a=>`<option value="${esc(a.id)}">${a.kind==='image'?'图片':'视频'} · ${esc(a.name)}${a.stock?' · 内置参考':''}</option>`).join('');
    $('sceneList').innerHTML=working.scenes.map((scene,index)=>{
      const asset=app.asset(scene.assetId),thumb=asset?(asset.kind==='image'?asset.url:imageUrl(app,asset.posterId)):'界面/mark.svg';
      return `<article class="scene-card" data-row="${esc(scene.id)}"><div class="scene-image"><img class="scene-thumb" src="${esc(thumb)}" alt="第${index+1}段参考画面"><span>${asset?asset.kind==='image'?'静态图片':'视频素材':'待选画面'}</span></div><div class="scene-body"><div class="scene-top"><strong>画面 ${String(index+1).padStart(2,'0')}</strong><button class="text-button" data-preview-scene="${esc(scene.id)}">预览此段</button><label>从<input data-key="start" aria-label="第${index+1}段开始时间" type="number" min="0" max="120" step="0.1" value="${scene.start}"></label><label>到<input data-key="end" aria-label="第${index+1}段结束时间" type="number" min="0.1" max="120" step="0.1" value="${scene.end}">秒</label><button class="icon-button" data-remove-scene="${esc(scene.id)}" aria-label="移除第${index+1}段画面">${icon('close')}</button></div><div class="scene-fields"><label>这一句歌词<input data-key="lyric" aria-label="第${index+1}段歌词" maxlength="120" value="${esc(scene.lyric)}" placeholder="也可以只写段落名称"></label><div class="scene-material"><label>搭配的画面<select data-key="assetId" aria-label="第${index+1}段画面素材"><option value="">请选择图片或视频</option>${options}</select></label><button class="text-button" data-upload-scene="${esc(scene.id)}">＋ 导入</button></div><label class="scene-description">为什么用这个画面<input data-key="intent" maxlength="500" aria-label="第${index+1}段画面想法" value="${esc(scene.intent)}" placeholder="例如：在这句唱到远方时，画面切到伸向山里的路"></label></div><label class="scene-offset">视频素材从第<input type="number" data-key="offset" aria-label="第${index+1}段素材起点" min="0" step="0.1" value="${scene.offset||0}">秒开始 <small>图片可忽略；短视频不足时会循环。</small></label></div></article>`;
    }).join('');
    for(const scene of working.scenes){const select=document.querySelector(`[data-row="${CSS.escape(scene.id)}"] [data-key="assetId"]`);if(select)select.value=scene.assetId;}
    validation();lockControls();
  }
  function drawOutput(){
    const work=app.works().find(w=>w.id===working.outputWorkId);
    $('projectOutput').innerHTML=work?`<div class="project-output"><img src="${esc(imageUrl(app,work.posterId))}" alt=""><div><strong>${esc(work.title)}</strong><small>成片已归档 · ${time(work.duration)}</small></div><button data-open="${esc(work.id)}" class="button secondary">观看成片 ↗</button></div>`:'<p class="small-note">还没有关联成片。做完后放回来，这份需求就完整了。</p>';
    $('outputSelect').innerHTML='<option value="">请选择已导入的个人作品</option>'+app.data.works.map(w=>`<option value="${esc(w.id)}">${esc(w.title)} · ${esc(w.artist)}</option>`).join('');$('outputSelect').value=working.outputWorkId||'';
  }
  function drawJob(){
    if(!working)return;
    const job=app.data.jobs.find(j=>j.projectId===working.id);$('editorJob').hidden=!job;if(!job)return;
    $('editorJob').innerHTML=`<div class="job-top"><strong>${esc(job.stage)}</strong><span>${job.status==='done'?'已完成':job.status==='failed'?'未完成':job.status==='cancelled'?'已取消':`${job.progress||0}%`}</span></div>${['queued','running'].includes(job.status)?`<progress max="100" value="${job.progress||0}" aria-label="本机合成进度"></progress>`:''}<div class="job-bottom"><span>${job.quality} × ${Number(job.quality)*16/9} · ${job.subtitles?'含歌词字幕':'不叠加歌词'}</span>${['queued','running'].includes(job.status)?`<button data-cancel-job="${esc(job.id)}" class="text-button">取消本次合成</button>`:job.workId?`<button data-open="${esc(job.workId)}" class="text-button">观看成片 ↗</button>`:''}</div>${job.error?`<details class="job-error"><summary>查看原因</summary><p>${esc(job.error)}</p></details>`:''}`;
    lockControls();
  }
  function lockControls(){
    const locked=!!activeJob();
    document.querySelectorAll('#page-editor input,#page-editor textarea,#page-editor select,#page-editor [data-remove-scene],#page-editor [data-upload-scene],#projectSteps button').forEach(el=>el.disabled=locked);
    for(const id of ['saveProject','uploadSourceButton','markStart','markEnd','generateScenes','useReferenceLyrics','addScene','openRender','importProjectOutput','linkOutput','archiveProject','resetCrop'])$(id).disabled=locked;
    $('openRender').disabled=locked||!app.data.capabilities.ffmpeg||!app.data.capabilities.ffprobe;
  }
  function draw(){
    $('editorTitle').textContent=working.song;$('editorSubtitle').textContent=[working.singer||'歌手 / 版本待确认',working.feeling].filter(Boolean).join(' · ');
    $('editSong').value=working.song;$('editSinger').value=working.singer;$('editFeeling').value=working.feeling;
    $('lyricInput').value=working.lyricDraft||working.scenes.map(s=>s.lyric).join('\n');
    $('projectSteps').innerHTML=Object.entries(statuses).map(([key,label],index)=>`<button data-status="${key}" class="${working.status===key?'active':''}" aria-pressed="${working.status===key}"><small>0${index+1}</small>${label}</button>`).join('');
    const ref=app.works().find(w=>w.id===working.reference);
    let reference=document.getElementById('editorReference');if(!reference){reference=document.createElement('p');reference.id='editorReference';reference.className='small-note';document.querySelector('.basic-details').append(reference);}
    reference.textContent=ref?`参考作品：《${ref.title}》 · ${ref.artist}`:'还没有选择参考作品，可以到灵感片库挑一条。';
    sourceOptions();drawSource();drawScenes();drawOutput();drawJob();composition.refresh();changed();
  }
  async function load(id){
    if(app.page==='editor'&&working?.id!==id&&!(await canLeave()))return false;
    const project=app.data.projects.find(p=>p.id===id);if(!project){toast('这份需求不存在或已归档');return false;}
    composition.pause();working=clone(project);baseline=projectContent(project);dirty=false;composition.refresh(true);
    try{const cache=JSON.parse(localStorage.getItem(key(id)));if(cache?.baseRevision===project.revision&&Array.isArray(cache.value?.scenes)){working=cache.value;dirty=projectContent(working)!==baseline;if(dirty)toast('已找回这份需求尚未保存的浏览器草稿');}else if(cache?.value&&cache.baseRevision!==project.revision){toast('磁盘内容已更新，旧浏览器草稿已保留，可导出查看',()=>downloadBlob(new Blob([JSON.stringify(cache.value,null,2)],{type:'application/json'}),'一歌一景-未保存草稿.json'),'导出旧草稿');}}catch{ /* Keep the disk version when local cache is malformed. */ }
    await app.navigate('editor',true);draw();return true;
  }
  async function save(){
    if(!working)return null;if(!$('editSong').reportValidity())return null;
    const saved=await api('PUT','/projects/'+working.id,{...working,revision:working.revision});
    working=clone(saved);baseline=projectContent(saved);dirty=false;try{localStorage.removeItem(key(working.id));}catch{}
    await app.refresh(false);draw();return saved;
  }
  async function ensureSaved(){try{return dirty?!!(await save()):!!working;}catch(error){toast(error.message);return false;}}
  async function canLeave(){return !dirty||await confirmAction('暂时离开这份方案？','修改还没有保存到工作目录，已尽量保留在当前浏览器草稿中。下次打开同一份需求可以继续。','保留草稿并离开');}
  function sync(){
    if(!working||app.page!=='editor')return;
    const latest=app.data.projects.find(p=>p.id===working.id);
    if(latest&&latest.revision!==working.revision&&!dirty){working=clone(latest);baseline=projectContent(latest);draw();}else drawJob();
  }
  function setReference(id){working.reference=id;const work=app.works().find(w=>w.id===id);changed();draw();toast(`已关联参考《${work?.title||''}》，可以带入它的歌词`);}
  $('saveProject').addEventListener('click',()=>busy($('saveProject'),async()=>{if(await save())toast('方案已保存到本机工作目录');}));
  $('backToBoard').addEventListener('click',()=>app.navigate('board'));
  $('page-editor').addEventListener('input',event=>{
    if(!working||activeJob())return;const element=event.target;
    if(element.id==='editSong')working.song=element.value;
    else if(element.id==='editSinger')working.singer=element.value;
    else if(element.id==='editFeeling')working.feeling=element.value;
    else if(element.id==='lyricInput')working.lyricDraft=element.value;
    else if(['clipStart','clipEnd','startRange','endRange'].includes(element.id)){
      const start=['clipStart','startRange'].includes(element.id);working[start?'clipStart':'clipEnd']=Number(element.value);$(start?'clipStart':'clipEnd').value=element.value;$(start?'startRange':'endRange').value=element.value;
    }else if(element.dataset.key){const scene=working.scenes.find(s=>s.id===element.closest('[data-row]')?.dataset.row);if(scene)scene[element.dataset.key]=['start','end','offset'].includes(element.dataset.key)?Number(element.value):element.value;}
    else return;changed();
  });
  $('sceneList').addEventListener('change',event=>{if(event.target.dataset.key==='assetId'&&!activeJob()){const row=working.scenes.find(s=>s.id===event.target.closest('[data-row]').dataset.row);row.assetId=event.target.value;changed();drawScenes();}});
  $('sourceSelect').addEventListener('change',()=>{working.sourceId=$('sourceSelect').value;const source=app.asset(working.sourceId);working.clipStart=0;working.clipEnd=Math.min(30,source?.duration||30);drawSource();changed();});
  for(const [id,field] of [['markStart','clipStart'],['markEnd','clipEnd']])$(id).addEventListener('click',()=>{working[field]=Math.round(sourceElement.currentTime*10)/10;if(working.clipEnd<=working.clipStart)working.clipEnd=Math.min(app.asset(working.sourceId)?.duration||120,working.clipStart+5);drawSourceValues();changed();});
  function drawSourceValues(){$('clipStart').value=working.clipStart;$('clipEnd').value=working.clipEnd;$('startRange').value=working.clipStart;$('endRange').value=working.clipEnd;}
  $('previewClip').addEventListener('click',()=>{const source=app.asset(working.sourceId),duration=working.clipEnd-working.clipStart;if(!source||duration<=0||working.clipEnd>source.duration){toast('请先选择有效的歌曲片段');return;}composition.pause();sourceElement.currentTime=working.clipStart;previewing=true;sourceElement.play().catch(()=>toast('当前文件不能试听，请换一个素材'));});
  for(const element of [$('sourceVideo'),$('sourceAudio')])element.addEventListener('timeupdate',()=>{if(previewing&&working&&element.currentTime>=working.clipEnd){element.pause();previewing=false;}});
  for(const element of [$('sourceVideo'),$('sourceAudio')])element.addEventListener('play',()=>composition.pause());
  $('uploadSourceButton').addEventListener('click',()=>$('sourceFile').click());
  $('sourceFile').addEventListener('change',event=>{const file=event.target.files[0];if(!file)return;busy($('uploadSourceButton'),async()=>{toast('正在复制并读取歌曲素材……');const asset=await upload(file);if(!asset.hasAudio)throw new Error('这份素材没有声音，请选择歌曲或带声音的视频');await app.refresh(false);working.sourceId=asset.id;working.clipStart=0;working.clipEnd=Math.min(30,asset.duration);sourceOptions();drawSource();changed();toast('歌曲已导入，可以试听选段');}).finally(()=>event.target.value='');});
  $('generateScenes').addEventListener('click',()=>busy($('generateScenes'),async()=>{
    const rows=splitScenes($('lyricInput').value,working.clipEnd-working.clipStart,app.works().find(w=>w.id===working.reference)?.posterId||'');
    if(working.scenes.length&&!(await confirmAction('重新拆分画面？','这会替换当前画面方案。已保存的旧方案仍可通过自动快照恢复。','替换当前方案')))return;
    working.scenes=rows;working.lyricDraft=$('lyricInput').value;changed();drawScenes();toast('已先平均分配时长，请试听调整切点并选择画面');
  }));
  $('useReferenceLyrics').addEventListener('click',()=>busy($('useReferenceLyrics'),async()=>{
    const reference=app.works().find(w=>w.id===working.reference);if(!reference?.lyrics?.length)throw new Error('请先选择带歌词时间轴的参考作品，也可以直接逐行填写歌词');
    if(working.scenes.length&&!(await confirmAction('带入参考歌词？','当前画面方案会被替换，请先确认已保存需要保留的内容。','带入并替换')))return;
    working.lyricDraft=reference.lyrics.map(line=>line.text).join('\n');$('lyricInput').value=working.lyricDraft;
    if(working.sourceId===reference.videoId){working.scenes=reference.lyrics.filter(line=>line.t1>working.clipStart&&line.t0<working.clipEnd).map((line,index)=>({id:`s-${Date.now()}-${index}`,start:Math.max(0,line.t0-working.clipStart),end:Math.min(working.clipEnd-working.clipStart,line.t1-working.clipStart),lyric:line.text,intent:'',assetId:reference.posterId,offset:0}));toast('已带入原样片的歌词切点，请安排对应画面');}
    else{working.scenes=splitScenes(working.lyricDraft,working.clipEnd-working.clipStart,reference.posterId);toast('已带入歌词并平均分配时长，需要重新试听调整');}
    changed();drawScenes();
  }));
  $('addScene').addEventListener('click',()=>{
    const duration=working.clipEnd-working.clipStart,last=working.scenes.at(-1);let start=0,end=duration;
    if(last){if(last.end<duration-.2){start=last.end;end=duration;}else if(last.end-last.start>=.4){end=last.end;start=Math.round((last.start+last.end)/2*1000)/1000;last.end=start;}else{toast('最后一段太短，请先调整时长');return;}}
    working.scenes.push({id:'s-'+crypto.randomUUID(),start,end,lyric:'',intent:'',assetId:'',offset:0});changed();drawScenes();
  });
  $('sceneList').addEventListener('click',event=>{
    const preview=event.target.closest('[data-preview-scene]');if(preview){composition.showScene(preview.dataset.previewScene);return;}
    const remove=event.target.closest('[data-remove-scene]');if(remove){const previous=clone(working.scenes);working.scenes=working.scenes.filter(s=>s.id!==remove.dataset.removeScene);changed();drawScenes();toast('已移除这段画面',()=>{working.scenes=previous;changed();drawScenes();});}
    const importer=event.target.closest('[data-upload-scene]');if(importer){sceneUploadId=importer.dataset.uploadScene;$('sceneFile').click();}
  });
  $('sceneFile').addEventListener('change',async event=>{const file=event.target.files[0];if(!file)return;try{toast('正在导入画面素材……');const asset=await upload(file);if(!['image','video'].includes(asset.kind))throw new Error('请选择图片或视频作为画面');await app.refresh(false);const scene=working.scenes.find(s=>s.id===sceneUploadId);if(scene){scene.assetId=asset.id;changed();drawScenes();toast('素材已放入这段画面');}}catch(error){toast(error.message);}finally{event.target.value='';}});
  $('exportTask').addEventListener('click',()=>busy($('exportTask'),async()=>{if(await ensureSaved()){await downloadApi('/projects/'+working.id+'/package',working.song+'-制作任务包.zip');toast('制作任务包已导出，包含方案、歌词时间轴和用到的素材');}}));
  $('importProjectOutput').addEventListener('click',()=>app.library.openImport(working.id));
  $('linkOutput').addEventListener('click',()=>busy($('linkOutput'),async()=>{if(!$('outputSelect').value)throw new Error('请先选择一条个人作品');const id=$('outputSelect').value;if(!(await ensureSaved()))return;working.outputWorkId=id;working.status='done';changed();await save();toast('成片已关联，这份需求已完成');}));
  $('projectSteps').addEventListener('click',event=>{const button=event.target.closest('[data-status]');if(!button||activeJob())return;if(button.dataset.status==='done'&&!working.outputWorkId){toast('请先导入或关联成片，再标记完成');return;}working.status=button.dataset.status;changed();draw();});
  $('openRender').addEventListener('click',()=>busy($('openRender'),async()=>{if(!(await ensureSaved()))return;const issues=planIssues(working,app.data.assets);if(issues.length)throw new Error(issues.slice(0,3).join('；'));$('renderSummary').textContent=`《${working.song}》 · ${(working.clipEnd-working.clipStart).toFixed(2)}秒 · ${working.scenes.length}段画面`;$('renderSubtitles').disabled=!app.data.capabilities.subtitles;$('renderSubtitles').checked=app.data.capabilities.subtitles&&captionSettings(working).enabled;$('renderDialog').showModal();}));
  $('startRender').addEventListener('click',()=>busy($('startRender'),async()=>{await api('POST','/projects/'+working.id+'/render',{revision:working.revision,quality:$('renderQuality').value,subtitles:$('renderSubtitles').checked});$('renderDialog').close();await app.refresh();toast('已开始本机合成，进度会显示在这份需求里');}));
  $('editorJob').addEventListener('click',event=>{const button=event.target.closest('[data-cancel-job]');if(button)busy(button,async()=>{await api('POST','/jobs/'+button.dataset.cancelJob+'/cancel',{});await app.refresh();toast('合成已取消，方案和原素材仍保留');});});
  $('archiveProject').addEventListener('click',()=>busy($('archiveProject'),async()=>{if(!(await confirmAction('归档这份需求？','它会移到已归档列表，素材和成片都会保留，之后可以恢复。','归档需求')))return;const archived=await api('DELETE','/projects/'+working.id,{revision:working.revision});dirty=false;try{localStorage.removeItem(key(working.id));}catch{}await app.refresh(false);await app.navigate('board',true);toast('需求已归档',async()=>{await api('POST','/projects/'+archived.id+'/restore',{revision:archived.revision});await app.refresh();});}));
  window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
  return {load,sync,save,ensureSaved,canLeave,setReference,drawJob,get current(){return working;},get dirty(){return dirty;},pause(){sourceElement.pause();composition.pause();previewing=false;}};
}
