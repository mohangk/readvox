import { afterEach, describe, expect, it, vi } from 'vitest';
import { createGenerationUpdates } from '../../src/tts_app/static/generation-updates.js';

afterEach(() => vi.useRealTimers());

describe('background generation updates', () => {
  it('refreshes on reconnect and polls through disconnection until completion', async () => {
    vi.useFakeTimers();
    const source = { close: vi.fn() };
    const refresh = vi.fn().mockResolvedValueOnce('running').mockResolvedValueOnce('running').mockResolvedValue('completed');
    const disconnect = vi.fn();
    const updates = createGenerationUpdates({ refresh, onMessage: vi.fn(), onDisconnect: disconnect, onSource: vi.fn(), createSource: () => source });
    updates.start(7);
    await source.onopen();
    source.onerror();
    expect(disconnect).toHaveBeenCalled();
    expect(source.close).not.toHaveBeenCalled();
    await source.onopen();
    await vi.advanceTimersByTimeAsync(5000);
    expect(refresh).toHaveBeenCalledWith(7);
    expect(source.close).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('stops observers without cancelling generation and ignores stale callbacks', async () => {
    vi.useFakeTimers();
    const sources = [];
    const refresh = vi.fn().mockResolvedValue('running');
    const onMessage = vi.fn();
    const updates = createGenerationUpdates({ refresh, onMessage, onDisconnect: vi.fn(), onSource: vi.fn(), createSource: () => {
      const source = {close: vi.fn()}; sources.push(source); return source;
    }});
    updates.start(7);
    const oldCallback = sources[0].onmessage;
    updates.start(8);
    oldCallback({data:'old event'});
    expect(onMessage).not.toHaveBeenCalled();
    updates.stop();
    await vi.advanceTimersByTimeAsync(10000);
    expect(refresh).not.toHaveBeenCalled();
    expect(sources.every(s => s.close.mock.calls.length === 1)).toBe(true);
  });
});
