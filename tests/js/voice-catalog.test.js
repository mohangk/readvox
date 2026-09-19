import { afterEach, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';

const cloned = {id:10,name:'Kai Narrator',voice_id:20,voice_name:'Kai clone',voice:'cloud-kai-id',language:'en',speed:1.1,instructions:'',preview_text:'Preview text'};
const personal = {id:1,name:'Personal',voice_id:11,voice:'Kai',language:'en',speed:1,instructions:'Calm',preview_text:'Preview'};
const options = {languages:[{value:'en',label:'English'},{value:'zh',label:'Chinese'}],
  voice_catalog:[
    {id:11,name:'Kai',provider:'qwen',available:true,kind:'builtin',model:'instruct',languages:['en','zh'],supports_instructions:true},
    {id:20,name:'Kai clone',provider:'qwen',available:true,kind:'cloned',model:'clone',languages:['en'],supports_instructions:false},
  ], speeds:[{value:1,label:'1x'},{value:1.1,label:'1.1x'},{value:1.25,label:'1.25x'}],default_voice_id:11};
afterEach(()=>{vi.resetModules();vi.restoreAllMocks();vi.unstubAllGlobals();document.body.innerHTML='';window.localStorage.clear();});
async function mount(handler) {
  document.body.innerHTML=readFileSync('src/tts_app/static/index.html','utf8');
  vi.spyOn(window.HTMLMediaElement.prototype,'pause').mockImplementation(()=>{});
  vi.spyOn(window.HTMLMediaElement.prototype,'play').mockResolvedValue();
  URL.createObjectURL=vi.fn(()=> 'blob:test');URL.revokeObjectURL=vi.fn();
  const requests=[];
  vi.stubGlobal('fetch',vi.fn(async(url,init)=>{
    if(url.endsWith('/options')) return {ok:true,json:async()=>options};
    if(url==='/api/voice-profiles' && !init) return {ok:true,json:async()=>[personal,cloned]};
    requests.push([url,init]);
    return handler ? handler(url,init) : {ok:true,blob:async()=>new Blob(['audio']),json:async()=>({...JSON.parse(init.body),id:init.method==='PUT'?10:99})};
  }));
  const {createProfileEditor}=await import('../../src/tts_app/static/profile-editor.js');
  const onUse=vi.fn(),onClose=vi.fn();const editor=createProfileEditor({onUse,onClose});
  await editor.open(cloned,[personal,cloned]);
  return {editor,onUse,onClose,requests};
}
const change = (id,value) => {const field=document.querySelector(id);field.value=value;field.dispatchEvent(new window.Event('change',{bubbles:true}));};
it('previews and saves clone profile edits using catalog identity',async()=>{
  const {requests,onUse}=await mount();
  expect(document.querySelector('#profile-save').disabled).toBe(false);
  expect(document.querySelector('#profile-delete').disabled).toBe(false);
  expect(document.querySelector('#profile-save-note')?.textContent).toContain('Save As');
  expect(document.querySelector('#instruction-prompt').disabled).toBe(true);
  expect(document.querySelector('#instruction-voice').textContent).toContain('Kai clone');
  expect(document.querySelector('#instruction-model')).toBeNull();
  change('#instruction-speed','1.25');
  document.querySelector('#instruction-sample-form').dispatchEvent(new window.Event('submit',{cancelable:true}));
  await vi.waitFor(()=>expect(requests).toHaveLength(1));
  expect(JSON.parse(requests[0][1].body)).toMatchObject({voice_id:20,speed:1.25,instructions:''});
  document.querySelector('#profile-save').click();
  await vi.waitFor(()=>expect(onUse).toHaveBeenCalled());
  expect(requests[1][0]).toBe('/api/voice-profiles/10');
  expect(JSON.parse(requests[1][1].body)).toMatchObject({name:'Kai Narrator',voice_id:20,speed:1.25});
  expect(JSON.parse(requests[1][1].body)).not.toHaveProperty('voice');
});
it('Save As retains the clone identity and restores editable controls after failure',async()=>{
  const {requests}=await mount(async()=>({ok:false,json:async()=>({detail:'Name conflict'})}));
  vi.spyOn(window,'prompt').mockReturnValue('Duplicate');
  change('#instruction-speed','1.25');document.querySelector('#profile-save-as').click();
  await vi.waitFor(()=>expect(document.querySelector('#instruction-status').textContent).toBe('Name conflict'));
  expect(requests[0][0]).toBe('/api/voice-profiles');
  expect(JSON.parse(requests[0][1].body)).toMatchObject({voice_id:20,speed:1.25});
  expect(document.querySelector('#profile-save').disabled).toBe(false);
  expect(document.querySelector('#profile-delete').disabled).toBe(false);
  expect(document.querySelector('#instruction-prompt').disabled).toBe(true);
});
it('deletes a clone profile through the ordinary profile endpoint',async()=>{
  const {requests,onClose}=await mount(async()=>({ok:true}));
  vi.spyOn(window,'confirm').mockReturnValue(true);document.querySelector('#profile-delete').click();
  await vi.waitFor(()=>expect(onClose).toHaveBeenCalled());
  expect(requests).toHaveLength(1);expect(requests[0][0]).toBe('/api/voice-profiles/10');expect(requests[0][1].method).toBe('DELETE');
});
it('voice capabilities disable instructions while retaining the current form draft',async()=>{
  const {editor,requests}=await mount();await editor.open(personal,[personal,cloned]);
  const prompt=document.querySelector('#instruction-prompt');prompt.value='Unsaved narration';
  change('#instruction-voice','20');expect(prompt.disabled).toBe(true);
  document.querySelector('#instruction-sample-form').dispatchEvent(new window.Event('submit',{cancelable:true}));
  await vi.waitFor(()=>expect(requests).toHaveLength(1));
  expect(JSON.parse(requests[0][1].body).instructions).toBe('');
  change('#instruction-voice','11');expect(prompt.value).toBe('Unsaved narration');
  vi.spyOn(window,'confirm').mockReturnValue(true);
  await editor.open({...personal,instructions:'Another profile'},[personal,cloned]);
  expect(prompt.value).toBe('Another profile');
});
it('clears an incompatible voice and explains how to restore preview',async()=>{
  await mount();change('#instruction-language','zh');
  expect(document.querySelector('#instruction-language').value).toBe('zh');
  expect(document.querySelector('#instruction-voice').value).toBe('');
  expect(document.querySelector('#instruction-sample').disabled).toBe(true);
  expect(document.querySelector('#instruction-capability-note').textContent).toContain('language');
  change('#instruction-voice','11');expect(document.querySelector('#instruction-sample').disabled).toBe(false);
});
it('keeps an unavailable saved voice visible without replacing its settings',async()=>{
  const {editor,requests}=await mount(async()=>({ok:false,json:async()=>({detail:'Voice is unavailable'})}));
  await editor.open({...personal,voice_id:77,voice_name:'Retired reader',instructions:'Keep these'},[personal]);
  expect(document.querySelector('#instruction-voice').value).toBe('77');
  expect(document.querySelector('#instruction-voice').textContent).toContain('Retired reader');
  expect(document.querySelector('#instruction-prompt').value).toBe('Keep these');
  expect(document.querySelector('#instruction-sample').disabled).toBe(true);
  expect(document.querySelector('#instruction-capability-note').textContent).toContain('unavailable');
  document.querySelector('#profile-save').click();
  expect(requests).toHaveLength(0);
  expect(document.querySelector('#profile-save').disabled).toBe(true);
});
it('uses the remembered profile or the first matching language profile without ownership labels',async()=>{
  await mount();const module=await import('../../src/tts_app/static/profile-selection.js');
  window.localStorage.setItem('readvox.profileSelection.v1',JSON.stringify({en:10,language:'en'}));
  await module.loadProfiles();expect(module.selectedProfile().id).toBe(10);
  window.localStorage.setItem('readvox.profileSelection.v1',JSON.stringify({en:999,language:'en'}));
  await module.loadProfiles();expect(module.selectedProfile().id).toBe(1);
  expect(document.querySelector('#profile-select').textContent).not.toContain('System');
});
it('escapes profile and catalog names and displays API errors as text',async()=>{
  const {editor}=await mount(async()=>({ok:false,json:async()=>({detail:'<img src=x onerror=alert(1)>'})}));
  const profile={...personal,name:'Reader <img src=x>',voice_id:77,voice_name:'Voice <img src=x>'};
  await editor.open(profile,[profile]);
  expect(document.querySelector('#editor-profiles').textContent).toBe(profile.name);
  expect(document.querySelector('#instruction-voice').textContent).toContain(profile.voice_name);
  expect(document.querySelector('#profile-editor img')).toBeNull();
  change('#instruction-voice','11');
  document.querySelector('#profile-save').click();
  await vi.waitFor(()=>expect(document.querySelector('#instruction-status').textContent).toBe('<img src=x onerror=alert(1)>'));
  expect(document.querySelector('#profile-editor img')).toBeNull();
});
