import test from 'node:test';
import assert from 'node:assert/strict';
import {splitScenes,planIssues,projectContent} from '../界面/core.mjs';

test('a lyric plan covers the selected duration without rounding gaps',()=>{
  const scenes=splitScenes('第一句\n\n 第二句\n第三句',7.01,'picture');
  assert.equal(scenes.length,3);assert.equal(scenes[0].start,0);assert.equal(scenes.at(-1).end,7.01);
  for(let i=1;i<scenes.length;i++)assert.equal(scenes[i].start,scenes[i-1].end);
});
test('incomplete, overlapping and out-of-bounds plans cannot appear ready',()=>{
  const assets=[{id:'song',kind:'audio',duration:10,hasAudio:true},{id:'picture',kind:'image'}];
  const valid={sourceId:'song',clipStart:2,clipEnd:9,scenes:splitScenes('一\n二',7,'picture')};
  assert.deepEqual(planIssues(valid,assets),[]);
  assert.ok(planIssues({...valid,clipEnd:11},assets).some(s=>s.includes('超出')));
  assert.ok(planIssues({...valid,scenes:[{start:1,end:7,assetId:'missing'}]},assets).length>=2);
  assert.throws(()=>splitScenes('',30));assert.throws(()=>splitScenes('歌词',121));
});
test('render-affecting edits are dirty; server revision alone is not',()=>{
  const p={song:'歌名',scenes:[],clipStart:0,clipEnd:30,lyricDraft:'第一句'};
  assert.equal(projectContent(p),projectContent({...p,revision:3,updatedAt:'today'}));
  assert.notEqual(projectContent(p),projectContent({...p,lyricDraft:'第二句'}));
});
