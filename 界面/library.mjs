import {$,esc,icon,time,size,imageUrl,api,upload,busy,toast,copyText} from './client.mjs';
import {groups} from './core.mjs';

export function initLibrary(app){
  const filters={view:'all',mood:'all',query:'',kind:'all'},video=$('workVideo');let currentId='',serial=0;
  const visible=()=>app.works().filter(work=>(filters.view!=='mine'||!work.stock)&&(filters.view!=='favorites'||app.prefs().favorites.includes(work.id))&&(filters.view!=='recent'||app.prefs().recent.includes(work.id))&&(filters.mood==='all'||work.group===filters.mood)&&(!filters.query||[work.title,work.artist,work.requestedArtist,work.mood,work.expression].join(' ').toLowerCase().includes(filters.query))).sort((a,b)=>filters.view==='recent'?app.prefs().recent.indexOf(a.id)-app.prefs().recent.indexOf(b.id):0);
  function render(){
    const works=visible();$('workCount').textContent=`${works.length} 条作品`;
    document.querySelectorAll('[data-view]').forEach(button=>{const on=button.dataset.view===filters.view;button.classList.toggle('active',on);button.setAttribute('aria-pressed',on);});
    document.querySelectorAll('[data-mood]').forEach(button=>{const on=button.dataset.mood===filters.mood;button.classList.toggle('active',on);button.setAttribute('aria-pressed',on);});
    $('worksGrid').innerHTML=works.map(work=>`<article class="work-card"><button class="work-open" data-open="${esc(work.id)}" aria-label="观看《${esc(work.title)}》，${esc(work.artist)}${work.isCover?'，翻唱版本':''}"><span class="work-art"><img src="${esc(imageUrl(app,work.posterId))}" alt="${esc(work.title)}作品封面" width="240" height="300" loading="lazy">${!work.stock?'<span class="own-tag">我的作品</span>':''}<small>${esc(work.mood||groups[work.group])}</small><time>${time(work.duration)}</time><span class="mini-play">${icon('play')}</span></span><strong>${esc(work.title)}</strong><span class="work-artist">${esc(work.artist||'个人作品')}${work.isCover?'<b class="cover-tag">翻唱</b>':''}</span></button><button class="card-like" data-like="${esc(work.id)}" aria-label="${app.prefs().favorites.includes(work.id)?'取消收藏':'收藏'}${esc(work.title)}" aria-pressed="${app.prefs().favorites.includes(work.id)}">${icon('heart')}</button></article>`).join('');
    $('workEmpty').hidden=!!works.length;
    $('workEmpty').innerHTML=`<h3>${filters.view==='mine'?'这里在等你的下一条作品':filters.query?'暂时没有找到这首歌':'这个范围里还没有作品'}</h3><p>${filters.view==='mine'?'导入一个本地视频，或者从制作需求中合成一条。':'已有样片只是参考，也可以从任何歌名开始新的创作。'}</p><button class="text-button" data-page="home">去记下一个想法 ↗</button>`;
  }
  function renderAssets(){
    const assets=app.data.assets.filter(a=>($('showStock').checked||!a.stock)&&(filters.kind==='all'||filters.kind===a.kind));
    document.querySelectorAll('[data-kind]').forEach(b=>{const active=b.dataset.kind===filters.kind;b.classList.toggle('active',active);b.setAttribute('aria-pressed',active);});
    $('assetsGrid').innerHTML=assets.length?assets.slice().reverse().map(asset=>`<article class="asset-card"><div class="asset-thumb">${asset.kind==='image'||asset.posterId?`<img src="${esc(asset.kind==='image'?asset.url:imageUrl(app,asset.posterId))}" alt="" loading="lazy">`:icon(asset.kind==='audio'?'headphones':'play')}</div><div class="asset-info"><strong title="${esc(asset.name)}">${esc(asset.name)}</strong><small>${{image:'图片',video:'视频',audio:'音乐'}[asset.kind]} · ${asset.kind==='image'?`${asset.width} × ${asset.height}`:time(asset.duration)} · ${size(asset.bytes)}${asset.stock?' · 内置参考':''}</small>${asset.kind==='audio'?`<audio src="${esc(asset.url)}" controls preload="none"></audio>`:''}<a class="text-button" href="${esc(asset.url)}?download=1" download>保存文件 ↓</a></div></article>`).join(''):'<div class="empty-state"><h3>从一些喜欢的声音和画面开始。</h3><p>导入图片、视频或音乐，就能在制作方案里选用。</p></div>';
  }
  function updateFavorite(){const work=app.works().find(w=>w.id===currentId);if(!work)return;const liked=app.prefs().favorites.includes(work.id);$('workFavorite').setAttribute('aria-pressed',liked);$('workFavorite').innerHTML=icon('heart')+(liked?'已收藏':'收藏作品');}
  async function like(id){
    const favorites=app.prefs().favorites.slice(),index=favorites.indexOf(id);if(index>=0)favorites.splice(index,1);else favorites.push(id);
    await app.savePrefs({favorites});render();updateFavorite();
  }
  function open(id,autoplay=true){
    const work=app.works().find(w=>w.id===String(id));if(!work)return;
    serial++;const request=serial;video.pause();currentId=work.id;
    const asset=app.asset(work.videoId);video.poster=imageUrl(app,work.posterId);video.removeAttribute('src');video.controls=!!asset;
    if(asset)video.src=asset.url;video.load();$('workUnavailable').hidden=!!asset;
    $('workTitle').textContent=work.title;$('workArtist').textContent=work.artist||'个人作品';$('workMood').textContent=`${work.mood||groups[work.group]} / ${time(work.duration)}`;
    $('workVersion').textContent=work.isCover?`翻唱版本 · 实际演唱：${work.artist} · 原点单歌手：${work.requestedArtist||'未填写'}`:work.stock?'指定歌手版本':'个人创作 / 已归档';
    $('workExpression').textContent=work.expression||'留住一段属于自己的片刻。';$('workStory').textContent=work.story||'这是一条由你导入的个人作品。';
    $('downloadWork').hidden=!asset;if(asset){$('downloadWork').href=asset.url+'?download=1';$('downloadWork').download=asset.name;}
    $('workCredits').hidden=!work.credits;if(work.credits)$('workCredits').href='/'+work.credits.split('/').map(encodeURIComponent).join('/');
    $('workLyrics').innerHTML=(work.lyrics||[]).map(line=>`<button class="lyric-line" data-at="${line.t0}" data-end="${line.t1}" ${!asset?'disabled':''}>${esc(line.text)}</button>`).join('')||'<p class="small-note">这条作品还没有单独的歌词时间轴。</p>';
    const list=visible(),index=list.findIndex(w=>w.id===work.id);$('workPosition').textContent=`${index>=0?String(index+1).padStart(2,'0'):'—'} / ${String(list.length).padStart(2,'0')}`;
    $('previousWork').disabled=list.length<2;$('nextWork').disabled=list.length<2;updateFavorite();
    if(!$('workDialog').open)$('workDialog').showModal();
    const url=new URL(location.href);url.searchParams.set('work',work.id);history.replaceState(null,'',url);
    if(asset&&autoplay)video.play().catch(error=>{if(request===serial&&error.name!=='AbortError'&&error.name!=='NotAllowedError')toast('视频无法播放，请确认文件完整或保存后用本地播放器观看');});
  }
  $('workDialog').addEventListener('close',()=>{serial++;video.pause();video.removeAttribute('src');video.load();const url=new URL(location.href);url.searchParams.delete('work');history.replaceState(null,'',url);});
  video.addEventListener('playing',()=>{if(currentId)app.savePrefs({recent:[currentId,...app.prefs().recent.filter(id=>id!==currentId)].slice(0,100)}).catch(error=>toast(error.message));});
  video.addEventListener('error',()=>{if(video.getAttribute('src')){$('workUnavailable').textContent='视频文件无法读取，请确认素材存在，或从完整备份恢复。';$('workUnavailable').hidden=false;}});
  video.addEventListener('timeupdate',()=>{document.querySelectorAll('#workLyrics .lyric-line').forEach(button=>{const active=video.currentTime>=Number(button.dataset.at)&&video.currentTime<Number(button.dataset.end);button.classList.toggle('active',active);if(active)button.setAttribute('aria-current','true');else button.removeAttribute('aria-current');});});
  $('workLyrics').addEventListener('click',event=>{const button=event.target.closest('[data-at]');if(button&&!button.disabled){video.currentTime=Number(button.dataset.at);video.play().catch(()=>toast('请点击视频的播放键重试'));}});
  for(const [id,direction] of [['previousWork',-1],['nextWork',1]])$(id).addEventListener('click',()=>{const list=visible();let index=list.findIndex(w=>w.id===currentId);if(index<0)index=0;if(list.length)open(list[(index+direction+list.length)%list.length].id);});
  $('workFavorite').addEventListener('click',()=>busy($('workFavorite'),()=>like(currentId)));
  $('workReference').addEventListener('click',()=>{const id=currentId;$('workDialog').close();reference(id);});
  $('copyWorkLink').addEventListener('click',()=>copyText(new URL('/index.html?work='+encodeURIComponent(currentId),location.origin).href).then(()=>toast('已复制本机定位链接，仅在这台电脑的工作台中使用')));
  function reference(id){const work=app.works().find(w=>w.id===String(id));if(!work)return;if(app.page==='editor')app.editor.setReference(work.id);else app.setReference(work);}
  async function openImport(projectId=''){
    if(projectId&&!(await app.editor.ensureSaved()))return;
    $('importWorkForm').reset();$('importWorkStatus').textContent='';$('requestedArtistLabel').hidden=true;
    $('importWorkProject').innerHTML='<option value="">独立作品，暂不关联</option>'+app.data.projects.map(p=>`<option value="${esc(p.id)}">${esc(p.song)}</option>`).join('');
    const project=app.data.projects.find(p=>p.id===projectId);if(project){$('importWorkTitle').value=project.song;$('importWorkArtist').value=project.singer;$('importWorkFeeling').value=project.feeling;$('importWorkProject').value=project.id;}
    $('importWorkDialog').showModal();
  }
  $('importIsCover').addEventListener('change',()=>$('requestedArtistLabel').hidden=!$('importIsCover').checked);
  $('importWorkForm').addEventListener('submit',event=>{event.preventDefault();busy($('submitWork'),async()=>{
    const file=$('importWorkVideo').files[0];if(!file)throw new Error('请先选择视频');
    $('importWorkStatus').textContent='正在复制视频并读取信息……';const videoAsset=await upload(file);
    let posterId=videoAsset.posterId||'';if($('importWorkPoster').files[0]){$('importWorkStatus').textContent='正在保存封面……';posterId=(await upload($('importWorkPoster').files[0])).id;}
    const projectId=$('importWorkProject').value;await app.refresh(false);const project=app.data.projects.find(p=>p.id===projectId);
    $('importWorkStatus').textContent='正在关联需求并归档作品……';
    await api('POST','/works',{title:$('importWorkTitle').value.trim(),artist:$('importWorkArtist').value.trim(),expression:$('importWorkFeeling').value.trim(),group:$('importWorkGroup').value,mood:groups[$('importWorkGroup').value],isCover:$('importIsCover').checked,requestedArtist:$('importRequestedArtist').value.trim(),videoId:videoAsset.id,posterId,projectId,projectRevision:project?.revision});
    $('importWorkDialog').close();await app.refresh();if(!projectId)await app.navigate('library');toast('新作品已归档'+(projectId?'，关联需求已完成':''));
  }).finally(()=>{$('importWorkStatus').textContent='';});});
  $('openImportWork').addEventListener('click',()=>openImport());
  $('openAssetUpload').addEventListener('click',()=>$('assetFiles').click());
  $('assetFiles').addEventListener('change',async event=>{
    const files=[...event.target.files];if(!files.length)return;if(files.length>10){toast('每次最多导入10个文件');event.target.value='';return;}
    await busy($('openAssetUpload'),async()=>{for(let index=0;index<files.length;index++){$('uploadStatus').textContent=`正在导入 ${index+1}/${files.length}：${files[index].name}`;await upload(files[index]);}await app.refresh();toast(`已导入 ${files.length} 份素材`);});
    $('uploadStatus').textContent='';event.target.value='';
  });
  $('showStock').addEventListener('change',renderAssets);
  $('workSearch').addEventListener('input',event=>{filters.query=event.target.value.trim().toLowerCase();render();});
  document.addEventListener('click',event=>{
    const openButton=event.target.closest('[data-open]');if(openButton){open(openButton.dataset.open);return;}
    const likeButton=event.target.closest('[data-like]');if(likeButton){busy(likeButton,()=>like(likeButton.dataset.like));return;}
    const ref=event.target.closest('[data-reference]');if(ref){reference(ref.dataset.reference);return;}
    const view=event.target.closest('[data-view]');if(view){filters.view=view.dataset.view;render();return;}
    const mood=event.target.closest('[data-mood]');if(mood){filters.mood=mood.dataset.mood;render();return;}
    const kind=event.target.closest('[data-kind]');if(kind){filters.kind=kind.dataset.kind;renderAssets();}
  });
  document.addEventListener('visibilitychange',()=>{if(document.hidden)video.pause();});
  return {render,renderAssets,open,openImport,visible};
}
