"""Safely extract some simple 2D stickers/icons from a flattened video.

Gemini can only PROPOSE bounded crops. Local CV rejects textured backgrounds,
unseen times, photos or overly uncertain shapes; accepted assets remain on PC.
This does NOT reconstruct arbitrary source layers or hidden imagery.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import cv2
import numpy as np

MAX_GRAPHICS=12
ALLOW_CATEGORIES={'logo','icon','sticker','illustration','pixel_art','graphic_symbol'}

def _finite(value, fallback=None):
    try:
        number=float(value)
        return number if math.isfinite(number) else fallback
    except (TypeError, ValueError, OverflowError):
        return fallback

def _candidate(obj,duration,allowed_times=None):
    if not isinstance(obj,dict) or obj.get('category') not in ALLOW_CATEGORIES:
        return None
    confidence=_finite(obj.get('confidence'))
    start=_finite(obj.get('start'));end=_finite(obj.get('end'))
    at=_finite(obj.get('sample_time_s'))
    box=obj.get('box')
    if (None in (confidence,start,end,at) or not (.84<=confidence<=1.0)
            or not (0<=start<end<=duration+.04) or not (start<=at<=min(end,duration))
            or not isinstance(box,list) or len(box)!=4):
        return None
    if allowed_times is not None and not any(abs(at-t)<.09 for t in allowed_times):
        return None
    x,y,w,h=[_finite(v) for v in box]
    if (None in (x,y,w,h) or not (0<=x<1 and 0<=y<1)
            or not (.03<=w<=.65 and .03<=h<=.65) or w*h>.32
            or x+w>1.001 or y+h>1.001):
        return None
    anim=obj.get('animation','fade')
    return {'confidence':confidence,'category':obj['category'],
            'start':start,'end':min(end,duration),'sample_time_s':at,
            'box':[x,y,w,h],
            'animation':anim if anim in ('fade','rise','slide','pop') else 'fade'}

def extract_alpha_asset(frame,normalized_box,dest):
    """Return PNG metadata when icon has a sufficiently flat border.

    A nonuniform border indicates a photographic background: do NOT copy its
    pixels into an overlay on the user's unrelated footage.
    """
    if frame is None or len(frame.shape)!=3:return None
    H,W=frame.shape[:2]
    x,y,w,h=normalized_box
    x0=max(0,round(x*W));y0=max(0,round(y*H))
    x1=min(W,round((x+w)*W));y1=min(H,round((y+h)*H))
    if x1-x0<24 or y1-y0<24:return None
    crop=frame[y0:y1,x0:x1];ch,cw=crop.shape[:2]
    border=max(2,min(12,int(min(cw,ch)*.10)))
    strips=np.concatenate([
        crop[:border].reshape(-1,3),crop[-border:].reshape(-1,3),
        crop[border:-border,:border].reshape(-1,3),
        crop[border:-border,-border:].reshape(-1,3)
    ]).astype(np.float32)
    bg=np.median(strips,axis=0)
    deviation=np.linalg.norm(strips-bg,axis=1)
    if np.percentile(deviation,90)>22 or np.median(deviation)>10:
        return None
    distance=np.linalg.norm(crop.astype(np.float32)-bg,axis=2)
    foreground=(distance>=32).astype(np.uint8)
    ratio=float(foreground.mean())
    if not(.018<=ratio<=.70):return None
    n,labels,stats,_=cv2.connectedComponentsWithStats(foreground,8)
    areas=sorted((int(stats[k,cv2.CC_STAT_AREA]) for k in range(1,n)),reverse=True)
    if not areas or areas[0]<max(50,int(ch*cw*.008)):
        return None
    alpha=np.clip((distance-15)/28,0,1)
    mask=np.zeros_like(foreground)
    for k in range(1,n):
        if stats[k,cv2.CC_STAT_AREA]>=max(6,int(ch*cw*.0002)):
            mask[labels==k]=1
    alpha=(alpha*mask*255).astype(np.uint8)
    if cv2.countNonZero(alpha)==0:return None
    rgba=cv2.cvtColor(crop,cv2.COLOR_BGR2BGRA);rgba[:,:,3]=alpha
    dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
    if not cv2.imwrite(str(dest),rgba):raise OSError('PNG write failed')
    return {'pixel_width':cw,'pixel_height':ch,'foreground_coverage':round(ratio,4)}



def extract_temporal_asset(frame,background_frame,normalized_box,dest):
    """Recover a sprite over static textured footage from a clean adjacent plate.

    Refuse if pixels outside the sprite candidate show camera or scene motion.
    This conservative path works for some pixel graphics on fixed backgrounds.
    """
    if frame.shape != background_frame.shape or len(frame.shape)!=3:
        return None
    H,W=frame.shape[:2]
    x,y,w,h=normalized_box
    x0=max(0,round(x*W));y0=max(0,round(y*H))
    x1=min(W,round((x+w)*W));y1=min(H,round((y+h)*H))
    if x1-x0<24 or y1-y0<24:return None
    diff=frame.astype(np.int16)-background_frame.astype(np.int16)
    global_diff=np.abs(diff).mean(axis=2)
    outside_mask=np.ones((H,W),dtype=bool)
    outside_mask[y0:y1,x0:x1]=False
    outside=global_diff[outside_mask]
    if not len(outside) or np.median(outside)>8 or np.quantile(outside,.8)>20:
        return None
    delta=np.linalg.norm(diff[y0:y1,x0:x1].astype(np.float32),axis=2)
    fg=(delta>32).astype(np.uint8)
    ratio=float(fg.mean())
    if not .018<=ratio<=.65:return None
    n,labels,stats,_=cv2.connectedComponentsWithStats(fg,8)
    areas=[int(stats[k,cv2.CC_STAT_AREA]) for k in range(1,n)]
    if not areas or max(areas)<max(35,int(fg.size*.006)):return None
    mask=np.zeros_like(fg)
    for k in range(1,n):
        if stats[k,cv2.CC_STAT_AREA]>=max(6,int(fg.size*.0002)):
            mask[labels==k]=1
    alpha=(np.clip((delta-18)/35,0,1)*mask*255).astype(np.uint8)
    if not alpha.any():return None
    rgba=cv2.cvtColor(frame[y0:y1,x0:x1],cv2.COLOR_BGR2BGRA)
    rgba[:,:,3]=alpha
    dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
    if not cv2.imwrite(str(dest),rgba):raise OSError('Cannot write temporal graphic PNG')
    return {'pixel_width':x1-x0,'pixel_height':y1-y0,
            'foreground_coverage':round(ratio,4),'extraction':'temporal_static_plate'}

def extract_reference_graphics(reference_path,raw_candidates,output_dir,*,duration,
                               allowed_sample_times=None):
    if not isinstance(raw_candidates,list):raw_candidates=[]
    accepted=[];layers=[];assets={};rejections=[]
    cap=cv2.VideoCapture(str(reference_path))
    if not cap.isOpened():raise ValueError('Reference graphics cannot be decoded')
    fps=float(cap.get(cv2.CAP_PROP_FPS))
    if fps<1:
        cap.release();raise ValueError('Invalid reference frame rate')
    try:
        for i,raw in enumerate(raw_candidates[:MAX_GRAPHICS]):
            item=_candidate(raw,float(duration),allowed_sample_times)
            if not item:
                rejections.append({'candidate':i,'reason':'invalid type, time, box or confidence'})
                continue
            cap.set(cv2.CAP_PROP_POS_FRAMES,round(item['sample_time_s']*fps))
            ok,frame=cap.read()
            if not ok:
                rejections.append({'candidate':i,'reason':'frame unavailable'})
                continue
            name='ref_graphic_'+str(len(accepted))
            dest=Path(output_dir)/(name+'.png')
            info=extract_alpha_asset(frame,item['box'],dest)
            if not info:
                # Some reference overlays sit on a complex but STILL
                # background: use video frames before/after the graphic as
                # a clean plate, never accept a moving photographic plate.
                positions=[item['start']-.15,item['end']+.15]
                for clean_at in positions:
                    if not(0<=clean_at<duration):
                        continue
                    cap.set(cv2.CAP_PROP_POS_FRAMES,round(clean_at*fps))
                    clean_ok,clean_frame=cap.read()
                    if not clean_ok:
                        continue
                    info=extract_temporal_asset(frame,clean_frame,item['box'],dest)
                    if info:break
            if not info:
                rejections.append({'candidate':i,'reason':'no flat or stable clean background'})
                continue
            x,y,w,h=item['box']
            layer={'kind':'image','asset':name,'start':round(item['start'],3),
                   'end':round(item['end'],3),'confidence':item['confidence'],
                   'x':round(x+w/2,5),'y':round(y+h/2,5),'width':round(w,5),
                   'animation':item['animation']}
            layers.append(layer);assets[name]=str(dest.resolve())
            accepted.append({'name':name,'category':item['category'],
                             'box':item['box'],'sample_time_s':item['sample_time_s'],**info})
    finally:cap.release()
    return {'layers':layers,'assets':assets,'extracted':accepted,'rejected':rejections}

def save_graphic_report(result,path):
    safe={'extracted':result['extracted'],'rejected':result['rejected'],
          'count':len(result['extracted'])}
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(safe,ensure_ascii=False,indent=2),encoding='utf-8')
    return safe
