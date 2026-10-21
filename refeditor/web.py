"""Local browser API. Run with `python -m refeditor web` (one worker only)."""
from contextlib import asynccontextmanager
import json
from pathlib import Path
import shutil
import subprocess
from typing import Literal
from urllib.parse import urlsplit
from uuid import uuid4

import cv2
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from .analyzer import video_metadata
from .web_jobs import FILES, ProjectStore

STATIC = Path(__file__).parent / 'static'


class RenderSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    brief: str = Field(default='', max_length=10000)
    mode: Literal['fit', 'native'] = 'fit'
    audio: Literal['none', 'reference', 'source'] = 'none'
    align_audio: bool = False
    max_seconds: float | None = Field(default=None, ge=.1, le=3600)
    source_ids: list[str] | None = Field(default=None, max_length=32)


def validate_video(path):
    # Reject playlists/network protocols before asking OpenCV to open user bytes.
    result = subprocess.run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe',
                             '-show_format', '-show_streams', '-of', 'json', str(path)],
                            capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError('Не удалось прочитать видео. Проверьте формат и целостность файла.')
    probe = json.loads(result.stdout)
    formats = set(probe.get('format', {}).get('format_name', '').split(','))
    containers = {'mov', 'mp4', 'matroska', 'webm', 'avi', 'mpeg', 'mpegts', 'ogg', 'asf', 'flv', 'mxf', 'nut'}
    if not formats & containers or not any(s.get('codec_type') == 'video' for s in probe.get('streams', [])):
        raise ValueError('Нужен видеофайл, а не аудио, изображение или плейлист.')
    meta = video_metadata(path)
    if meta['duration'] > 3600 or meta['width'] * meta['height'] > 4096 * 2160 or meta['fps'] > 120:
        raise ValueError('Лимиты этой версии: 60 минут, 4096×2160 пикселей, 120 кадров/с.')
    cap = cv2.VideoCapture(str(path))
    try:
        ok, _ = cap.read()
        if not ok:
            raise ValueError('Видеопоток не декодируется установленным OpenCV.')
    finally:
        cap.release()
    return meta


def create_app(storage_dir='output/web', *, max_upload_bytes=2 * 1024**3, max_project_bytes=10 * 1024**3):
    store = ProjectStore(storage_dir)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await run_in_threadpool(store.close)

    app = FastAPI(title='AI Reference Editor', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store

    @app.middleware('http')
    async def local_api_guard(request, call_next):
        if request.url.path.startswith('/api/') and request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('origin')
            if (request.headers.get('x-refeditor-client') != 'web'
                or request.headers.get('sec-fetch-site') == 'cross-site'
                or (origin and urlsplit(origin).netloc != request.headers.get('host'))):
                return JSONResponse({'detail': 'Разрешены только запросы из интерфейса этого сервера.'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(KeyError)
    async def not_found(request, error):
        return JSONResponse({'detail': 'Проект или файл не найден.'}, status_code=404)

    @app.get('/api/health')
    def health():
        ready = all(shutil.which(p) for p in ('ffmpeg', 'ffprobe'))
        return JSONResponse({'ready': ready, 'max_upload_bytes': max_upload_bytes,
                             'max_project_bytes': max_project_bytes, 'max_sources': 32},
                            status_code=200 if ready else 503)

    @app.post('/api/projects', status_code=201)
    def new_project():
        return store.create()

    @app.get('/api/projects/{pid}')
    def get_project(pid: str):
        return store.get(pid)

    @app.post('/api/projects/{pid}/media', status_code=201)
    async def upload(pid: str, request: Request, role: Literal['reference', 'source'],
                     name: str = Query(min_length=1, max_length=255),
                     upload_id: str | None = Query(default=None, pattern=r'^[a-f0-9]{32}$')):
        safe_name = name.replace('\\', '/').rsplit('/', 1)[-1]
        safe_name = ''.join(c for c in safe_name if c.isprintable()).strip() or 'video'
        try:
            declared = int(request.headers.get('content-length', '0'))
        except ValueError:
            raise HTTPException(400, 'Некорректный размер загрузки.')
        with store.lock:
            directory = store.directory(pid)
            state = store.projects[pid]
            if upload_id:
                candidates = ([state['reference']] if state['reference'] else []) + state['sources']
                previous = next((s for s in candidates if s['id'] == upload_id), None)
                if previous:
                    if ((previous == state['reference']) != (role == 'reference')
                        or previous['name'] != safe_name or declared not in (0, previous['size'])):
                        raise HTTPException(409, 'Идентификатор загрузки уже используется другим файлом.')
                    return previous
            if store.busy(pid) or pid in store.uploading:
                raise HTTPException(409, 'Дождитесь завершения текущей операции.')
            if role == 'reference' and state['reference']:
                raise HTTPException(409, 'Для другого референса создайте новый проект.')
            if len(state['sources']) >= 32 and role == 'source':
                raise HTTPException(400, 'Максимум 32 исходника в проекте.')
            used = sum(s['size'] for s in state['sources']) + (state['reference'] or {}).get('size', 0)
            limit = min(max_upload_bytes, max_project_bytes - used)
            if declared > limit:
                raise HTTPException(413, 'Файл превышает лимит загрузки или свободный лимит проекта.')
            store.uploading.add(pid)
        asset_id = upload_id or uuid4().hex
        media = directory / 'media'
        media.mkdir(exist_ok=True)
        part = media / (asset_id + '.part')
        final = media / (asset_id + '.media')
        try:
            size = 0
            with part.open('wb') as handle:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(413, 'Файл превышает лимит загрузки или проекта.')
                    await run_in_threadpool(handle.write, chunk)
            try:
                metadata = await run_in_threadpool(validate_video, part)
            except (ValueError, RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
                raise HTTPException(422, 'Файл не является поддерживаемым видео. ' +
                                    (str(exc) if isinstance(exc, ValueError) else 'Проверьте формат и целостность файла.')) from exc
            asset = {'id': asset_id, 'name': safe_name, 'size': size, 'metadata': metadata}
            with store.lock:
                part.replace(final)
                if role == 'reference':
                    state['reference'] = asset
                else:
                    state['sources'].append(asset)
                store.save(state)
            return asset
        finally:
            part.unlink(missing_ok=True)
            with store.lock:
                store.uploading.discard(pid)

    @app.post('/api/projects/{pid}/renders', status_code=202)
    def render(pid: str, settings: RenderSettings):
        try:
            return store.start(pid, settings.model_dump())
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get('/api/projects/{pid}/renders/{rid}/files/{filename}')
    def artifact(pid: str, rid: str, filename: str, download: bool = False):
        state = store.get(pid)
        run = next((r for r in state['renders'] if r['id'] == rid), None)
        if filename not in FILES or not run or run['status'] != 'completed':
            raise HTTPException(404, 'Готовый файл не найден.')
        path = store.directory(pid) / 'renders' / rid / filename
        if not path.is_file():
            raise HTTPException(404, 'Файл не найден на диске.')
        return FileResponse(path, filename=f'reference-edit-v{run["version"]}.mp4' if download and filename == 'final.mp4' else None)

    @app.get('/')
    def index():
        return FileResponse(STATIC / 'index.html')

    app.mount('/static', StaticFiles(directory=STATIC), name='static')
    return app
