import { expect, it } from 'vitest';
import { renderHistoryItems } from '../../src/tts_app/static/history.js';

const row={id:17,title:'Book',text_preview:'Opening',voice:'cloud-original-id',provider:'qwen',settings:{profile_name:'Evening <reader>',speed:1.1},progress_percent:25};
it('displays and searches the immutable profile name while escaping markup',()=>{
  document.body.innerHTML=renderHistoryItems([row],'evening');
  expect(document.querySelector('.history-item')).not.toBeNull();
  expect(document.querySelector('dd').textContent).toBe('Evening <reader>');
  expect(document.querySelector('reader')).toBeNull();
  expect(document.body.textContent).not.toContain('cloud-original-id');
  expect(document.querySelector('[data-action="open"]').dataset.generationId).toBe('17');
  expect(document.querySelector('[data-action="delete"]').dataset.generationId).toBe('17');
});
it('keeps the original voice searchable and falls back to it for old generations',()=>{
  const legacy={...row,id:18,settings:{speed:1}};
  document.body.innerHTML=renderHistoryItems([row,legacy],'cloud-original');
  expect(document.querySelectorAll('.history-item')).toHaveLength(2);
  expect(document.querySelectorAll('dd')[4].textContent).toBe('cloud-original-id');
  expect(renderHistoryItems([row],'missing')).toContain('No generations found');
});
