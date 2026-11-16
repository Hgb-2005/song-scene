import {$,toast} from './client.mjs';
import {captionSettings,clipDuration,sceneAt,visualTime} from './composition.mjs';

export function initPreview(app,getProject,onChange,pauseSource){
  const audio=$('compositionAudio'),video=$('compositionVideo'),image=$('compositionImage');
  let position=0,sourceId='',visualId='',frame=0,playing=false,selected=null,loading=false;
  const duration=()=>clipDuration(getProject());
  const stamp=t=>`${Math.floor(t/60).toString().padStart(2,'0')}:${(t%60).toFixed(1).padStart(4,'0')}`;
  function pause(){playing=false;audio.pause();video.pause();cancelAnimationFrame(frame);$('compositionPlay').textContent='播放预览';}
  function seek(value){
    position=Math.min(duration(),Math.max(0,Number(value)||0));
    if(audio.readyState){audio.currentTime=(getProject()?.clipStart||0)+position;}
    draw();
  }
  function draw(){
    const project=getProject();if(!project)return;
    const scene=sceneAt(project,position),asset=app.asset(scene?.assetId),caption=captionSettings(project);
    selected=scene;
    $('compositionPosition').textContent=`${stamp(position)} / ${stamp(duration())}`;
    $('compositionSeek').max=duration();$('compositionSeek').value=position;
    $('compositionScene').textContent=scene?`画面 ${project.scenes.indexOf(scene)+1} · ${asset?.name||'尚未选择素材'}`:'这段时间还没有画面';
    $('compositionCaption').textContent=scene?.lyric||'';
    $('compositionCaption').hidden=!caption.enabled||!scene?.lyric;
    $('compositionCaption').style.fontSize=`${caption.size}cqw`;
    $('compositionCaption').style.bottom=`${caption.bottom}%`;
    for(const el of [image,video])el.style.objectPosition=`${(scene?.cropX??.5)*100}% ${(scene?.cropY??.5)*100}%`;
    $('cropX').value=(scene?.cropX??.5)*100;$('cropY').value=(scene?.cropY??.5)*100;
    const locked=app.data.jobs.some(j=>j.projectId===project.id&&['queued','running'].includes(j.status));
    $('cropX').disabled=$('cropY').disabled=!scene||locked;
    $('previewCropLabel').textContent=scene?`调整画面 ${project.scenes.indexOf(scene)+1} 的取景`:'先为这一段选择画面';
    document.querySelectorAll('[data-preview-scene]').forEach(el=>el.classList.toggle('preview-active',el.dataset.previewScene===scene?.id));
    if(visualId!==(asset?.id||'')){
      visualId=asset?.id||'';video.pause();video.removeAttribute('src');video.load();
      image.hidden=true;video.hidden=true;$('compositionEmpty').hidden=false;
      $('compositionError').hidden=true;
      if(asset?.kind==='image'){image.src=asset.url;image.hidden=false;$('compositionEmpty').hidden=true;}
      if(asset?.kind==='video'){video.src=asset.url;video.hidden=false;video.load();$('compositionEmpty').hidden=true;}
    }
    if(asset?.kind==='video'&&video.readyState){
      const target=visualTime(scene,position,video.duration||asset.duration);
      if(!playing||Math.abs(video.currentTime-target)>.18){try{video.currentTime=target;}catch{}}
      if(playing&&video.paused)video.play().catch(()=>{$('compositionError').hidden=false;});
    }
  }
  function tick(){
    if(!playing)return;
    position=Math.max(0,audio.currentTime-(getProject()?.clipStart||0));
    if(position>=duration()){position=duration();pause();}
    draw();if(playing)frame=requestAnimationFrame(tick);
  }
  async function play(){
    if(playing){pause();return;}
    const project=getProject(),source=app.asset(project?.sourceId);
    if(!source?.hasAudio||!duration()||project.clipEnd>source.duration+.02){toast('请先选择有效的歌曲片段');return;}
    pauseSource();if(position>=duration()-.03)position=0;
    try{
      if(audio.readyState)audio.currentTime=project.clipStart+position;
      loading=true;await audio.play();loading=false;playing=true;$('compositionPlay').textContent='暂停预览';draw();tick();
    }catch{loading=false;pause();toast('浏览器无法播放这份声音素材，请换用 MP3、WAV 或 H.264/AAC MP4');}
  }
  function refresh(reset=false){
    const project=getProject();if(!project)return;
    const id=project.sourceId||'';
    if(reset||sourceId!==id){
      pause();position=0;sourceId=id;visualId='';
      audio.removeAttribute('src');const asset=app.asset(id);if(asset)audio.src=asset.url;audio.load();
    }
    if(position>duration())seek(duration());
    const c=captionSettings(project);$('captionEnabled').checked=c.enabled;$('captionSize').value=c.size;$('captionBottom').value=c.bottom;
    draw();
  }
  audio.addEventListener('loadedmetadata',()=>{audio.currentTime=(getProject()?.clipStart||0)+position;draw();});
  audio.addEventListener('ended',()=>{pause();position=Math.min(position,duration());draw();});
  audio.addEventListener('timeupdate',()=>{if(playing&&audio.currentTime>=(getProject()?.clipEnd||0)){position=duration();pause();audio.currentTime=getProject().clipEnd;draw();}});
  audio.addEventListener('waiting',()=>{video.pause();});
  audio.addEventListener('error',()=>{if(playing||loading){pause();toast('这份声音在浏览器中无法解码，可以更换素材后重试。');}});
  video.addEventListener('loadedmetadata',draw);
  video.addEventListener('error',()=>{$('compositionError').hidden=false;});
  image.addEventListener('error',()=>{$('compositionError').hidden=false;});
  $('compositionPlay').addEventListener('click',play);
  $('compositionSeek').addEventListener('input',event=>seek(event.target.value));
  $('compositionPrevious').addEventListener('click',()=>seek(position-.1));
  $('compositionNext').addEventListener('click',()=>seek(position+.1));
  for(const id of ['cropX','cropY'])$(id).addEventListener('input',()=>{if(selected){selected[id]=Number($(id).value)/100;onChange();draw();}});
  for(const id of ['captionEnabled','captionSize','captionBottom'])$(id).addEventListener('input',()=>{
    const p=getProject();if(!p)return;p.caption={enabled:$('captionEnabled').checked,size:Number($('captionSize').value),bottom:Number($('captionBottom').value)};onChange();draw();
  });
  $('resetCrop').addEventListener('click',()=>{if(selected){selected.cropX=selected.cropY=.5;onChange();draw();}});
  return {refresh,pause,seek,get position(){return position;},showScene(id){const s=getProject()?.scenes.find(s=>s.id===id);if(s){pause();seek(s.start);$('compositionPanel').scrollIntoView({behavior:'smooth',block:'start'});}}};
}
