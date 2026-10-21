"""Validated motion-layer plan and opt-in Remotion rendering (Windows or Linux).

No arbitrary JSX, filters, CSS or file paths from Gemini are ever executed.
All layers are data, validated and rendered by checked-in React components.
"""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid

KINDS = {'title','caption','card','badge','route','image'}
ANIMATIONS = {'rise','slide','pop','fade'}
MAX_LAYERS = 50
MAX_DURATION = 300


def validate_motion_layers(layers, duration, available_assets=None):
    if not isinstance(layers, list) or len(layers) > MAX_LAYERS:
        raise ValueError('Motion layer plan must contain 0–50 layers.')
    if not 0 < float(duration) <= MAX_DURATION:
        raise ValueError('Motion compositor supports durations up to 300 seconds.')
    available_assets = set(available_assets or [])
    accepted = []
    for item in layers:
        if not isinstance(item, dict) or item.get('kind') not in KINDS:
            continue
        try:
            start, end = float(item['start']), float(item['end'])
            confidence = float(item.get('confidence', 1.))
            x, y = float(item.get('x', .5)), float(item.get('y', .5))
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
        if not all(math.isfinite(v) for v in (start,end,confidence,x,y)):
            continue
        if not (0 <= start < end <= duration+.04 and .72 <= confidence <= 1):
            continue
        if end - start < .15 or not (0 <= x <= 1 and 0 <= y <= 1):
            continue
        kind = item['kind']
        out = {'kind': kind, 'start': round(start,3),
               'end':round(min(end,duration),3), 'x':x, 'y':y,
               'animation': item.get('animation') if item.get('animation') in ANIMATIONS else 'fade'}
        if kind == 'image':
            asset = item.get('asset')
            if not isinstance(asset,str) or asset not in available_assets:
                continue
            out['asset'] = asset
            out['width'] = max(.15, min(.95, float(item.get('width',.65))))
        else:
            text = item.get('text')
            if not isinstance(text,str) or not text.strip() or len(text) > 180:
                continue
            out['text'] = text
            out['size'] = max(16,min(110,float(item.get('size',50))))
            if kind == 'route':
                pts = item.get('points')
                if not isinstance(pts,list) or not 2 <= len(pts) <= 12:
                    continue
                good = []
                for p in pts:
                    if not isinstance(p,list) or len(p)!=2:
                        break
                    try: px,py = map(float,p)
                    except (TypeError,ValueError): break
                    if not all(math.isfinite(v) and 0<=v<=1 for v in (px,py)): break
                    good.append([px,py])
                if len(good)!=len(pts): continue
                out['points'] = good
        accepted.append(out)
    return accepted


def motion_engine_status(project_root=None):
    root = Path(project_root or Path(__file__).resolve().parents[1])
    module = root / 'motion' / 'node_modules'
    remotion = module / '.bin' / ('remotion.cmd' if os.name=='nt' else 'remotion')
    return {'remotion_ready': remotion.is_file(), 'node': shutil.which('node') is not None}


def render_motion(base_video, layers, output, *, asset_files=None, duration=None,
                  fps=30, width=None, height=None):
    """Render video layers and remux original audio locally. Never call AI."""
    from .analyzer import video_metadata
    base = Path(base_video).resolve()
    meta=video_metadata(base)
    duration=float(duration or meta['duration'])
    width=int(width or meta['width'])
    height=int(height or meta['height'])
    if width*height > 3840*2160 or width<64 or height<64:
        raise ValueError('Unsupported motion output dimensions')
    if not 12<=fps<=60:
        raise ValueError('Motion fps out of range')
    valid = validate_motion_layers(layers,duration,(asset_files or {}).keys())
    if not valid:
        raise ValueError('No validated motion layers to render: no unapproved generic graphics inserted.')
    output=Path(output).resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    root=Path(__file__).resolve().parents[1]/'motion'
    status=motion_engine_status(root.parent)
    if not status['remotion_ready']:
        raise RuntimeError('Remotion not installed. Run setup-motion.cmd once before using Motion Design.')
    program = root/'node_modules'/'.bin'/('remotion.cmd' if os.name=='nt' else 'remotion')
    work=root/'public'/'assets'
    work.mkdir(parents=True,exist_ok=True)
    token=uuid.uuid4().hex
    video_name='base-'+token+'.mp4'
    props_path=output.parent/(token+'-motion-props.json')
    video_output=output.parent/(token+'-silent.mp4')
    created=[work/video_name,props_path,video_output]
    try:
        shutil.copy2(base,work/video_name)
        mapping={}
        for idx,(key,path) in enumerate((asset_files or {}).items()):
            if any(item.get('asset')==key for item in valid):
                path=Path(path).resolve()
                if not path.is_file() or path.suffix.lower() not in ('.png','.jpg','.jpeg','.webp'):
                    raise ValueError('Only real local image assets are supported')
                filename='asset-'+token+'-'+str(idx)+path.suffix.lower()
                dest=work/filename
                shutil.copy2(path,dest);created.append(dest)
                mapping[key]=filename
        for item in valid:
            if item['kind']=='image':item['asset']=mapping[item['asset']]
        props_path.write_text(json.dumps({'baseFile':video_name,'layers':valid}),encoding='utf-8')
        frames=max(1,int(round(duration*fps)))
        cmd=[str(program),'render','src/index.jsx','Motion',str(video_output),
             '--props',str(props_path),'--duration',str(frames),
             '--fps',str(fps),'--width',str(width),'--height',str(height),
             '--concurrency','2','--public-license-key','free-license',
             '--log','error']
        result=subprocess.run(cmd,cwd=root,capture_output=True,text=True,timeout=3600)
        if result.returncode:
            raise RuntimeError('Remotion failed: '+(result.stderr or result.stdout)[-1000:])
        cmd=['ffmpeg','-y','-v','error','-i',str(video_output),
             '-i',str(base),'-map','0:v:0','-map','1:a:0?',
             '-c:v','copy','-c:a','aac','-b:a','192k','-t',str(duration),
             '-movflags','+faststart',str(output)]
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=120)
        if result.returncode:
            raise RuntimeError('Motion audio mux failed: '+result.stderr[-850:])
        return str(output)
    finally:
        for path in created:
            path.unlink(missing_ok=True)
