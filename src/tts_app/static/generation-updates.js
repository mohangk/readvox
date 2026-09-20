// Observe a server-owned job. Stopping observation never cancels synthesis.
export function createGenerationUpdates({ refresh, onMessage, onDisconnect, onSource, createSource = (url) => new EventSource(url) }) {
  let source = null;
  let timer = null;
  let version = 0;

  function stop() {
    version += 1;
    if (timer !== null) clearTimeout(timer);
    timer = null;
    if (source) source.close();
    source = null;
    onSource(null);
  }

  function start(generationId) {
    stop();
    const current = version;
    let refreshing = false;
    async function update() {
      if (current !== version || refreshing) return;
      refreshing = true;
      try {
        const status = await refresh(generationId);
        if (current === version && ["completed", "failed"].includes(status)) stop();
      } catch {
        if (current === version) onDisconnect();
      } finally {
        refreshing = false;
      }
    }
    async function poll() {
      await update();
      if (current === version) timer = setTimeout(poll, 5000);
    }
    try {
      source = createSource(`/api/generations/${generationId}/events`);
      onSource(source);
      source.onopen = update;
      source.onmessage = (message) => {
        if (current === version) onMessage(message, generationId);
      };
      // EventSource reconnects itself; polling also covers missed terminal events.
      source.onerror = () => { if (current === version) onDisconnect(); };
    } catch {
      onDisconnect();
    }
    timer = setTimeout(poll, 5000);
  }
  return { start, stop };
}
