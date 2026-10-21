"""Stream frames from the editing plan into an FFmpeg H.264 encoder."""
import json
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np
from .analyzer import video_metadata
from .effects import apply as apply_effects, source_curve


class SourceReader:
    def __init__(self,path):
        self.path=path
        self.cap=cv2.VideoCapture(str(path))
        if not self.cap.isOpened():raise ValueError(f'Cannot open {path}')
        self.meta=video_metadata(path)
        self.last_index=-1;self.last_image=None
    def frame(self,second):
        idx=int(np.clip(round(second*self.meta['fps']),0,self.meta['frames']-1))
        if idx!=self.last_index:
            if idx != self.last_index+1:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES,idx)
            ok,img=self.cap.read()
            if not ok:
                if self.last_image is None:raise RuntimeError(f'Failed to decode {self.path} at {second:.3f}s')
                return self.last_image.copy()
            self.last_image=img;self.last_index=idx
        return self.last_image.copy()
    def close(self):self.cap.release()


def cover(frame,width,height):
    h,w=frame.shape[:2]
    wanted=width/height
    if w/h>wanted:
        nw=int(round(h*wanted));start=(w-nw)//2;frame=frame[:,start:start+nw]
    else:
        nh=int(round(w/wanted));start=(h-nh)//2;frame=frame[start:start+nh,:]
    return cv2.resize(frame,(width,height),interpolation=cv2.INTER_AREA)


def effect_mask(frame,bounds):
    """Black digital foreground/door-closing masks, measured per reference frame."""
    w=frame.shape[1]
    left=int(round(float(bounds[0])*w));right=int(round(float(bounds[1])*w))
    left=max(0,min(w,left));right=max(left,min(w,right))
    if left>0:frame[:,:left,:]=0
    if right<w:frame[:,right:,:]=0
    return frame


def stream_render(project,output,crf=19,preset='fast',max_seconds=None,*,progress=None):
    output=Path(output).expanduser().resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    fps=float(project['fps']);width=int(project['width']);height=int(project['height'])
    frames=min(len(project['reference_analysis']['edge_masks']),int(round(project['duration']*fps)))
    if max_seconds is not None:
        frames=min(frames,int(round(max_seconds*fps)))
    if frames <1:raise ValueError('Nothing to render')
    readers=[SourceReader(p) for p in project['source_files']]
    raw=output.parent/(output.stem+'.silent.tmp.mp4')
    log_path=output.parent/(output.stem+'.ffmpeg.log')
    commands=['ffmpeg','-y','-hide_banner','-loglevel','error',
             '-f','rawvideo','-pix_fmt','bgr24','-s',f'{width}x{height}',
             '-r',str(fps),'-i','pipe:0','-an','-c:v','libx264',
             '-preset',preset,'-crf',str(crf),'-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2','-pix_fmt','yuv420p',
             '-movflags','+faststart',str(raw)]
    pipe=None
    try:
        with log_path.open('wb') as log:
            pipe=subprocess.Popen(commands,stdin=subprocess.PIPE,stderr=log)
            segments=project['segments']
            current_seg=0
            for i in range(frames):
                while current_seg <len(segments)-1 and i>=segments[current_seg]['end_frame']:
                    current_seg+=1
                seg=segments[current_seg]
                t=i/fps
                local_duration=(seg['end_frame']-seg['start_frame'])/fps
                u=float(np.clip((i-seg['start_frame'])/max(1,seg['end_frame']-seg['start_frame']),0,1))
                a=float(seg.get('source_start',0));b=float(seg.get('source_end',readers[seg['source_index']].meta['duration']))
                if seg.get('speed_mode','fit')=='fit':
                    src_t=a+(b-a)*source_curve(u,seg.get('speed_keyframes',[]))
                else:
                    src_t=a+(i-seg['start_frame'])/fps
                frame=readers[seg['source_index']].frame(src_t)
                frame=cover(frame,width,height)
                frame=apply_effects(frame,t,project.get('effects',[]),i)
                bounds=project['reference_analysis']['edge_masks'][i]
                frame=effect_mask(frame,bounds)
                try:pipe.stdin.write(frame.tobytes())
                except BrokenPipeError:
                    break
                if progress and (i == 0 or (i+1) % max(1, round(fps)) == 0 or i+1 == frames):
                    progress(i+1, frames)
            pipe.stdin.close()
            code=pipe.wait()
        if code:
            raise RuntimeError('FFmpeg encoder failed: '+log_path.read_text(encoding='utf-8',errors='replace')[-4000:])
        audio_choice=project.get('audio','reference')
        src_audio=project['reference'] if audio_choice=='reference' else None
        if audio_choice=='none':src_audio=None
        if audio_choice=='source':src_audio=project['source_files'][0]
        if src_audio:
            cmd=['ffmpeg','-y','-hide_banner','-loglevel','error', '-i',str(raw),
                 '-i',str(src_audio),'-map','0:v:0','-map','1:a:0?',
                 '-c:v','copy','-c:a','aac','-b:a','192k',
                 '-t',f'{frames/fps:.6f}','-movflags','+faststart',str(output)]
            result=subprocess.run(cmd,capture_output=True,text=True)
            if result.returncode:
                raise RuntimeError('FFmpeg audio mux failed: '+result.stderr[-2000:])
        else:
            raw.replace(output)
    finally:
        for reader in readers:reader.close()
        if pipe is not None and pipe.poll() is None:
            pipe.kill()
            pipe.wait()
        if raw.exists() and raw != output:raw.unlink()
    return str(output)
