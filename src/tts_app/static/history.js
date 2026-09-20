import { escapeHtml, formatSpeed, withButtonBusy } from "./utils.js?v=playback-progress-1";

export function renderHistoryItems(generations, search = "") {
  const query = search.trim().toLowerCase();
  const rows = generations.filter((item) => {
    const text = `${item.title} ${item.text_preview} ${item.url ?? ""} ${item.voice} ${item.settings?.profile_name ?? ""} ${item.settings?.speed ?? ""}`.toLowerCase();
    return text.includes(query);
  });

  if (rows.length === 0) {
    return '<div class="history-item">No generations found</div>';
  }

  return rows
    .map((item) => {
      const created = item.created_at ? new Date(`${item.created_at}Z`).toLocaleString() : "";
      const speed = item.settings?.speed ?? 1;
      const progress = Number(item.progress_percent || 0);
      const urlMarkup = item.url
        ? `<div class="history-item-url">${escapeHtml(item.url)}</div>`
        : "";
      const failed = item.status === "failed";
      const failureMarkup = failed
        ? '<div class="history-failure"><svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3 2 21h20Z"/><path d="M12 9v5m0 3v1"/></svg> Generation failed</div>'
        : "";
      const generatedMarkup = Number.isInteger(item.total_segments)
        ? `<div class="history-item-meta">Generated ${escapeHtml(item.completed_segments ?? 0)} / ${escapeHtml(item.total_segments)} segments</div>` : "";
      const resumeMarkup = failed && item.can_resume
        ? `<button class="secondary-action compact-action" type="button" data-action="resume" data-generation-id="${item.id}">Resume</button>` : "";
      const recoveryNote = failed && item.resume_unavailable_reason
        ? `<p class="history-item-meta">${escapeHtml(item.resume_unavailable_reason)}</p>` : "";
      const errorMarkup = item.error
        ? `<div><dt>Error</dt><dd class="history-error">${escapeHtml(item.error)}</dd></div>`
        : "";
      return `
        <article class="history-item${failed ? " history-item-failed" : ""}" data-generation-id="${item.id}">
          <div class="history-item-title">${escapeHtml(item.title)}</div>
          ${failureMarkup}
          ${generatedMarkup}
          ${recoveryNote}
          <div class="history-item-meta">${escapeHtml(item.status)} ${escapeHtml(created)}</div>
          ${urlMarkup}
          <div class="history-item-preview">${escapeHtml(item.text_preview)}</div>
          <details class="history-details">
            <summary>Details</summary>
            <dl>
              <div><dt>Voice</dt><dd>${escapeHtml(item.settings?.profile_name || item.voice)}</dd></div>
              <div><dt>Speed</dt><dd>${escapeHtml(formatSpeed(speed))}</dd></div>
              <div><dt>Provider</dt><dd>${escapeHtml(item.provider)}</dd></div>
              <div><dt>Listening progress</dt><dd>${escapeHtml(progress)}%</dd></div>
              ${errorMarkup}
            </dl>
          </details>
          <p class="history-item-meta" role="status"></p>
          <div class="history-actions">
            ${resumeMarkup}
            <button class="secondary-action compact-action" type="button" data-action="open" data-generation-id="${item.id}">Open</button>
            <button class="danger-action compact-action" type="button" data-action="delete" data-generation-id="${item.id}">Delete</button>
          </div>
        </article>
      `;
    })
    .join("");
}

export function createHistory({ historyList, historySearch, playerStatus, state, openGeneration, resetPlaybackState }) {
  async function loadHistory() {
    try {
      const response = await fetch("/api/generations");
      if (!response.ok) {
        historyList.innerHTML = '<div class="history-item">Unable to load history</div>';
        return;
      }
      state.generations = await response.json();
      renderHistory();
    } catch {
      historyList.innerHTML = '<div class="history-item">Unable to load history</div>';
    }
  }

  function renderHistory() {
    historyList.innerHTML = renderHistoryItems(state.generations, historySearch.value);
  }

  async function deleteGeneration(generationId, button = null) {
    if (!window.confirm("Delete this history entry and cached audio?")) {
      return;
    }
    await withButtonBusy(button, "Deleting...", async () => {
      try {
        const response = await fetch(`/api/generations/${generationId}`, { method: "DELETE" });
        if (!response.ok) {
          playerStatus.textContent = "Unable to delete history entry";
          return;
        }
        if (state.currentGenerationId === generationId) {
          resetPlaybackState("Deleted generation");
        }
        await loadHistory();
      } catch {
        playerStatus.textContent = "Unable to delete history entry";
      }
    });
  }

  async function resumeGeneration(generationId, button = null) {
    const status = button?.closest(".history-item")?.querySelector('[role="status"]');
    const showError = (message) => {
      playerStatus.textContent = message;
      if (status) status.textContent = message;
    };
    if (status) status.textContent = "";
    await withButtonBusy(button, "Resuming...", async () => {
      try {
        const response = await fetch(`/api/generations/${generationId}/resume`, { method: "POST" });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          showError(body.detail || "Unable to resume generation");
          return;
        }
        await openGeneration(generationId, { subscribe: true, autoplay: false });
      } catch {
        showError("Unable to resume generation. Refresh History to check its status.");
      }
    });
  }

  function registerEvents() {
    historySearch.addEventListener("input", renderHistory);
    historyList.addEventListener("click", (event) => {
      const action = event.target.closest("[data-action]");
      const historyItem = event.target.closest("[data-generation-id]");
      if (!historyItem) {
        return;
      }
      const generationId = Number(historyItem.dataset.generationId);
      if (action?.dataset.action === "resume") {
        resumeGeneration(Number(action.dataset.generationId), action);
        return;
      }
      if (action?.dataset.action === "delete") {
        deleteGeneration(Number(action.dataset.generationId), action);
        return;
      }
      if (action?.dataset.action === "open") {
        openGeneration(Number(action.dataset.generationId), { subscribe: false, autoplay: true, button: action });
        return;
      }
      if (!action) {
        if (event.target.closest(".history-details") && !action) {
          return;
        }
        openGeneration(generationId, { subscribe: false, autoplay: true });
      }
    });

  }

  return { loadHistory, renderHistory, deleteGeneration, resumeGeneration, registerEvents };
}
