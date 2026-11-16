export const $=id=>document.getElementById(id);
export const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
export const icon=name=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${window.SONGSCENE_ICONS?.[name]||''}</svg>`;
export const time=n=>`${String(Math.floor(Math.max(0,n||0)/60)).padStart(2,'0')}:${String(Math.floor(Math.max(0,n||0)%60)).padStart(2,'0')}`;
export const size=n=>n>=1024**3?`${(n/1024**3).toFixed(1)} GB`:`${(n/1024**2).toFixed(1)} MB`;
export const date=value=>value?new Date(value).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}):'未记录';
export const imageUrl=(app,id)=>app.asset(id)?.url||'界面/mark.svg';
let token='',timer,toastAction;
export function setToken(value){token=value;}
export async function api(method,path,body){
  let response;
  try{response=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json',...(method!=='GET'?{'X-Songscene-Token':token}:{})},...(body!==undefined?{body:JSON.stringify(body)}:{})});}catch{throw new Error('连接不到本机工作台，请确认启动窗口仍然开着');}
  let result;
  try{result=await response.json();}catch{throw new Error('工作台响应不正确，请重新启动并刷新页面');}
  if(!response.ok){const error=new Error(result.error||'操作未完成');error.status=response.status;throw error;}
  return result;
}
export async function upload(file){
  if(!file) throw new Error('请先选择文件');
  if(file.size>1024**3) throw new Error('单个素材不能超过1GB');
  const response=await fetch('/api/assets?name='+encodeURIComponent(file.name),{method:'POST',headers:{'X-Songscene-Token':token,'Content-Type':'application/octet-stream'},body:file});
  const value=await response.json(); if(!response.ok) throw new Error(value.error||'素材导入失败'); return value;
}
export async function inspectBackup(file){
  if(file.size>2*1024**3)throw new Error('备份不能超过2GB');
  const response=await fetch('/api/backup/inspect',{method:'POST',headers:{'X-Songscene-Token':token,'Content-Type':'application/octet-stream'},body:file});
  const value=await response.json();if(!response.ok)throw new Error(value.error||'备份无法读取');return value;
}
export async function downloadApi(path,name){
  const response=await fetch('/api'+path);
  if(!response.ok){const error=await response.json();throw new Error(error.error||'导出未完成');}
  downloadBlob(await response.blob(),name);
}
export function downloadBlob(blob,name){const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),15000);}
export async function copyText(value){try{await navigator.clipboard.writeText(value);toast('已复制');}catch{downloadBlob(new Blob([value],{type:'text/plain;charset=utf-8'}),'一歌一景-文案.txt');toast('复制未获允许，已导出文本文件');}}
export function toast(message,action=null,label='撤销'){
  clearTimeout(timer);$('toastText').textContent=message;$('toastAction').hidden=!action;$('toastAction').textContent=label;toastAction=action;
  const dialogs=[...document.querySelectorAll('dialog[open]')];(dialogs.at(-1)||document.body).append($('toast'));$('toast').hidden=false;
  timer=setTimeout(()=>{$('toast').hidden=true;toastAction=null;document.body.append($('toast'));},action?12000:5500);
}
$('toastAction').addEventListener('click',async()=>{const action=toastAction;toastAction=null;$('toast').hidden=true;if(action)try{await action();}catch(error){toast(error.message);}});
let resolveConfirmation;
export function confirmAction(title,message,label='确定'){
  $('confirmTitle').textContent=title;$('confirmText').textContent=message;$('confirmYes').textContent=label;
  $('confirmDialog').showModal();return new Promise(resolve=>{resolveConfirmation=resolve;});
}
$('confirmYes').addEventListener('click',()=>{const resolve=resolveConfirmation;resolveConfirmation=null;$('confirmDialog').close();resolve?.(true);});
$('confirmNo').addEventListener('click',()=>$('confirmDialog').close());
$('confirmDialog').addEventListener('close',()=>{resolveConfirmation?.(false);resolveConfirmation=null;});
export async function busy(button,action){
  if(button.disabled)return;button.disabled=true;
  try{return await action();}catch(error){toast(error.message);return null;}finally{button.disabled=false;}
}
export function registerDialogs(){
  document.querySelectorAll('[data-icon]').forEach(el=>el.innerHTML=icon(el.dataset.icon));
  document.addEventListener('click',event=>{const close=event.target.closest('[data-close]');if(close)$(close.dataset.close).close();});
  document.querySelectorAll('dialog').forEach(dialog=>dialog.addEventListener('close',()=>{if(dialog.contains($('toast'))){$('toast').hidden=true;document.body.append($('toast'));}}));
}
