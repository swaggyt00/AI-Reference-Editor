"""Time-coded storyboard for Gemini's existing opt-in edit-plan request.

Image sheets are computed locally and ONLY sent after explicit user consent.
No additional model request and no server-side GitHub uploads.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
import cv2
import numpy as np

MAX_STILLS=48
TILE_W,TILE_H=400,260
GRID_COLS,GRID_ROWS=4,4

def storyboard_times(duration, cuts=None, *, max_frames=MAX_STILLS):
    if not math.isfinite(float(duration)) or duration <= 0:
        raise ValueError('Invalid reference duration')
    max_frames=max(1,min(MAX_STILLS,int(max_frames)))
    count=min(max_frames,max(8,math.ceil(duration/2)))
    basic=np.linspace(.1,max(.1,duration-.12),count).tolist()
    priority=[]
    for event in cuts if isinstance(cuts,list) else []:
        cut=event.get('time') if isinstance(event,dict) else None
        try: t=float(cut)
        except (TypeError,ValueError):continue
        if not math.isfinite(t):continue
        for offset in (-.15,.15):
            v=t+offset
            if 0<=v<duration:priority.append(v)
    priority=sorted(set(round(v,3) for v in priority))
    if len(priority)>max_frames//2:
        ii=np.linspace(0,len(priority)-1,max_frames//2).astype(int)
        priority=[priority[i] for i in ii]
    remaining=max_frames-len(priority)
    if len(basic)>remaining:
        ii=np.linspace(0,len(basic)-1,remaining).astype(int)
        basic=[basic[i] for i in ii]
    return sorted(set(round(max(0,min(duration-.001,v)),3)
                      for v in priority+basic))[:max_frames]

def generate_storyboards(reference, folder, *, hard_cuts=None, max_frames=MAX_STILLS):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    cap=cv2.VideoCapture(str(reference))
    if not cap.isOpened():raise ValueError('Cannot open reference for storyboard')
    fps=cap.get(cv2.CAP_PROP_FPS);frames=cap.get(cv2.CAP_PROP_FRAME_COUNT)
    if fps<1 or frames<1:
        cap.release();raise ValueError('Bad reference fps or frames')
    duration=frames/fps
    times=storyboard_times(duration,hard_cuts,max_frames=max_frames)
    images=[];records=[]
    try:
        for stamp in times:
            cap.set(cv2.CAP_PROP_POS_FRAMES,int(round(stamp*fps)))
            ok,frame=cap.read()
            if not ok:continue
            h,w=frame.shape[:2];inner_w=TILE_W-12;inner_h=TILE_H-39
            ratio=min(inner_w/w,inner_h/h)
            scaled=cv2.resize(frame,(max(1,round(w*ratio)),max(1,round(h*ratio))),
                              interpolation=cv2.INTER_AREA)
            tile=np.full((TILE_H,TILE_W,3),33,dtype=np.uint8)
            left=(TILE_W-scaled.shape[1])//2
            top=30+(inner_h-scaled.shape[0])//2
            tile[top:top+scaled.shape[0],left:left+scaled.shape[1]]=scaled
            label=f'FRAME {len(images):02d}   {stamp:06.2f}s'
            cv2.putText(tile,label,(11,21),cv2.FONT_HERSHEY_SIMPLEX,
                        .58,(255,255,255),2,cv2.LINE_AA)
            records.append({'tile':len(images),'time_s':stamp})
            images.append(tile)
    finally:cap.release()
    if not images:raise ValueError('No decodable reference frames')
    paths=[]
    for page,offset in enumerate(range(0,len(images),GRID_ROWS*GRID_COLS)):
        sheet=np.full((TILE_H*GRID_ROWS,TILE_W*GRID_COLS,3),33,dtype=np.uint8)
        for j,frame in enumerate(images[offset:offset+GRID_ROWS*GRID_COLS]):
            row,col=divmod(j,GRID_COLS)
            sheet[row*TILE_H:(row+1)*TILE_H,col*TILE_W:(col+1)*TILE_W]=frame
        dest=folder/f'storyboard-{page+1}.jpg'
        if not cv2.imwrite(str(dest),sheet,[cv2.IMWRITE_JPEG_QUALITY,85]):
            raise OSError('Storyboard JPEG could not be saved')
        paths.append(dest)
    record={'duration_s':round(duration,3),'reference_frames':records,
            'storyboard_sheets':[p.name for p in paths],
            'note':'Time-coded still evidence only, not frame-accurate OCR or graphics tracking'}
    (folder/'storyboard-index.json').write_text(
        json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    return paths,record
