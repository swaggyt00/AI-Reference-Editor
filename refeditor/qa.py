"""Technical render checks and visual comparison. Quality is not judged artistically."""
import json
from pathlib import Path
import subprocess
import cv2
import numpy as np
from .analyzer import analyze_video, video_metadata


def _probe(path):
    command=['ffprobe','-v','error','-show_entries','stream=codec_type,codec_name,width,height,r_frame_rate',
             '-show_entries','format=duration','-of','json',str(path)]
    r=subprocess.run(command,capture_output=True,text=True,check=True)
    return json.loads(r.stdout)


def qa_report(project,output,analysis_output=None):
    output=Path(output)
    outmeta=video_metadata(output)
    probe=_probe(output)
    target=min(project['duration'],outmeta['duration'])
    warnings=list(project.get('warnings',[]))
    if outmeta['duration']+.08 < target:warnings.append('Rendered duration shorter than planned')
    has_audio=any(s['codec_type']=='audio' for s in probe['streams'])
    if project.get('audio') not in (None,'none') and not has_audio:
        warnings.append('No audio track found in output')
    report={'file':str(output),'file_size_mb':round(output.stat().st_size/1e6,2),
            'duration_s':round(outmeta['duration'],3),'fps':outmeta['fps'],
            'resolution':f"{outmeta['width']}x{outmeta['height']}",
            'audio_present':has_audio,'reference_cuts_s':[c['time'] for c in project['reference_analysis']['hard_cuts']],
            'checks':{},'warnings':warnings}
    if abs(outmeta['fps']-project['fps'])>.05:
        warnings.append('Unexpected output frame rate')
    # Spatial mask fidelity at 4 fps; black borders should match even with entirely different footage.
    cap=cv2.VideoCapture(str(output));samp=[]
    ratio=float(project['fps'])/max(1,outmeta['fps'])
    target_masks=project['reference_analysis']['edge_masks']
    # Read sequentially: seeking on each 4-fps sample repeatedly redecodes H264 GOPs.
    sample_stride=max(1,int(round(outmeta['fps']/4)))
    for fi in range(min(outmeta['frames'],len(target_masks))):
        ok,fr=cap.read()
        if not ok:break
        if fi % sample_stride:continue
        from .analyzer import black_edge_bounds
        predicted=black_edge_bounds(fr)
        ref_idx=min(len(target_masks)-1,round(fi*ratio))
        expected=target_masks[ref_idx]
        # Avoid naturally dark footage false errors where ref has no mask.
        if expected[0]>.02 or expected[1]<.98:
            samp.append(abs(predicted[0]-expected[0])+abs(predicted[1]-expected[1]))
    cap.release()
    if samp:
        report['checks']['masked_edge_mean_absolute_error_fraction']=round(float(np.mean(samp)/2),4)
    report['checks']['decode_ok']=outmeta['frames']>1
    report['checks']['has_video']=any(s['codec_type']=='video' for s in probe['streams'])
    if analysis_output:
        analysis_output=Path(analysis_output);analysis_output.parent.mkdir(parents=True,exist_ok=True)
        analysis_output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    return report


def contact_sheet(reference,rendered,output,at=None):
    """Reference/output comparison contact sheet at selected timestamps."""
    if at is None:
        d=min(video_metadata(reference)['duration'],video_metadata(rendered)['duration'])
        at=np.linspace(0,max(0,d-.3),min(9,max(2,int(d//1.5)))).tolist()
    cols=[]
    for p in (reference,rendered):
        cap=cv2.VideoCapture(str(p));frames=[]
        for t in at:
            cap.set(cv2.CAP_PROP_POS_MSEC, float(t)*1000)
            ok,fr=cap.read()
            if not ok:fr=np.zeros((180,240,3),dtype=np.uint8)
            # fit no crop: display aspect-aware, close to 4:3 for sample dataset
            fr=cv2.resize(fr,(240,180),interpolation=cv2.INTER_AREA)
            cv2.rectangle(fr,(0,151),(240,180),(16,16,16),-1)
            cv2.putText(fr,f'{t:.2f}s',(9,172),cv2.FONT_HERSHEY_SIMPLEX,.48,(255,255,255),1,cv2.LINE_AA)
            frames.append(fr)
        cols.append(np.concatenate(frames,axis=1))
        cap.release()
    canvas=np.concatenate(cols,axis=0)
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    cv2.imwrite(str(output),canvas,[cv2.IMWRITE_JPEG_QUALITY,88])
    return str(output)
