import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {readFileSync} from 'node:fs';
const options={default_voice_id:1,default_language:'en',default_speed:1,languages:[{value:'en',label:'English'},{value:'zh',label:'Chinese'}],speeds:[{value:1,label:'1x'},{value:1.25,label:'1.25x'}],voice_catalog:[
  {id:1,name:'Kai',provider:'qwen',kind:'builtin',available:true,model:'instruct',languages:['en','zh'],supports_instructions:true},
  {id:2,name:'Kai Narrator',provider:'qwen',kind:'cloned',available:true,model:'clone',languages:['en'],supports_instructions:false},
]};
afterEach(()=>{vi.restoreAllMocks();vi.unstubAllGlobals();});
const change=(id,value)=>{const field=document.querySelector(id);field.value=value;field.dispatchEvent(new window.Event('change',{bubbles:true}));};
beforeEach(()=>{vi.resetModules();document.body.innerHTML=readFileSync('src/tts_app/static/index.html','utf8');vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>JSON.parse(JSON.stringify(options))})));vi.spyOn(window.HTMLMediaElement.prototype,'pause').mockImplementation(()=>{});});
it('filters one bilingual identity by language and displays the provider',async()=>{
  const module=await import('../../src/tts_app/static/instruction-voice-sample.js');await module.sampleReady;
  expect(document.querySelector('#instruction-model')).toBeNull();
  expect([...document.querySelector('#instruction-voice').options].filter(o=>o.value==='1')).toHaveLength(1);
  expect(document.querySelector('#instruction-voice').textContent).toContain('Kai · Qwen');
  change('#instruction-language','zh');
  expect(document.querySelector('#instruction-voice').value).toBe('1');
  expect([...document.querySelector('#instruction-voice').options].filter(o=>o.value==='1')).toHaveLength(1);
  expect(document.querySelector('#instruction-voice option[value="2"]')).toBeNull();
  expect(module.sampleValues()).not.toHaveProperty('model');
});
it('clears an incompatible clone selection and disables saving and preview until replaced',async()=>{
  const {createProfileEditor}=await import('../../src/tts_app/static/profile-editor.js');
  const editor=createProfileEditor({onUse:vi.fn(),onClose:vi.fn()});
  const profile={id:5,name:'Narrator',voice_id:2,language:'en',speed:1,instructions:'',preview_text:'Preview'};
  await editor.open(profile,[profile]);change('#instruction-language','zh');
  expect(document.querySelector('#instruction-voice').value).toBe('');
  expect(document.querySelector('#instruction-sample').disabled).toBe(true);
  expect(document.querySelector('#profile-save').disabled).toBe(true);
  expect(document.querySelector('#profile-save-as').disabled).toBe(true);
  change('#instruction-voice','1');
  expect(document.querySelector('#profile-save').disabled).toBe(false);
  expect(document.querySelector('#profile-save-as').disabled).toBe(false);
  expect(document.querySelector('#instruction-sample').disabled).toBe(false);
});
it('fetches fresh options on reopen after catalog sync and leaves the current draft untouched until close',async()=>{
  const {createProfileEditor}=await import('../../src/tts_app/static/profile-editor.js');
  const editor=createProfileEditor({onUse:vi.fn(),onClose:vi.fn()});
  const profile={id:5,name:'Narrator',voice_id:2,language:'en',speed:1,instructions:'',preview_text:'Preview'};
  await editor.open(profile,[profile]);
  document.querySelector('#instruction-text').value='Unsaved preview';
  const refreshed={...options,voice_catalog:options.voice_catalog.map(voice=>({...voice,available:voice.id!==2,name:voice.id===1?'Updated reader':voice.name}))};
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>refreshed})));
  vi.spyOn(window,'confirm').mockReturnValue(false);
  await editor.open(profile,[profile]);
  expect(document.querySelector('#instruction-text').value).toBe('Unsaved preview');
  expect(fetch).not.toHaveBeenCalled();
  editor.leave();await editor.open(profile,[profile]);
  expect(document.querySelector('#instruction-voice').textContent).toContain('Updated reader');
  expect(document.querySelector('#instruction-voice').value).toBe('2');
  expect(document.querySelector('#instruction-voice').textContent).toContain('unavailable');
  expect(document.querySelector('#profile-save').disabled).toBe(true);
});
