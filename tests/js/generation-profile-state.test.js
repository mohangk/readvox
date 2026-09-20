import {afterEach, expect, it, vi} from 'vitest';
import {readFileSync} from 'node:fs';
const profile={id:1,name:'Reader',voice_id:11,language:'en',speed:1,instructions:'',preview_text:'Preview',voice_available:1};
const options={default_voice_id:11,languages:[{value:'en',label:'English'},{value:'zh',label:'Chinese'}],speeds:[{value:1,label:'1x'}],voice_catalog:[{id:11,name:'Reader',available:true,languages:['en','zh'],supports_instructions:true}]};
afterEach(()=>{vi.resetModules();vi.restoreAllMocks();vi.unstubAllGlobals();document.body.innerHTML='';window.localStorage.clear();});
async function mount(initialProfiles=[],generationHandler) {
  document.body.innerHTML=readFileSync('src/tts_app/static/index.html','utf8');
  vi.spyOn(window.HTMLMediaElement.prototype,'pause').mockImplementation(()=>{});
  vi.spyOn(window.HTMLMediaElement.prototype,'load').mockImplementation(()=>{});
  let profiles=initialProfiles;
  vi.stubGlobal('fetch',vi.fn(async(url,init)=>{
    if(url==='/api/voice-profiles') return {ok:true,json:async()=>profiles};
    if(url.endsWith('/options')) return {ok:true,json:async()=>options};
    if(url==='/api/generations') return {ok:true,json:async()=>[]};
    if(init?.method==='POST') return generationHandler?.(url,init) || {ok:false,json:async()=>({detail:'Try again'})};
    return {ok:true,json:async()=>[]};
  }));
  await import('../../src/tts_app/static/app.js');
  await vi.waitFor(()=>expect(fetch).toHaveBeenCalledWith('/api/voice-profiles'));
  const selection=await import('../../src/tts_app/static/profile-selection.js?v=voice-language-2');
  const stateModule=await import('../../src/tts_app/static/state.js?v=playback-progress-1');
  return {selection,state:stateModule.state,setProfiles:next=>{profiles=next;}};
}
it('shows an actionable empty state and disables Text and URL generation until a profile is available',async()=>{
  const {selection,setProfiles}=await mount();
  const generate=document.querySelector('#generate-form button[type="submit"]');
  await vi.waitFor(()=>expect(document.querySelector('#profile-select').textContent).toContain('No saved profiles'));
  expect(document.querySelector('#profile-summary').textContent).toContain('Edit');
  expect(generate.disabled).toBe(true);
  document.querySelector('#url-mode').click();expect(generate.disabled).toBe(true);
  setProfiles([profile]);await selection.loadProfiles();expect(generate.disabled).toBe(false);
  setProfiles([]);await selection.loadProfiles();expect(generate.disabled).toBe(true);
  expect(document.querySelector('#profile-status').textContent).not.toContain('Using the available language default');
});
it('keeps a retired selected profile visible and blocks generation until it is replaced',async()=>{
  const {selection,setProfiles}=await mount([{...profile,voice_available:0}]);
  const generate=document.querySelector('#generate-form button[type="submit"]');
  await vi.waitFor(()=>expect(generate.disabled).toBe(true));
  expect(document.querySelector('#profile-select').textContent).toContain('Reader');
  expect(document.querySelector('#profile-summary').textContent).toContain('unavailable');
  expect(()=>selection.voiceGenerationPayload()).toThrow('unavailable');
  setProfiles([profile]);await selection.loadProfiles();expect(generate.disabled).toBe(false);
});
it('keeps OCR draft and busy constraints while profile selection changes',async()=>{
  let finish;
  const pending=new Promise(resolve=>{finish=resolve;});
  const {selection,state,setProfiles}=await mount([profile],()=>pending);
  state.currentOcrDraftId=42;state.currentOcrDraft={id:42,language:'zh',combined_text:'Reviewed 中文',linked_generation_id:null};
  document.querySelector('#ocr-review-list').innerHTML='<textarea class="ocr-combined-text">Reviewed 中文</textarea>';
  document.querySelector('#image-mode').click();
  const generate=document.querySelector('#generate-ocr-audio');
  document.querySelector('.ocr-combined-text').dispatchEvent(new window.Event('input',{bubbles:true}));
  expect(generate.disabled).toBe(true);
  expect(document.querySelector('#profile-summary').textContent).toContain('Chinese');
  setProfiles([{...profile,language:'zh'}]);await selection.loadProfiles();expect(generate.disabled).toBe(false);
  generate.click();await vi.waitFor(()=>expect(generate.getAttribute('aria-busy')).toBe('true'));
  await selection.loadProfiles();expect(generate.disabled).toBe(true);
  setProfiles([]);await selection.loadProfiles();finish({ok:false,json:async()=>({detail:'Try again'})});
  await vi.waitFor(()=>expect(generate.getAttribute('aria-busy')).toBeNull());
  expect(generate.disabled).toBe(true);
  expect(state.currentOcrDraftId).toBe(42);expect(state.currentOcrDraft.language).toBe('zh');
  expect(document.querySelector('.ocr-combined-text').value).toBe('Reviewed 中文');
});
