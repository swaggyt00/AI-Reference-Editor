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
let projectId = null, reference = null, music = null, sources = [], library = [], runs = [], busy = false;
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
    editor_mode: $('editor-mode').value, reel_seconds: Number($('reel-seconds').value || 60),
    align_audio: $('align-audio').checked, ai_semantic: $('ai-semantic').checked,
    motion_design: $('motion-design').checked,
    max_seconds: $('duration').value ? Number($('duration').value) : null,
    source_ids: sources.filter(s => s.id).map(s => s.id)};
}
function saveDraft() {
  if (projectId) storage.set(`refeditor-draft-${projectId}`, JSON.stringify(settings()));
}
function saveProject() {
  storage.set('refeditor-project', projectId);
  $('delete-project').hidden = false;
  history.replaceState(null, '', `#${projectId}`);
  saveDraft();
}
async function api(url, options = {}) {
  const response = await fetch(apiUrl(url), {...options, mode: 'cors', targetAddressSpace: 'loopback', headers: {...headers, ...options.headers}});
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
  $('delete-project').disabled = value;
  $('manage-projects').disabled = value;
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
async function deleteUploaded(asset, role) {
  if (busy || !asset) return;
  if (!asset.id) {
    if (role === 'reference') reference = null;
    else if (role === 'music') music = null;
    else sources = sources.filter(s => s !== asset);
    renderFiles(); saveDraft(); return;
  }
  if (!window.confirm('Безвозвратно удалить загруженный файл «' + asset.name +
    '» с этого ПК? Готовые MP4 и версии монтажа останутся. Для удаления ВСЕГО нажми «Удалить проект».')) return;
  setBusy(true); message('');
  try {
    const state = await api('/api/projects/' + projectId + '/media/' + asset.id, {method:'DELETE'});
    if (role === 'reference') reference = null;
    else if (role === 'music') music = null;
    else sources = sources.filter(s => s.id !== asset.id);
    library = state.sources;
    renderFiles(); saveDraft();
    message('Файл «' + asset.name + '» удалён с ПК. Готовые рендеры сохранены.');
  } catch (error) {
    message('Не удалось удалить файл: ' + error.message);
  } finally {
    setBusy(false);
  }
}
function fileRow(asset, index = null, role = 'source') {
  const selectedSource = role === 'source';
  const row = document.createElement(selectedSource ? 'li' : 'div'); row.className = 'file-row';
  const icon = document.createElement('span'); icon.className = 'file-icon';
  icon.textContent = role === 'reference' ? 'REF' : index === null ? 'SRC' : String(index + 1).padStart(2, '0');
  const description = document.createElement('div'); description.className = 'file-description';
  const name = document.createElement('div'); name.className = 'file-name'; name.textContent = asset.name; name.title = asset.name;
  const meta = document.createElement('div'); meta.className = 'file-meta';
  meta.textContent = `${size(asset.size)} · ${asset.id ? 'Загружено' : 'Готово к загрузке'}`;
  if (asset.metadata) meta.textContent += ` · ${asset.metadata.duration.toFixed(1)} с`;
  description.append(name, meta); row.append(icon, description);
  const actions = document.createElement('div'); actions.className = 'file-actions';
  if (selectedSource) {
    actions.append(button('↑', `Поднять ${asset.name}`, () => {
      [sources[index - 1], sources[index]] = [sources[index], sources[index - 1]]; renderFiles(); saveDraft();
    }, index === 0));
    actions.append(button('↓', `Опустить ${asset.name}`, () => {
      [sources[index + 1], sources[index]] = [sources[index], sources[index + 1]]; renderFiles(); saveDraft();
    }, index === sources.length - 1));
    actions.append(button('−', `Убрать из монтажа, оставить на ПК: ${asset.name}`,
      () => { sources.splice(index, 1); renderFiles(); saveDraft(); }));
  }
  const trash = button('🗑', `Удалить с ПК: ${asset.name}`, () =>
    deleteUploaded(asset, role === 'reference' ? 'reference' : 'source'));
  trash.classList.add('danger-icon');
  actions.append(trash);
  row.append(actions); return row;
}
function renderFiles() {
  $('reference-drop').hidden = Boolean(reference);
  $('music-drop').hidden = Boolean(music);
  $('music-info').textContent = music ? `♫ ${music.name} · ${music.id ? 'Загружено' : 'Готово к загрузке'}` : 'Музыка не выбрана';
  $('delete-music').hidden = !music;
  $('reference-info').hidden = !reference;
  $('reference-info').replaceChildren();
  if (reference) $('reference-info').append(fileRow(reference, null, 'reference'));
  $('source-list').replaceChildren(...sources.map((asset, i) => fileRow(asset, i, 'source')));
  $('source-count').textContent = `${sources.length} / 32`;
  const unused = library.filter(asset => !sources.some(s => s.id === asset.id));
  $('library-status').hidden = !library.length;
  $('library-status').textContent = `На ПК загружено ${library.length} / 32 исходников. Ненужные файлы можно удалить через 🗑.`;
  $('restore-sources').hidden = !unused.length;
  $('unused-source-list').hidden = !unused.length;
  $('unused-source-list').replaceChildren(...unused.map(asset => fileRow(asset, null, 'source-hidden')));
}
$('restore-sources').addEventListener('click', () => {
  sources.push(...library.filter(asset => !sources.some(s => s.id === asset.id)));
  renderFiles(); saveDraft();
});
$('delete-music').addEventListener('click', () => {
  if (music) deleteUploaded(music, 'music');
});
function acceptFiles(files, role) {
  if (busy) return;
  message('');
  if (role === 'reference' && reference?.id) { message('Для другого референса начните новый проект.'); return; }
  if (role === 'music' && music?.id) { message('Для другой музыки начните новый проект.'); return; }
  if ((role === 'reference' || role === 'music') && files.length !== 1) { message('Выберите один файл.'); return; }
  const valid = [];
  for (const file of files) {
    if (file.size > maxBytes || !file.size) { message(`«${file.name}»: файл пустой или больше ${size(maxBytes)}.`); continue; }
    valid.push({file, name: file.name, size: file.size});
  }
  if (role === 'reference') reference = valid[0] || reference;
  else if (role === 'music') music = valid[0] || music;
  else {
    if (library.length + sources.filter(s => !s.id).length + valid.length > 32) {
      message('В проекте можно хранить до 32 исходников, включая убранные из монтажа. Верните загруженные файлы или начните новый проект.'); return;
    }
    sources.push(...valid);
  }
  renderFiles();
}
for (const [inputId, dropId, role] of [['reference', 'reference-drop', 'reference'], ['sources', 'source-drop', 'source'], ['music', 'music-drop', 'music']]) {
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
  $('motion-qa-link').hidden = !run.settings?.motion_design;
  if (run.settings?.motion_design) $('motion-qa-link').href = apiUrl(run.motion_qa_url);
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
  const reel = $('editor-mode').value === 'smart_reels';
  if (!sources.length || (!reel && !reference)) {
    message(reel ? 'Для Smart Reels нужен исходный длинный ролик.' : 'Нужны референс и хотя бы один исходник.');
    return;
  }
  if (reel && sources.length !== 1) { message('Smart Reels пока принимает один длинный исходник.'); return; }
  if (reel && !$('ai-semantic').checked) { message('Для интеллектуального Smart Reels включите галочку Gemini и подтвердите передачу сжатой копии видео.'); return; }
  if ($('motion-design').checked && (reel || !$('ai-semantic').checked)) {
    message('Motion Design требует Reference Clone и включённого Gemini AI.');
    return;
  }
  if ($('ai-semantic').checked) {
    if (!reel && sources.length > 3) { message('Reference Clone AI поддерживает максимум 3 исходника.'); return; }
    const motionWarning = $('motion-design').checked ? ' ВКЛЮЧЁН Motion Design: помимо видео, Google получит до 3 обзорных листов с кадрами и таймкодами. Возможен расход API-квоты. Простая графика с подходящим фоном будет восстановлена; сложные эффекты не гарантируются. Требуется setup-motion.cmd.' : '';
    const disclaimer = reel
      ? 'Отправить сжатую копию длинного ролика со звуком в Google Gemini? Понадобится API-квота. Gemini выберет интересные моменты, но может ошибиться. Финальный монтаж выполняется на ПК.'
      : 'Отправить сжатые копии референса и исходников в Google Gemini для анализа? Понадобится API-квота. Сложные VFX пока воспроизводятся только частично.';
    if (!window.confirm(disclaimer + motionWarning)) return;
  }
  setBusy(true);
  try {
    if (!projectId) { const state = await api('/api/projects', {method: 'POST'}); projectId = state.id; saveProject(); }
    const pending = [reference, ...sources, music].filter(asset => asset?.file && !asset.id);
    let count = 0;
    for (const asset of pending) {
      const saved = await upload(asset, asset === reference ? 'reference' : asset === music ? 'music' : 'source', ++count, pending.length);
      Object.assign(asset, saved); delete asset.file;
      if (asset !== reference && asset !== music && !library.some(s => s.id === saved.id)) library.push(saved);
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
  const smart = $('editor-mode').value === 'smart_reels';
  $('reference-section').hidden = smart;
  $('reels-fields').hidden = !smart;
  $('reference-options').hidden = smart;
  $('source-order-hint').textContent = smart
    ? 'Для Smart Reels выберите один исходный ролик 15 секунд — 30 минут.'
    : 'В Reference Clone движок переносит подтверждённые склейки и маски; Gemini подбирает исходники.';
  $('brief-mode-hint').textContent = smart
    ? 'Gemini учитывает вашу задачу при выборе лучших моментов и монтаже короткого Reels.'
    : 'В Reference Clone свободная задача — подсказка Gemini, точное выполнение сложных указаний не гарантируется.';
  $('ai-consent-hint').textContent = smart
    ? 'Для Smart Reels требуется Gemini: сжатая копия со звуком отправляется в Google с вашего согласия. Ролики до 30 минут. Не гарантируется идеальный выбор моментов.'
    : 'Gemini отправляются сжатые копии видео со звуком; в Motion Design ещё и обзорные кадры референса — только с вашего согласия. До 3 исходников и 60 секунд на видео. Сложные эффекты воспроизводятся частично.';
  $('mode-hint').textContent = $('mode').value === 'fit' ? 'Fit меняет скорость исходников под длину сцен референса.' : 'Native сохраняет скорость; если исходник короче сцены, последний кадр удерживается.';
  $('audio-hint').hidden = $('audio').value === 'none';
}
['brief', 'mode', 'audio', 'duration', 'align-audio', 'editor-mode', 'reel-seconds', 'ai-semantic', 'motion-design'].forEach(id =>
  $(id).addEventListener('input', () => {updateHints(); saveDraft();}));
async function loadProjectLibrary() {
  const list = await api('/api/projects');
  $('project-library').replaceChildren();
  if (!list.length) {
    const blank = document.createElement('p');
    blank.className = 'hint'; blank.textContent = 'На этом ПК пока нет сохранённых проектов.';
    $('project-library').append(blank);
    return;
  }
  for (const item of list) {
    const row = document.createElement('div'); row.className = 'project-row';
    const label = document.createElement('div'); label.className = 'project-label';
    const title = document.createElement('strong');
    title.textContent = item.reference_name || 'Проект без референса';
    const subtitle = document.createElement('small');
    subtitle.textContent = [
      item.sources + ' исходников', item.renders + ' версий',
      size(item.uploaded_bytes) + ' исходных файлов',
      new Date(item.updated * 1000).toLocaleString('ru-RU'),
      item.id === projectId ? 'Текущий проект' : ''
    ].filter(Boolean).join(' · ');
    label.append(title, subtitle);
    const actions = document.createElement('div'); actions.className = 'project-actions';
    const open = button('Открыть', 'Открыть проект', () => {
      if (busy || item.id === projectId) return;
      storage.set('refeditor-project', item.id);
      location.hash = '#' + item.id;
      location.reload();
    }, busy || item.id === projectId);
    open.className = 'button';
    const remove = button('🗑 Удалить', 'Удалить проект безвозвратно', async () => {
      if (busy || item.busy) return;
      if (!window.confirm('Удалить ВЕСЬ проект «' + (item.reference_name || item.id.slice(0, 8)) +
        '» навсегда? Все исходники, референсы и MP4 этого проекта будут удалены с ПК.')) return;
      setBusy(true); message('');
      try {
        await api('/api/projects/' + item.id, {method:'DELETE'});
        if (item.id === projectId) resetWorkspace();
        await loadProjectLibrary();
        message('Проект безвозвратно удалён с ПК.');
      } catch (error) {
        message('Ошибка удаления проекта: ' + error.message);
      } finally {
        setBusy(false);
      }
    }, busy || item.busy);
    remove.className = 'button danger';
    actions.append(open,remove); row.append(label,actions);
    $('project-library').append(row);
  }
}
$('manage-projects').addEventListener('click', async () => {
  if (busy) return;
  $('project-manager').hidden = !$('project-manager').hidden;
  if (!$('project-manager').hidden) {
    try { await loadProjectLibrary(); }
    catch (error) { message('Не удалось загрузить список проектов: ' + error.message); }
  }
});
$('close-project-manager').addEventListener('click', () => {
  $('project-manager').hidden = true;
});
function resetWorkspace() {
  const previous = projectId;
  clearTimeout(pollTimer);
  projectId = null; reference = null; music = null; sources = []; library = []; runs = []; selectedRun = null;
  if (previous) storage.remove(`refeditor-draft-${previous}`);
  storage.remove('refeditor-project'); history.replaceState(null, '', location.pathname);
  $('delete-project').hidden = true;
  $('editor-form').reset(); $('preview').pause(); $('preview').removeAttribute('src'); $('preview').load();
  $('preview').hidden = true; $('empty-preview').hidden = false; $('download').hidden = true;
  $('artifact-links').hidden = true; $('warnings').hidden = true;
  $('result-meta').textContent = 'Ожидаем материалы'; $('preview-label').textContent = 'MP4 / H.264';
  renderFiles(); renderVersions(); updateHints(); setBusy(false);
  status('Готов к работе', 0, 'Загрузите референс и хотя бы один исходник.');
}
$('new-project').addEventListener('click', () => {
  if (busy) return;
  resetWorkspace();
  message('Новый проект открыт. Старые файлы не удалены — для их удаления используй кнопку «Удалить проект».');
});
$('delete-project').addEventListener('click', async () => {
  if (busy || !projectId) return;
  if (!window.confirm('БЕЗВОЗВРАТНО удалить весь текущий проект с ПК? Исчезнут референс, исходники, музыка, временные файлы и ВСЕ готовые MP4-рендеры.')) return;
  const deleting = projectId;
  setBusy(true); message('');
  try {
    await api('/api/projects/' + deleting, {method:'DELETE'});
    resetWorkspace();
    message('Проект удалён с ПК вместе со всеми загруженными файлами и рендерами.');
  } catch (error) {
    message('Не удалось удалить проект: ' + error.message);
    setBusy(false);
  }
});
window.addEventListener('beforeunload', event => {
  if (busy && [reference, ...sources, music].some(asset => asset?.file)) {event.preventDefault(); event.returnValue = '';}
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
      projectId = saved; reference = state.reference; music = state.music || null; sources = [...state.sources]; library = state.sources;
      let draft; try { draft = JSON.parse(storage.get(`refeditor-draft-${saved}`)); } catch { draft = null; }
      const options = draft || state.renders.at(-1)?.settings;
      if (options) {
        $('brief').value = options.brief || ''; $('mode').value = options.mode || 'fit';
        $('audio').value = options.audio || 'none'; $('duration').value = options.max_seconds ?? '';
        $('align-audio').checked = options.align_audio || false;
        $('editor-mode').value = options.editor_mode || 'reference';
        $('reel-seconds').value = options.reel_seconds || 60;
        $('ai-semantic').checked = options.ai_semantic || false;
        $('motion-design').checked = options.motion_design || false;
        if (Array.isArray(options.source_ids)) sources = options.source_ids.map(id => state.sources.find(s => s.id === id)).filter(Boolean);
      }
      saveProject(); renderFiles(); updateHints(); updateRunState(state);
    } catch (error) {
      if (error.status === 404) storage.remove('refeditor-project');
      message('Не удалось восстановить проект. Проверьте сервер или начните новый проект.'); setBusy(false);
    }
  } else setBusy(false);
}
// Chrome 142+ asks permission before a remote HTTPS site can contact localhost.
// Trigger the first request from a real click, not on page load.
$('connect-local').addEventListener('click', async () => {
  const button = $('connect-local');
  button.disabled = true;
  try { await init(); }
  finally { button.disabled = false; }
});
$('connection').textContent = 'Нажмите «Подключить ПК»';
setBusy(false);
$('run').disabled = true;
updateHints();
