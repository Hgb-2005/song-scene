export const statuses={idea:'待规划',planning:'安排画面',making:'制作中',done:'已完成'};
export const groups={warm:'温暖日常',travel:'远行自由',memory:'回忆告别',quiet:'寻光独处'};
export function splitScenes(value,duration,assetId='') {
  const lines=String(value).split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
  if(!lines.length) throw new Error('请先按行写下歌词或段落名称');
  if(lines.length>60||lines.some(s=>s.length>120)) throw new Error('最多60段，每段歌词不超过120字');
  if(!Number.isFinite(duration)||duration<.2||duration>120) throw new Error('请先选择0.2至120秒的歌曲片段');
  if(duration/lines.length<.2) throw new Error('段落太密，请减少歌词行数或延长片段');
  return lines.map((lyric,index)=>({id:`s-${Date.now()}-${index}`,start:Math.round(index*duration/lines.length*1000)/1000,end:index===lines.length-1?duration:Math.round((index+1)*duration/lines.length*1000)/1000,lyric,intent:'',assetId,offset:0}));
}
export function planIssues(project,assets) {
  const issues=[],duration=project.clipEnd-project.clipStart;
  const byId=new Map(assets.map(a=>[a.id,a])),source=byId.get(project.sourceId);
  if(!source?.hasAudio) issues.push('还没有选择带声音的歌曲素材');
  if(!Number.isFinite(duration)||duration<.2||duration>120) issues.push('片段时长需要在0.2至120秒之间');
  if(project.clipStart<0||source&&project.clipEnd>source.duration+.02) issues.push('所选片段超出了歌曲范围');
  const rows=[...project.scenes].sort((a,b)=>a.start-b.start);
  if(!rows.length) issues.push('还没有安排画面');
  let end=0;
  rows.forEach((row,index)=>{
    if(!Number.isFinite(row.start)||!Number.isFinite(row.end)||row.end<=row.start) issues.push(`第${index+1}段时间不正确`);
    if(Math.abs(row.start-end)>.04) issues.push(`第${index+1}段与上一段之间有空隙或重叠`);
    const asset=byId.get(row.assetId);
    if(!asset||!['image','video'].includes(asset.kind)) issues.push(`第${index+1}段还没有选择画面素材`);
    if(asset?.kind==='video'&&row.offset>=asset.duration) issues.push(`第${index+1}段素材起点超过了视频时长`);
    end=row.end;
  });
  if(rows.length&&Math.abs(end-duration)>.04) issues.push(`画面结束于${end.toFixed(2)}秒，需要对齐${duration.toFixed(2)}秒`);
  return issues;
}
export function projectContent(p) {
  const {song,singer,feeling,reference,status,sourceId,clipStart,clipEnd,scenes,outputWorkId,lyricDraft}=p;
  return JSON.stringify({song,singer,feeling,reference,status,sourceId,clipStart,clipEnd,scenes,outputWorkId,lyricDraft});
}
