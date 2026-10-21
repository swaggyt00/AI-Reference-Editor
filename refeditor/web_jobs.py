"""Durable local projects and a single background render worker.

Use one server process per storage directory. Media never enters source control.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import logging
from pathlib import Path
import re
from threading import RLock
from uuid import uuid4

from .analyzer import analyze_video
from .project import build_project, write_project
from .qa import contact_sheet, qa_report
from .renderer import stream_render

LOG = logging.getLogger(__name__)
ACTIVE = {'queued', 'running'}
FILES = {'final.mp4', 'project.json', 'qa_report.json', 'comparison.jpg'}
BRIEF_WARNING = ('Свободный текст сохранён как задание для редактора, но автоматически не исполнен. '
                 'Применяются только отдельные строки «звук: нет/референс/исходник», '
                 '«режим: fit/native», «длительность: число секунд».')


def resolve_settings(settings):
    """Deliberately small explicit grammar, never pretend to understand free prose."""
    result = dict(settings)
    warnings = []
    for line in result['brief'].splitlines():
        line = line.strip()
        if not line:
            continue
        key, sep, value = line.partition(':')
        key, value = key.strip().lower(), value.strip().lower()
        if sep and key in ('звук', 'режим', 'длительность'):
            if key == 'звук':
                options = {'нет': 'none', 'референс': 'reference', 'исходник': 'source'}
                if value not in options:
                    raise ValueError('Звук: укажите нет, референс или исходник.')
                result['audio'] = options[value]
            elif key == 'режим':
                if value not in ('fit', 'native'):
                    raise ValueError('Режим: укажите fit или native.')
                result['mode'] = value
            else:
                if not re.fullmatch(r'\d+(?:[.,]\d+)?(?:\s*(?:с|сек|секунд|s))?', value):
                    raise ValueError('Длительность: укажите положительное число секунд.')
                duration = float(re.match(r'\d+(?:[.,]\d+)?', value)[0].replace(',', '.'))
                if not .1 <= duration <= 3600:
                    raise ValueError('Длительность должна быть от 0,1 до 3600 секунд.')
                result['max_seconds'] = duration
        elif BRIEF_WARNING not in warnings:
            warnings.append(BRIEF_WARNING)
    return result, warnings


class ProjectStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.projects = {}
        self.uploading = set()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='refeditor')
        for path in self.root.glob('*/state.json'):
            try:
                state = json.loads(path.read_text(encoding='utf-8'))
                if state['id'] != path.parent.name or not re.fullmatch(r'[a-f0-9]{32}', state['id']):
                    continue
                state.setdefault('music', None)
                self.projects[state['id']] = state
                changed = False
                for run in state['renders']:
                    if run['status'] in ACTIVE:
                        run.update(status='failed', stage='Обработка прервана',
                                   error='Сервер перезапущен. Запустите повторный рендер.')
                        changed = True
                if changed:
                    self.save(state)
                for part in path.parent.glob('media/*.part'):
                    part.unlink(missing_ok=True)
            except (ValueError, KeyError, OSError):
                LOG.exception('Cannot recover project %s', path.parent.name)

    def close(self):
        self.executor.shutdown(wait=True)

    def directory(self, pid):
        if not re.fullmatch(r'[a-f0-9]{32}', pid) or pid not in self.projects:
            raise KeyError(pid)
        return self.root / pid

    def save(self, state):
        directory = self.root / state['id']
        directory.mkdir(parents=True, exist_ok=True)
        temp = directory / 'state.tmp'
        temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(directory / 'state.json')

    def create(self):
        with self.lock:
            state = {'id': uuid4().hex, 'reference': None, 'music': None, 'sources': [], 'renders': []}
            self.projects[state['id']] = state
            self.save(state)
            return deepcopy(state)

    def get(self, pid):
        with self.lock:
            self.directory(pid)
            return deepcopy(self.projects[pid])

    def media_path(self, pid, asset):
        return self.directory(pid) / 'media' / (asset['id'] + '.media')

    def busy(self, pid):
        return any(r['status'] in ACTIVE for r in self.projects[pid]['renders'])

    def start(self, pid, settings):
        with self.lock:
            self.directory(pid)
            state = self.projects[pid]
            if self.busy(pid) or pid in self.uploading:
                raise ValueError('Дождитесь завершения текущей загрузки или рендера.')
            editor_mode = settings.get('editor_mode', 'reference')
            if editor_mode == 'reference' and (not state['reference'] or not state['sources']):
                raise ValueError('Загрузите референс и хотя бы один исходник.')
            if editor_mode == 'smart_reels':
                if not state['sources']:
                    raise ValueError('Загрузите длинный исходный ролик.')
                if not settings.get('ai_semantic'):
                    raise ValueError('Smart Reels требует включить и подтвердить Gemini AI-анализ.')
            settings, warnings = resolve_settings(settings)
            if settings.get('motion_design') and (
                settings.get('editor_mode') != 'reference' or not settings.get('ai_semantic')
            ):
                raise ValueError('Motion Design требует Reference Clone и включённого Gemini AI.')
            ids = settings.get('source_ids')
            assets = {s['id']: s for s in state['sources']}
            if ids is None:
                ids = list(assets)
            if not ids or len(ids) != len(set(ids)) or any(i not in assets for i in ids):
                raise ValueError('Выберите загруженные исходники без повторений.')
            settings['source_ids'] = ids
            if editor_mode == 'smart_reels':
                if len(ids) != 1:
                    raise ValueError('Smart Reels пока принимает один длинный исходник.')
                duration = assets[ids[0]]['metadata']['duration']
                if duration < 15 or duration > 1800:
                    raise ValueError('Smart Reels принимает видео длительностью от 15 секунд до 30 минут.')
            if settings.get('ai_semantic') and editor_mode == 'reference':
                if len(ids) > 3:
                    raise ValueError('Первый AI-режим поддерживает до 3 исходников за один запуск.')
                selected = [state['reference'], *(assets[i] for i in ids)]
                max_clip = 120 if settings.get('motion_design') else 60
                if any(asset['metadata']['duration'] > max_clip for asset in selected):
                    raise ValueError('AI-режим принимает видео до ' + str(max_clip) + ' секунд каждое.')
            rid = uuid4().hex
            prefix = f'/api/projects/{pid}/renders/{rid}/files/'
            run = {'id': rid, 'version': len(state['renders']) + 1, 'status': 'queued',
                   'stage': 'В очереди', 'progress': 0, 'settings': settings,
                   'warnings': warnings, 'error': None,
                   'video_url': prefix + 'final.mp4', 'download_url': prefix + 'final.mp4?download=1',
                   'project_url': prefix + 'project.json', 'qa_url': prefix + 'qa_report.json',
                   'comparison_url': prefix + 'comparison.jpg'}
            state['renders'].append(run)
            self.save(state)
            self.executor.submit(self.process, pid, rid, deepcopy(state['reference']),
                                 [deepcopy(assets[i]) for i in ids], deepcopy(settings),
                                 deepcopy(state.get('music')))
            return deepcopy(run)

    def update(self, pid, rid, **values):
        with self.lock:
            state = self.projects[pid]
            run = next(r for r in state['renders'] if r['id'] == rid)
            if all(run.get(k) == v for k, v in values.items()):
                return
            run.update(values)
            self.save(state)

    def process_reels(self, pid, rid, sources, settings, music=None):
        """One local video, AI-planned highlights; no external footage rendering."""
        from .smart_reels import propose_highlights, render_reels, ffprobe_media
        from .qa import contact_sheet
        from .ai_gemini import safe_error_reason
        src = self.media_path(pid, sources[0])
        audio = self.media_path(pid, music) if music else None
        folder = self.directory(pid) / 'renders' / rid
        folder.mkdir(parents=True, exist_ok=True)
        try:
            self.update(pid, rid, status='running', stage='Gemini: анализ длинного видео', progress=3)
            proposal = propose_highlights(
                src, settings.get('reel_seconds', 60), settings.get('brief', '')
            )
            proposal['brief'] = settings.get('brief', '')
            proposal['music'] = music['name'] if music else None
            write_project(proposal, folder / 'project.json')
            self.update(pid, rid, stage='Монтаж лучших моментов', progress=42)
            video = render_reels(
                proposal, folder / 'final.mp4', music=audio,
                progress=lambda progress, stage: self.update(
                    pid, rid, progress=progress, stage=stage)
            )
            self.update(pid, rid, stage='Проверка экспорта', progress=93)
            meta = ffprobe_media(video)
            report = {
                'resolution': '720x1280', 'duration_s': round(meta['duration'], 2),
                'audio_present': meta['audio'], 'highlights': len(proposal['clips']),
                'model': proposal['model'],
                'warnings': list(proposal.get('warnings', [])) + [
                    'Gemini highlights are approximate; manually review dialogue cuts and meaning.',
                    'Vertical framing is center crop; person tracking is not implemented.'
                ]
            }
            (folder / 'qa_report.json').write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8'
            )
            contact_sheet(src, video, folder / 'comparison.jpg')
            self.update(pid, rid, status='completed', stage='Готово', progress=100,
                        warnings=report['warnings'])
        except Exception as exc:
            LOG.exception('Smart Reels render failed: %s/%s', pid, rid)
            reason = str(exc) if isinstance(exc, ValueError) else safe_error_reason(exc)
            self.update(pid, rid, status='failed', stage='Ошибка Smart Reels',
                        error='Smart Reels: ' + reason)

    def process(self, pid, rid, reference, sources, settings, music=None):
        directory = self.directory(pid)
        out = directory / 'renders' / rid
        out.mkdir(parents=True, exist_ok=True)
        try:
            if settings.get('editor_mode') == 'smart_reels':
                return self.process_reels(pid, rid, sources, settings, music)
            self.update(pid, rid, status='running', stage='Анализ референса', progress=1)
            cache = directory / ('analysis-' + reference['id'] + '.json')
            try:
                analysis = json.loads(cache.read_text(encoding='utf-8'))
            except (FileNotFoundError, json.JSONDecodeError):
                analysis = analyze_video(self.media_path(pid, reference),
                    progress=lambda done, total: self.update(pid, rid, progress=1 + int(29 * done / total)))
                cache_temp = cache.with_suffix('.tmp')
                write_project(analysis, cache_temp)
                cache_temp.replace(cache)
            self.update(pid, rid, stage='Сборка монтажного плана', progress=32)
            project = build_project(analysis, [self.media_path(pid, s) for s in sources],
                                    mode=settings['mode'], audio=settings['audio'],
                                    align_audio=settings['align_audio'])
            project['brief'] = settings['brief']
            project['motion_design'] = settings.get('motion_design', False)
            project['web_settings'] = settings
            if settings.get('ai_semantic'):
                from .ai_director import run_ai_scene_matching
                from .ai_gemini import DEFAULT_MODEL
                run_ai_scene_matching(
                    project, self.media_path(pid, reference),
                    [self.media_path(pid, asset) for asset in sources],
                    directory / 'ai-cache',
                    graphics_dir=out / 'graphic-assets' if settings.get('motion_design') else None,
                    model=DEFAULT_MODEL,
                    progress=lambda stage, p: self.update(pid, rid, stage=stage, progress=p)
                )
            # Duration is an explicit end trim, not a fabricated new pacing model.
            if settings['max_seconds'] is not None:
                frame_count = max(1, min(len(analysis['edge_masks']), round(settings['max_seconds'] * project['fps'])))
                project['duration'] = frame_count / project['fps']
            used = {s['source_index'] for s in project['segments'] if s['start_frame'] < round(project['duration'] * project['fps'])}
            if len(used) < len(sources):
                project['warnings'].append(f'В этом монтаже использовано {len(used)} из {len(sources)} исходников. '
                    'Число сцен определяется референсом; часть исходников может остаться неиспользованной.')
            with self.lock:
                run = next(r for r in self.projects[pid]['renders'] if r['id'] == rid)
                project['warnings'] += list(run['warnings'])
            write_project(project, out / 'project.json')
            self.update(pid, rid, stage='Рендер видео', progress=38, warnings=project['warnings'])
            mp4 = stream_render(project, out / 'final.mp4',
                progress=lambda done, total: self.update(pid, rid, progress=38 + int(46 * done / total)))
            if settings.get('motion_design'):
                overlay = project.get('motion_layers', [])
                if overlay:
                    from .motion import render_motion
                    self.update(pid, rid, stage='Remotion: многослойный монтаж', progress=86)
                    motion_output = out / 'with-motion.mp4'
                    render_motion(mp4, overlay, motion_output,
                        asset_files={
                            **{'source_' + str(i): path
                               for i, path in enumerate(project['source_files'])},
                            **project.get('generated_graphic_assets', {})
                        },
                        duration=project['duration'], fps=round(project['fps']),
                        width=project['width'], height=project['height'])
                    import os
                    os.replace(motion_output, mp4)
                else:
                    project['warnings'].append(
                        'Motion Design: уверенные слои отсутствуют, исходный монтаж сохранён.'
                    )
            write_project(project, out / 'project.json')
            self.update(pid, rid, stage='Проверка видео и аудио', progress=91)
            qa = qa_report(project, mp4, out / 'qa_report.json')
            self.update(pid, rid, stage='Создание сравнения', progress=96)
            contact_sheet(project['reference'], mp4, out / 'comparison.jpg')
            self.update(pid, rid, status='completed', stage='Готово', progress=100, warnings=qa['warnings'])
        except Exception as exc:
            LOG.exception('Render failed: %s/%s', pid, rid)
            if settings.get('motion_design') and (
                str(exc).startswith('Remotion not installed.') or
                str(exc).startswith('Remotion failed:')
            ):
                error = 'Motion Design: ' + str(exc)[:450] + ' Обычный режим доступен без этой опции.'
            elif settings.get('ai_semantic'):
                from .ai_gemini import safe_error_reason
                reason = str(exc) if isinstance(exc, ValueError) and str(exc).startswith('AI pilot') else safe_error_reason(exc)
                error = 'AI-анализ не выполнен: ' + reason + ' Обычный монтаж доступен без AI-режима.'
            else:
                error = 'Ошибка чтения или обработки видео. Проверьте файлы и повторите рендер. Подробности в журнале сервера.'
            self.update(pid, rid, status='failed', stage='Не удалось завершить рендер',
                        error=error)
