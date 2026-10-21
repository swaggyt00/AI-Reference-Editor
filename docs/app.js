'use strict';
const API_ORIGIN = 'http://127.0.0.1:8000';
// The GitHub Pages site sends files DIRECTLY from the browser to this Windows PC.
// Never relay media through GitHub or a remote server.
function apiUrl(path) {
  if (typeof path !== 'string' || !path.startsWith('/api/')) throw new Error('Invalid local API path');
  return API_ORIGIN + path;
}

const $ = (id) => document.getElementById(id);
const headers = {'X-Refeditor-Client': 'web'};
let projectId = null, reference = null, sources = [], library = [], runs = [], busy = false;
let selectedRun = null, pollTimer = null, maxBytes = 2 * 1024 ** 3, ready = false;
const active = (run) => ['queued', 'running'].includes(run.status);
const storage = {
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch { /* Storage is optional. */ } },
  remove(key) { try { localStorage.removeItem(key); } catch { /* Storage is optional. */ } }
};
function message(text) { $('error').textContent = text; $('error').hidden = !text; }
function size(bytes) { return bytes >= 1024 ** 3 ? `${(bytes / 1024 ** 3).toFixed(1)} ГБ` : bytes >= 1024 ** 2 ? `${(bytes / 1024 ** 2).toFixed(1)} МБ` : `${Math.ceil(bytes / 1024)} КБ`; }
function settings() {
  return {brief: $('brief').value, mode: $('mode').value, audio: $('audio').value,
    align_audio: $('align-audio').checked, max_seconds: $('duration').value ? Number($('duration').value) : null,
    source_ids: sources.filter(s => s.id).map(s => s.id)};
}
function saveDraft() {
  if (projectId) storage.set(`refeditor-draft-${projectId}`, JSON.stringify(settings()));
}
function saveProject() {
  storage.set('refeditor-project', projectId);
  history.replaceState(null, '', `#${projectId}`);
  saveDraft();
}
async function api(url, options = {}) {
  const response = await fetch(apiUrl(url), {...options, headers: {...headers, ...options.headers}});
  if (!response.ok) {
    let data; try { data = await response.json(); } catch { data = {}; }
    const detail = typeof data.detail === 'string' ? data.detail : 'Проверьте параметры запроса.';
    const error = new Error(`${detail} (${response.status})`); error.status = response.status; throw error;
  }
  return response.json();
}
function setBusy(value) {
  busy = value;
  $('editor-fields').disabled = value;
  $('new-project').disabled = value;
  $('run').disabled = value || !ready;
  if (value) $('run').textContent = 'Обработка…';
  else $('run').textContent = runs.length ? '↻ Повторить рендер' : '▶ Анализировать и смонтировать ↗';
  $('run-hint').textContent = runs.length ? 'Меняйте задание и настройки. Предыдущие версии сохранятся.' : 'Файлы обрабатываются на сервере этого приложения.';
}
function status(stage, percent, detail, phase = -1) {
  $('stage').textContent = stage;
  $('percentage').textContent = `${Math.round(percent)}%`;
  $('progress').value = percent;
  $('progress-detail').textContent = detail;
  document.querySelectorAll('.stage-list li').forEach((li, i) => li.classList.toggle('active', i <= phase));
}
function button(text, label, handler, disabled = false) {
  const element = document.createElement('button');
  element.type = 'button'; element.className = 'icon-button'; element.textContent = text;
  element.setAttribute('aria-label', label); element.title = label; element.disabled = disabled;
  element.addEventListener('click', handler); return element;
}
function fileRow(asset, index = null) {
  const row = document.createElement(index === null ? 'div' : 'li'); row.className = 'file-row';
  const icon = document.createElement('span'); icon.className = 'file-icon'; icon.textContent = index === null ? 'REF' : String(index + 1).padStart(2, '0');
  const description = document.createElement('div'); description.className = 'file-description';
  const name = document.createElement('div'); name.className = 'file-name'; name.textContent = asset.name; name.title = asset.name;
  const meta = document.createElement('div'); meta.className = 'file-meta';
  meta.textContent = `${size(asset.size)} · ${asset.id ? 'Загружено' : 'Готово к загрузке'}`;
  if (asset.metadata) meta.textContent += ` · ${asset.metadata.duration.toFixed(1)} с`;
  description.append(name, meta); row.append(icon, description);
  const actions = document.createElement('div'); actions.className = 'file-actions';
  if (index !== null) {
    actions.append(button('↑', `Поднять ${asset.name}`, () => {
      [sources[index - 1], sources[index]] = [sources[index], sources[index - 1]]; renderFiles(); saveDraft();
    }, index === 0));
    actions.append(button('↓', `Опустить ${asset.name}`, () => {
      [sources[index + 1], sources[index]] = [sources[index], sources[index + 1]]; renderFiles(); saveDraft();
    }, index === sources.length - 1));
    actions.append(button('×', `Убрать из монтажа ${asset.name}`, () => {sources.splice(index, 1); renderFiles(); saveDraft();}));
  } else if (!asset.id) {
    actions.append(button('×', 'Убрать референс', () => { reference = null; renderFiles(); }));
  }
  row.append(actions); return row;
}
function renderFiles() {
  $('reference-drop').hidden = Boolean(reference);
  $('reference-info').hidden = !reference;
  $('reference-info').replaceChildren();
  if (reference) $('reference-info').append(fileRow(reference));
  $('source-list').replaceChildren(...sources.map((asset, i) => fileRow(asset, i)));
  $('source-count').textContent = `${sources.length} / 32`;
  $('library-status').hidden = !library.length;
  $('library-status').textContent = `На сервере ${library.length} / 32 исходников. Убранные из монтажа файлы сохраняются для прошлых версий и учитываются в лимите проекта.`;
  $('restore-sources').hidden = !library.some(asset => !sources.some(s => s.id === asset.id));
}
$('restore-sources').addEventListener('click', () => {
  sources.push(...library.filter(asset => !sources.some(s => s.id === asset.id)));
  renderFiles(); saveDraft();
});
function acceptFiles(files, role) {
  if (busy) return;
  message('');
  if (role === 'reference' && reference?.id) { message('Для другого референса начните новый проект.'); return; }
  if (role === 'reference' && files.length !== 1) { message('Выберите один референс.'); return; }
  const valid = [];
  for (const file of files) {
    if (file.size > maxBytes || !file.size) { message(`«${file.name}»: файл пустой или больше ${size(maxBytes)}.`); continue; }
    valid.push({file, name: file.name, size: file.size});
  }
  if (role === 'reference') reference = valid[0] || reference;
  else {
    if (library.length + sources.filter(s => !s.id).length + valid.length > 32) {
      message('В проекте можно хранить до 32 исходников, включая убранные из монтажа. Верните загруженные файлы или начните новый проект.'); return;
    }
    sources.push(...valid);
  }
  renderFiles();
}
for (const [inputId, dropId, role] of [['reference', 'reference-drop', 'reference'], ['sources', 'source-drop', 'source']]) {
  $(inputId).addEventListener('change', event => {acceptFiles([...event.target.files], role); event.target.value = '';});
  const zone = $(dropId);
  zone.addEventListener('dragover', event => {event.preventDefault(); if (!busy) zone.classList.add('dragging');});
  zone.addEventListener('dragleave', () => zone.classList.remove('dragging'));
  zone.addEventListener('drop', event => {event.preventDefault(); zone.classList.remove('dragging'); acceptFiles([...event.dataTransfer.files], role);});
}
function upload(asset, role, number, total) {
  return new Promise((resolve, reject) => {
    asset.uploadId ||= Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('');
    const xhr = new XMLHttpRequest();
    xhr.open('POST', apiUrl(`/api/projects/${projectId}/media?${new URLSearchParams({role, name: asset.name, upload_id: asset.uploadId})}`));
    xhr.setRequestHeader('X-Refeditor-Client', 'web');
    xhr.upload.onprogress = event => {
      const fraction = event.lengthComputable ? event.loaded / event.total : 0;
      status(`Загрузка ${number} из ${total}`, ((number - 1 + fraction) / total) * 100,
        fraction === 1 ? `Проверяем видео «${asset.name}»…` : asset.name, 0);
    };
    xhr.onerror = () => reject(new Error('Соединение прервалось при загрузке. Уже загруженные файлы сохранены. Повторите запуск.'));
    xhr.onload = () => {
      let data; try { data = JSON.parse(xhr.responseText); } catch { data = {}; }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else reject(new Error(typeof data.detail === 'string' ? data.detail : `Не удалось загрузить файл (${xhr.status}).`));
    };
    xhr.send(asset.file);
  });
}
async function showResult(run) {
  if (!run || run.status !== 'completed') return;
  selectedRun = run.id;
  $('empty-preview').hidden = true; $('preview').hidden = false;
  if ($('preview').getAttribute('src') !== apiUrl(run.video_url)) { $('preview').src = apiUrl(run.video_url); $('preview').load(); }
  $('preview-label').textContent = `ВЕРСИЯ ${String(run.version).padStart(2, '0')} / MP4`;
  $('download').hidden = false; $('download').href = apiUrl(run.download_url);
  $('download').download = `reference-edit-v${run.version}.mp4`;
  $('artifact-links').hidden = false;
  $('project-link').href = apiUrl(run.project_url); $('project-link').download = `project-v${run.version}.json`;
  $('qa-link').href = apiUrl(run.qa_url); $('comparison-link').href = apiUrl(run.comparison_url);
  $('result-meta').textContent = `Версия ${run.version}`;
  renderVersions();
  try {
    const qa = await api(run.qa_url);
    if (selectedRun === run.id) $('result-meta').textContent = `${qa.resolution} · ${qa.duration_s} с · ${qa.audio_present ? 'Со звуком' : 'Без звука'}`;
  } catch { /* The video stays available if the optional report cannot load. */ }
}
function renderVersions() {
  $('versions-card').hidden = !runs.length;
  $('versions').replaceChildren();
  for (const run of [...runs].reverse()) {
    const row = document.createElement('div'); row.className = 'version';
    const label = document.createElement('div'); label.textContent = `Версия ${String(run.version).padStart(2, '0')}`;
    const sub = document.createElement('small');
    sub.textContent = {completed: 'Готово', failed: 'Ошибка', queued: 'В очереди', running: 'Обработка'}[run.status];
    label.append(sub); row.append(label);
    if (run.status === 'completed') {
      const view = button(selectedRun === run.id ? 'На экране' : 'Смотреть', `Смотреть версию ${run.version}`, () => showResult(run));
      view.className = 'button'; view.setAttribute('aria-pressed', String(selectedRun === run.id)); row.append(view);
    }
    $('versions').append(row);
  }
}
function showWarnings(run) {
  $('warnings').replaceChildren(); $('warnings').hidden = !run.warnings?.length;
  for (const text of run.warnings || []) { const p = document.createElement('p'); p.textContent = text; $('warnings').append(p); }
}
function updateRunState(state) {
  const oldLast = runs.at(-1);
  runs = state.renders;
  renderVersions();
  const latest = runs.at(-1);
  if (!latest) { setBusy(false); return; }
  const working = active(latest);
  setBusy(working);
  const phase = latest.progress >= 91 ? 3 : latest.progress >= 38 ? 2 : 1;
  status(latest.stage, latest.progress, working ? 'Процент отражает этапы обработки и количество обработанных кадров.' :
    latest.status === 'completed' ? 'Можно скачать видео или изменить настройки и создать новую версию.' : latest.error, phase);
  showWarnings(latest);
  if (latest.status === 'failed') message(latest.error);
  if (latest.status === 'completed' && (!selectedRun || oldLast?.status !== 'completed')) showResult(latest);
  else if (!selectedRun) showResult([...runs].reverse().find(r => r.status === 'completed'));
  if (working) schedulePoll();
}
function schedulePoll(delay = 1000) {
  clearTimeout(pollTimer);
  const pid = projectId;
  pollTimer = setTimeout(async () => {
    try {
      const state = await api(`/api/projects/${pid}`);
      if (pid !== projectId) return;
      message(''); updateRunState(state);
    } catch (error) {
      if (pid !== projectId) return;
      if (error.status === 404) { setBusy(false); message('Проект не найден на сервере. Начните новый проект.'); return; }
      message('Связь с сервером потеряна. Обработка могла продолжиться; повторяем подключение…'); schedulePoll(3000);
    }
  }, delay);
}
$('editor-form').addEventListener('submit', async event => {
  event.preventDefault(); if (busy) return;
  message('');
  if (!reference || !sources.length) { message('Выберите референс и хотя бы один исходник.'); return; }
  setBusy(true);
  try {
    if (!projectId) { const state = await api('/api/projects', {method: 'POST'}); projectId = state.id; saveProject(); }
    const pending = [reference, ...sources].filter(asset => asset.file && !asset.id);
    let count = 0;
    for (const asset of pending) {
      const saved = await upload(asset, asset === reference ? 'reference' : 'source', ++count, pending.length);
      Object.assign(asset, saved); delete asset.file;
      if (asset !== reference && !library.some(s => s.id === saved.id)) library.push(saved);
      renderFiles(); saveDraft();
    }
    status('Запуск обработки', 0, 'Передаём задание движку…', 1);
    saveDraft();
    const run = await api(`/api/projects/${projectId}/renders`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(settings())});
    runs.push(run); renderVersions(); schedulePoll(100);
  } catch (error) {
    // Recover an accepted job if its POST response was lost.
    let working = false;
    if (projectId) {
      try {
        const state = await api(`/api/projects/${projectId}`);
        working = state.renders.some(active) || state.renders.some(r => !runs.some(existing => existing.id === r.id));
        if (working) updateRunState(state);
      } catch { /* Retry is still possible after the server returns. */ }
    }
    if (!working) { setBusy(false); status('Не удалось запустить', 0, 'Исправьте ошибку и повторите запуск.'); message(error.message); }
  }
});
function updateHints() {
  $('mode-hint').textContent = $('mode').value === 'fit' ? 'Fit меняет скорость исходников под длину сцен референса.' : 'Native сохраняет скорость; если исходник короче сцены, последний кадр удерживается.';
  $('audio-hint').hidden = $('audio').value === 'none';
}
['brief', 'mode', 'audio', 'duration', 'align-audio'].forEach(id => $(id).addEventListener('input', () => {updateHints(); saveDraft();}));
$('new-project').addEventListener('click', () => {
  if (busy) return;
  clearTimeout(pollTimer); projectId = null; reference = null; sources = []; library = []; runs = []; selectedRun = null;
  storage.remove('refeditor-project'); history.replaceState(null, '', location.pathname);
  $('editor-form').reset(); $('preview').pause(); $('preview').removeAttribute('src'); $('preview').load();
  $('preview').hidden = true; $('empty-preview').hidden = false; $('download').hidden = true;
  $('artifact-links').hidden = true; $('warnings').hidden = true;
  $('result-meta').textContent = 'Ожидаем материалы'; $('preview-label').textContent = 'MP4 / H.264';
  message(''); renderFiles(); renderVersions(); updateHints(); setBusy(false);
  status('Готов к работе', 0, 'Загрузите референс и хотя бы один исходник.');
});
window.addEventListener('beforeunload', event => {
  if (busy && [reference, ...sources].some(asset => asset?.file)) {event.preventDefault(); event.returnValue = '';}
});
$('preview').addEventListener('error', () => {
  if ($('preview').getAttribute('src')) message('Браузер не смог воспроизвести видео. Попробуйте скачать MP4 и открыть его в видеоплеере.');
});
async function init() {
  setBusy(true);
  try {
    const health = await api('/api/health'); ready = health.ready; maxBytes = health.max_upload_bytes;
    $('connection').textContent = 'Движок подключён'; $('connection').classList.add('ready');
    $('file-limit').textContent = `Форматы FFmpeg · до ${size(maxBytes)} на файл · до ${size(health.max_project_bytes)} в проекте`;
  } catch { $('connection').textContent = 'Движок недоступен'; message('Локальный монтажный сервер недоступен. Запустите start-editor.cmd на своём Windows-ПК, убедитесь, что FFmpeg установлен, и обновите страницу. Если Chrome попросит разрешить доступ к локальной сети — разрешите.'); }
  const saved = location.hash.slice(1) || storage.get('refeditor-project');
  if (saved && /^[a-f0-9]{32}$/.test(saved)) {
    try {
      const state = await api(`/api/projects/${saved}`);
      projectId = saved; reference = state.reference; sources = [...state.sources]; library = state.sources;
      let draft; try { draft = JSON.parse(storage.get(`refeditor-draft-${saved}`)); } catch { draft = null; }
      const options = draft || state.renders.at(-1)?.settings;
      if (options) {
        $('brief').value = options.brief || ''; $('mode').value = options.mode || 'fit';
        $('audio').value = options.audio || 'none'; $('duration').value = options.max_seconds ?? '';
        $('align-audio').checked = options.align_audio || false;
        if (Array.isArray(options.source_ids)) sources = options.source_ids.map(id => state.sources.find(s => s.id === id)).filter(Boolean);
      }
      saveProject(); renderFiles(); updateHints(); updateRunState(state);
    } catch (error) {
      if (error.status === 404) storage.remove('refeditor-project');
      message('Не удалось восстановить проект. Проверьте сервер или начните новый проект.'); setBusy(false);
    }
  } else setBusy(false);
}
init();
