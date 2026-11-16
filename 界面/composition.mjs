// Keep crop and caption defaults in step with server/composition.py.
export const defaultCaption={enabled:true,size:4.7,bottom:10};
export const captionSettings=p=>({...defaultCaption,...p?.caption});
export const clipDuration=p=>Math.max(0,(p?.clipEnd||0)-(p?.clipStart||0));
export function sceneAt(project,time){
  const duration=clipDuration(project);
  if(time<0||time>duration||!duration)return null;
  const rows=[...(project?.scenes||[])].sort((a,b)=>a.start-b.start);
  return rows.find((s,i)=>time>=s.start&&(time<s.end||(time===duration&&i===rows.length-1&&time===s.end)))||null;
}
export function visualTime(scene,time,duration){
  if(!scene||!Number.isFinite(duration)||duration<=0)return 0;
  return (((scene.offset||0)+Math.max(0,time-scene.start))%duration+duration)%duration;
}
export function coverRect(iw,ih,ow,oh,x=.5,y=.5){
  const scale=Math.max(ow/iw,oh/ih),width=iw*scale,height=ih*scale;
  return {width,height,left:(ow-width)*x||0,top:(oh-height)*y||0};
}
