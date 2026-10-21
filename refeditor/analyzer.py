"""Extract reproducible editing signals from a provided reference video.

High-confidence: hard cuts, edge-black occlusion/masks, narrow flash events.
No claim of generic VFX recognition, semantic shot understanding or 1:1 transfer.
"""
import json
from pathlib import Path
import cv2
import numpy as np
from .transfer_fx import white_edge_bounds


def video_metadata(path):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f'Cannot open video: {path}')
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    if fps < 1 or frames < 1:
        raise ValueError(f'Bad video metadata: {path}')
    return dict(fps=round(fps, 6), frames=frames, duration=frames/fps, width=width, height=height)


def black_edge_bounds(frame, work_width=320, max_pixel=14, min_black_fraction=.975):
    """Normalized horizontal content boundaries; works for true black digital borders.
    A naturally dark scene is not reliably separable from an applied black mask.
    """
    orig_w=frame.shape[1]
    work_h=max(32, round(frame.shape[0]*work_width/orig_w))
    gray=cv2.cvtColor(cv2.resize(frame,(work_width,work_h)),cv2.COLOR_BGR2GRAY)
    is_black=(gray<=max_pixel).mean(axis=0)>=min_black_fraction
    left=0;right=work_width-1
    while left < work_width-1 and is_black[left]: left+=1
    while right>0 and is_black[right]:right-=1
    # avoid false positive from minimal codec padding
    if left<3:left=0
    if right>work_width-4:right=work_width-1
    if right<=left or right-left < 4: return [0.0,1.0]
    return [round(left/work_width,6),round((right+1)/work_width,6)]


def analyze_video(path, out=None, *, progress=None):
    path=Path(path).expanduser().resolve()
    meta=video_metadata(path)
    cap=cv2.VideoCapture(str(path))
    prev_img=None;prev_hist=None
    diffs=[];hist_diffs=[];bounds=[];white_bounds=[];lumas=[]
    frame_idx=0
    while True:
        ok,frame=cap.read()
        if not ok:break
        small=cv2.resize(frame,(120,90),interpolation=cv2.INTER_AREA)
        hsv=cv2.cvtColor(small,cv2.COLOR_BGR2HSV)
        hist=cv2.calcHist([hsv],[0,1],None,[12,8],[0,180,0,256])
        hist=cv2.normalize(hist,hist).ravel()
        gray=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY)
        lumas.append(round(float(np.mean(gray)),2))
        bounds.append(black_edge_bounds(frame))
        white_bounds.append(white_edge_bounds(frame))
        if prev_img is not None:
            diffs.append(float(np.mean(np.abs(small.astype(np.int16)-prev_img.astype(np.int16)))))
            hist_diffs.append(float(cv2.compareHist(hist,prev_hist,cv2.HISTCMP_BHATTACHARYYA)))
        prev_img=small;prev_hist=hist;frame_idx+=1
        if progress and (frame_idx == 1 or frame_idx % max(1, round(meta['fps'])) == 0):
            progress(min(frame_idx, meta['frames']), meta['frames'])
    cap.release()
    if not frame_idx:raise ValueError('No decodable frames')
    if progress:progress(frame_idx, frame_idx)
    meta['frames']=frame_idx;meta['duration']=frame_idx/meta['fps']
    d=np.asarray(diffs,dtype='float64');h=np.asarray(hist_diffs,dtype='float64')
    # Two independent signals avoid classifying large moving objects as scene cuts.
    d_threshold=max(45.0,float(np.percentile(d,99)*1.15)) if len(d) else np.inf
    h_threshold=max(.50,float(np.percentile(h,99)*1.15)) if len(h) else np.inf
    candidate=[(i+1,float(d[i]),float(h[i])) for i in range(len(d))
                if d[i]>=d_threshold and h[i]>=h_threshold]
    cuts=[]
    for idx,pixel_diff,hash_diff in sorted(candidate):
        at=idx/meta['fps']
        if at<.35 or meta['duration']-at<.35:continue  # terminal fade/black
        if cuts and at-cuts[-1]['time']<.35:continue
        cuts.append({'frame':idx,'time':round(at,6),'confidence':'high',
                     'pixel_change':round(pixel_diff,2),'hist_change':round(hash_diff,3)})
    arr=np.asarray(lumas)
    flashes=[]
    # Flash detection is deliberately conservative: brief bright spikes only.
    for i in range(3,len(arr)-3):
        neigh=np.r_[arr[i-3:i-1],arr[i+2:i+4]]
        base=float(np.median(neigh))
        if arr[i]>130 and arr[i]-base>52 and (not flashes or i-flashes[-1]['frame']>3):
            flashes.append({'frame':i,'time':round(i/meta['fps'],6),
                            'strength':round(min(.9,(arr[i]-base)/160),3)})
    result={'format_version':1,'reference':str(path),'video':meta,
            'hard_cuts':cuts,'edge_masks':bounds,'white_edge_masks':white_bounds,'flash_events':flashes,
            'luminance_mean':lumas,
            'analysis_limitations':[
              'Automated visual interpretation currently covers hard cuts, digital black side masks, and brief bright flashes.',
              'Zooms, speed ramps, object tracking, complex transitions and scene matching require review or an editor-defined effect recipe.',
              'Black borders and genuine pitch-black surroundings can sometimes be confused.'
            ]}
    if out:
        out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    return result
