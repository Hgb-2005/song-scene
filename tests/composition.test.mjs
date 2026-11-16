import test from 'node:test';
import assert from 'node:assert/strict';
import {sceneAt,visualTime,coverRect,captionSettings} from '../界面/composition.mjs';
import {projectContent} from '../界面/core.mjs';

test('preview uses half-open scene intervals and includes the final paused frame',()=>{
  const p={clipStart:10,clipEnd:14,scenes:[{id:'b',start:2,end:4},{id:'a',start:0,end:2}]};
  assert.equal(sceneAt(p,0).id,'a');assert.equal(sceneAt(p,1.999).id,'a');assert.equal(sceneAt(p,2).id,'b');
  assert.equal(sceneAt(p,4).id,'b');assert.equal(sceneAt(p,4.1),null);
  assert.equal(sceneAt({...p,scenes:[p.scenes[0]]},1),null);
});
test('video visual time includes its offset and loops independently from the song',()=>{
  const s={start:2,end:12,offset:1.5};
  assert.equal(visualTime(s,2,3),1.5);assert.equal(visualTime(s,4,3),.5);assert.equal(visualTime(s,10,3),.5);
  assert.equal(visualTime(s,2,0),0);
});
test('cover positioning keeps chosen left/right and top/bottom regions visible',()=>{
  assert.deepEqual(coverRect(1000,500,540,960,0,.5),{width:1920,height:960,left:0,top:0});
  assert.equal(coverRect(1000,500,540,960,1,.5).left,-1380);
  assert.equal(coverRect(300,1000,540,960,.5,1).top,-840);
});
test('V7 defaults stay compatible and visual settings participate in unsaved changes',()=>{
  const p={song:'歌名',scenes:[{start:0,end:2,cropX:.5,cropY:.5}],clipStart:0,clipEnd:2};
  assert.deepEqual(captionSettings(p),{enabled:true,size:4.7,bottom:10});
  assert.notEqual(projectContent(p),projectContent({...p,caption:{enabled:false,size:6,bottom:20}}));
  assert.notEqual(projectContent(p),projectContent({...p,scenes:[{...p.scenes[0],cropX:0}]}));
});
