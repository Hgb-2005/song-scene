import {$,esc,icon,date,setToken,api,busy,toast,confirmAction,registerDialogs,downloadApi,inspectBackup} from './client.mjs';
import {statuses} from './core.mjs';
import {initLibrary} from './library.mjs';
import {initEditor} from './editor.mjs';

registerDialogs();
const app={data:{projects:[],works:[],stockWorks:[],assets:[],jobs:[],trash:[],capabilities:{}},page:'home',editor:null,library:null,
  asset(id){return this.data.assets.find(asset=>asset.id===id);},
  works(){const order=['49','28','17','7','15','3','5','6','19','37'];return [...this.data.works.slice().sort((a,b)=>b.updatedAt.localeCompare(a.updatedAt)),...this.data.stockWorks.slice().sort((a,b)=>order.indexOf(a.id)-order.indexOf(b.id))];},
  prefs(){return {favorites:[],recent:[],...this.data.preferences};}
};
let pollTimer,refreshing=false,preferenceQueue=Promise.resolve(),draftTimer,draftSaving=false,pendingDraft=null,homeReference='',showTrash=false,restorePreview=null;
app.savePrefs=changes=>{const operation=preferenceQueue.then(async()=>{const record=await api('PUT','/preferences',{...app.prefs(),...changes,revision:app.data.preferences?.revision||0});app.data.preferences=record;return record;});preferenceQueue=operation.catch(()=>{});return operation;};

function projectCard(project){const job=app.data.jobs.find(j=>j.projectId===project.id&&['queued','running'].includes(j.status));return `<article class="project-card"><span class="status-pill ${project.status}">${statuses[project.status]}</span><h3>${esc(project.song)}</h3><p class="singer">${esc(project.singer||'歌手 / 版本待确认')}</p><p class="feeling">${esc(project.feeling||'给这首歌，留一个想表达的感觉。')}</p><div class="card-bottom"><button class="text-button" data-edit="${esc(project.id)}">${project.status==='done'?'查看成片与方案':'继续制作'} ↗</button><span>${job?`${esc(job.stage)} · ${job.progress||0}%`:project.scenes.length?`${project.scenes.length}段画面`:'还未安排画面'}</span></div></article>`;}
function renderHome(){
  const projects=app.data.projects;
  $('homeStats').innerHTML=[['idea','待规划','先把想法留下'],['planning','安排画面','慢慢对齐歌词'],['making','制作中','再往前推一步'],['done','已完成','让作品留下来']].map(([status,title,note])=>`<button class="stat" data-board-status="${status}"><strong>${projects.filter(p=>p.status===status).length}</strong><span>${title}<small>${note}</small></span></button>`).join('');
  const recent=projects.slice().sort((a,b)=>b.updatedAt.localeCompare(a.updatedAt)).slice(0,3);
  $('recentProjects').innerHTML=recent.length?recent.map(projectCard).join(''):'<div class="empty-state"><h3>第一段风景，从一首歌开始。</h3><p>上面写下的想法，保存后就可以继续选片段、安排画面。</p></div>';
}
function renderBoard(){
  const query=$('projectSearch').value.trim().toLowerCase();
  const projects=app.data.projects.filter(p=>[p.song,p.singer,p.feeling].join(' ').toLowerCase().includes(query)).sort((a,b)=>b.updatedAt.localeCompare(a.updatedAt));
  $('kanban').hidden=showTrash;$('trashList').hidden=!showTrash;$('toggleTrash').textContent=showTrash?'返回制作看板':`查看已归档需求${app.data.trash.length?' · '+app.data.trash.length:''}`;
  $('kanban').innerHTML=Object.entries(statuses).map(([status,label])=>{const list=projects.filter(p=>p.status===status);return `<section class="kanban-column" aria-label="${label}"><div class="column-heading"><strong>${label}</strong><span>${list.length}</span></div>${list.length?list.map(projectCard).join(''):'<p class="kanban-empty">这里暂时没有需求</p>'}</section>`;}).join('');
  $('trashList').innerHTML=app.data.trash.length?app.data.trash.map(p=>`<article class="trash-row"><strong>${esc(p.song)}</strong><span>${date(p.updatedAt)} 归档 · 素材仍保留</span><button class="text-button" data-restore-project="${esc(p.id)}">恢复需求 ↗</button></article>`).join(''):'<div class="empty-state">还没有归档的需求。</div>';
}
function renderDoctor(){
  const rows=[['保存方式','本机磁盘数据库'],['需求 / 个人作品',`${app.data.projects.length} / ${app.data.works.length}`],['自动记录快照',`${app.data.snapshotCount||0} 份`],['FFmpeg 本机合成',app.data.capabilities.ffmpeg?'已就绪':'未找到'],['FFprobe 素材识别',app.data.capabilities.ffprobe?'已就绪':'未找到'],['歌词字幕',app.data.capabilities.subtitles?'可用':'当前版本未包含']];
  rows.push(['数据文件夹',app.data.dataDirectory||'程序目录的 data 文件夹']);
  $('doctor').innerHTML=rows.map(([name,value])=>`<div class="doctor-row"><span>${name}</span><span>${esc(value)}</span></div>`).join('')+(app.data.backupWarning?`<p class="small-note">${esc(app.data.backupWarning)}</p>`:'');
}
app.render=()=>{if(app.page==='home')renderHome();else if(app.page==='board')renderBoard();else if(app.page==='library')app.library.render();else if(app.page==='assets')app.library.renderAssets();else if(app.page==='editor')app.editor.sync();else if(app.page==='settings'){renderDoctor();loadSnapshots().catch(error=>toast(error.message));}$('navProjectCount').textContent=app.data.projects.length;};
app.refresh=async(render=true)=>{
  app.data=await api('GET','/state');setToken(app.data.token);$('connection').classList.remove('offline');$('connection').lastElementChild.textContent='工作目录已连接';$('errorBanner').hidden=true;
  if(render)app.render();
  clearTimeout(pollTimer);if(app.data.jobs.some(j=>['queued','running'].includes(j.status)))pollTimer=setTimeout(async()=>{if(refreshing)return;refreshing=true;try{await app.refresh();}catch(error){showConnectionError(error.message);}finally{refreshing=false;}},1500);
  return app.data;
};
app.navigate=async(page,skipGuard=false)=>{
  if(!['home','board','library','assets','settings','editor'].includes(page))page='home';
  if(!skipGuard&&app.page==='editor'&&page!=='editor'&&!(await app.editor.canLeave()))return false;
  if(app.page==='editor'&&page!=='editor')app.editor.pause();app.page=page;
  document.querySelectorAll('.page').forEach(section=>section.hidden=section.id!=='page-'+page);
  document.querySelectorAll('#mainNav [data-page]').forEach(button=>{const active=button.dataset.page===(page==='editor'?'board':page);button.classList.toggle('active',active);if(active)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');});
  const url=new URL(location.href);url.hash=page==='editor'&&app.editor.current?'project='+app.editor.current.id:page;history.replaceState(null,'',url);app.render();window.scrollTo({top:0,behavior:'instant'});return true;
};
function showConnectionError(message){$('connection').classList.add('offline');$('connection').lastElementChild.textContent='连接已断开';$('errorText').textContent=message;$('errorBanner').hidden=false;}
app.library=initLibrary(app);app.editor=initEditor(app);

function draftFields(){return {song:$('newSong').value,singer:$('newSinger').value,feeling:$('newFeeling').value,reference:homeReference};}
function paintHomeReference(){const work=app.works().find(w=>w.id===homeReference);$('newReference').hidden=!work;$('newReference').innerHTML=work?`<span>参考：《${esc(work.title)}》 · ${esc(work.artist)}</span><button id="clearHomeReference" aria-label="移除参考">×</button>`:'';}
function paintDraft(draft){$('newSong').value=draft?.song||'';$('newSinger').value=draft?.singer||'';$('newFeeling').value=draft?.feeling||'';homeReference=draft?.reference||'';paintHomeReference();}
function draftChanged(){
  pendingDraft=draftFields();$('newSong').setCustomValidity('');$('draftStatus').textContent='正在保存草稿……';
  try{localStorage.setItem('songscene.v7.homeDraft',JSON.stringify({workspaceId:app.data.workspaceId,baseRevision:app.data.draft?.revision||0,value:pendingDraft}));}catch{}
  clearTimeout(draftTimer);draftTimer=setTimeout(flushDraft,500);
}
async function flushDraft(){
  if(draftSaving)return;draftSaving=true;
  try{while(pendingDraft){const value=pendingDraft;pendingDraft=null;app.data.draft=await api('PUT','/draft',{...value,revision:app.data.draft?.revision||0});} $('draftStatus').textContent='草稿已保存在工作目录';try{localStorage.removeItem('songscene.v7.homeDraft');}catch{}}
  catch(error){$('draftStatus').textContent='草稿未存入磁盘，请保持页面并重新连接';toast(error.message);}
  finally{draftSaving=false;}
}
for(const id of ['newSong','newSinger','newFeeling'])$(id).addEventListener('input',draftChanged);
app.setReference=async work=>{if(!await app.navigate('home'))return;const empty=!$('newSong').value.trim();if(empty){$('newSong').value=work.title;$('newSinger').value=work.artist;}$('newFeeling').value=$('newFeeling').value||work.expression||'';homeReference=work.id;paintHomeReference();draftChanged();toast('参考作品已加入，歌名和心情可以继续修改');};
$('newReference').addEventListener('click',event=>{if(event.target.closest('#clearHomeReference')){homeReference='';paintHomeReference();draftChanged();}});
$('newProjectForm').addEventListener('submit',event=>{event.preventDefault();busy($('createProject'),async()=>{
  $('newSong').setCustomValidity($('newSong').value.trim()?'':'先写下想做的歌名');if(!$('newSong').reportValidity())return;
  const value=draftFields(),reference=app.works().find(w=>w.id===value.reference),asset=app.asset(reference?.videoId);
  const project=await api('POST','/projects',{...value,status:'idea',sourceId:asset?.id||'',clipStart:0,clipEnd:Math.min(30,asset?.duration||30)});
  clearTimeout(draftTimer);pendingDraft=null;paintDraft({});pendingDraft=draftFields();await flushDraft();await app.refresh(false);await app.editor.load(project.id);toast('需求已保存，可以继续选片段和安排画面');
});});

$('projectSearch').addEventListener('input',renderBoard);$('toggleTrash').addEventListener('click',()=>{showTrash=!showTrash;renderBoard();});
document.addEventListener('click',event=>{
  const brand=event.target.closest('.brand');if(brand){event.preventDefault();app.navigate('home');return;}
  const nav=event.target.closest('[data-page]');if(nav){app.navigate(nav.dataset.page);return;}
  const edit=event.target.closest('[data-edit]');if(edit){busy(edit,async()=>{await app.refresh(false);await app.editor.load(edit.dataset.edit);});return;}
  const feeling=event.target.closest('[data-feeling]');if(feeling){$('newFeeling').value=feeling.dataset.feeling;draftChanged();return;}
  const stat=event.target.closest('[data-board-status]');if(stat){app.navigate('board').then(()=>document.querySelector(`.kanban-column[aria-label="${statuses[stat.dataset.boardStatus]}"]`)?.scrollIntoView({block:'nearest',behavior:'smooth'}));return;}
  const restore=event.target.closest('[data-restore-project]');if(restore)busy(restore,async()=>{const value=app.data.trash.find(p=>p.id===restore.dataset.restoreProject);await api('POST','/projects/'+value.id+'/restore',{revision:value.revision});await app.refresh();toast('需求已恢复');});
});

async function loadSnapshots(){const snapshots=await api('GET','/snapshots'),selected=$('snapshotSelect').value;$('snapshotSelect').innerHTML=snapshots.length?snapshots.map(item=>{const name=item.name;const iso=`${name.slice(0,4)}-${name.slice(4,6)}-${name.slice(6,8)}T${name.slice(9,11)}:${name.slice(11,13)}:${name.slice(13,15)}.${name.slice(15,18)}Z`;return `<option value="${name}">${date(iso)}</option>`;}).join(''):'<option value="">还没有自动记录快照</option>';if(snapshots.some(s=>s.name===selected))$('snapshotSelect').value=selected;}
function openRestore(preview){restorePreview=preview;$('restoreSummary').innerHTML=`<div class="restore-counts">${preview.projects} 份需求 · ${preview.works} 条个人作品 · ${preview.assets} 份素材</div><p class="lead">${preview.conflictCount?`发现 ${preview.conflictCount} 条同编号需求或作品，请选择处理方式。`:'没有同编号需求或作品冲突。草稿和收藏也会按所选方式处理。'}</p>`;$('restoreConflicts').innerHTML=preview.conflicts.map(item=>`<div class="conflict-row">${item.kind==='project'?'需求':'作品'} · ${esc(item.title)}<small>本机：${date(item.localUpdated)} · 备份：${date(item.incomingUpdated)}</small></div>`).join('');$('restoreStrategy').value='newer';$('restoreDialog').showModal();}
$('exportBackup').addEventListener('click',()=>busy($('exportBackup'),async()=>{await downloadApi('/backup','一歌一景-完整备份-'+new Date().toLocaleDateString('sv-SE')+'.zip');toast('完整备份已导出，包含导入的素材文件');}));
$('importBackupButton').addEventListener('click',()=>$('backupFile').click());
$('backupFile').addEventListener('change',event=>{const file=event.target.files[0];if(!file)return;busy($('importBackupButton'),async()=>{toast('正在读取备份，暂不更改当前记录……');openRestore(await inspectBackup(file));}).finally(()=>event.target.value='');});
$('restoreSnapshot').addEventListener('click',()=>busy($('restoreSnapshot'),async()=>{if(!$('snapshotSelect').value)throw new Error('还没有可恢复的记录快照');openRestore(await api('POST','/backup/snapshot',{name:$('snapshotSelect').value}));}));
$('confirmRestore').addEventListener('click',()=>busy($('confirmRestore'),async()=>{if(!restorePreview)return;const result=await api('POST','/backup/restore',{token:restorePreview.token,strategy:$('restoreStrategy').value});$('restoreDialog').close();restorePreview=null;await app.refresh();paintDraft(app.data.draft);toast(`${result.message}，合并了${result.restored}条需求或作品`);}));

async function boot(){
  try{
    await app.refresh(false);
    let legacy=null;try{const notes=JSON.parse(localStorage.getItem('songscene.v6.notes')||'[]'),draft=JSON.parse(localStorage.getItem('songscene.v6.draft')||'null'),favorites=JSON.parse(localStorage.getItem('songscene.favorites')||'[]'),recent=JSON.parse(localStorage.getItem('songscene.recent')||'[]');if(notes.length||draft?.song||favorites.length)legacy={notes,draft,favorites,recent};}catch{}
    if(legacy){const result=await api('POST','/migrate-v6',legacy);if(result.migrated)toast(`已把V6的${result.migrated}份需求迁移到磁盘`);await app.refresh(false);}
    paintDraft(app.data.draft);$('draftStatus').textContent='草稿自动保存在工作目录';
    try{const cache=JSON.parse(localStorage.getItem('songscene.v7.homeDraft'));if(cache?.workspaceId===app.data.workspaceId&&cache.baseRevision===(app.data.draft?.revision||0)){paintDraft(cache.value);draftChanged();}}catch{}
    if($('offlineDialog').open)$('offlineDialog').close();
    const hash=decodeURIComponent(location.hash.slice(1));if(hash.startsWith('project='))await app.editor.load(hash.slice(8));else await app.navigate(['home','board','library','assets','settings'].includes(hash)?hash:'home',true);
    const workId=new URLSearchParams(location.search).get('work');if(workId)app.library.open(workId,false);
  }catch(error){showConnectionError(error.message);if(!$('offlineDialog').open)$('offlineDialog').showModal();}
}
$('retryConnect').addEventListener('click',()=>busy($('retryConnect'),boot));$('reloadState').addEventListener('click',()=>busy($('reloadState'),async()=>{await app.refresh();toast('已重新连接，磁盘内容已更新；未保存的编辑草稿仍保留。');}));
document.addEventListener('keydown',event=>{if(event.ctrlKey||event.metaKey||event.altKey||document.querySelector('dialog[open]')||event.target.closest('input,textarea,select,button,[contenteditable=true]'))return;if(event.key==='/'){event.preventDefault();app.navigate('library').then(()=>$('workSearch').focus());}});
boot();
