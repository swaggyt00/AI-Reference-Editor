"""Reference-time timeline and per-source alignment."""
import json
from pathlib import Path
from .analyzer import video_metadata


def build_project(analysis, sources, *, mode='fit', audio='reference', align_audio=True):
    if mode not in ('fit','native'):raise ValueError('mode must be fit or native')
    sources=[str(Path(s).resolve()) for s in sources]
    if not sources:raise ValueError('At least one source is required')
    source_meta=[video_metadata(s) for s in sources]
    fps=analysis['video']['fps'];duration=analysis['video']['duration']
    sync=[]
    if align_audio:
        from .alignment import audio_offset
        for src in sources:
            sync.append(audio_offset(analysis['reference'],src))
    else:
        sync=[None]*len(sources)
    boundaries=[0]+[c['frame'] for c in analysis['hard_cuts']]+[analysis['video']['frames']]
    segments=[];warnings=[]
    n=len(boundaries)-1
    for i in range(n):
        # By default map final shot to last supplied clip; order is user-controlled.
        src_idx=min(len(sources)-1,int(i*len(sources)/n))
        if i==n-1:src_idx=len(sources)-1
        src=source_meta[src_idx]
        start=boundaries[i]/fps;end=boundaries[i+1]/fps
        match=sync[src_idx]
        # Start at the same musical/dialogue moment if audio actually overlaps.
        src_start=max(0.0,start-match['reference_offset_s']) if match else 0.0
        src_start=min(src_start,max(0.0,src['duration']-.1))
        available=src['duration']-src_start
        target=end-start
        if mode=='fit':
            effective_speed=available/target
            if effective_speed < .8:
                warnings.append(f'Segment {i+1}: source {src_idx+1} is only {available:.2f}s for {target:.2f}s; it must slow to {effective_speed:.2f}x. Missing actions cannot be invented.')
        else:
            effective_speed=1.0
            if target>available:
                warnings.append(f'Segment {i+1}: source {src_idx+1} ends {target-available:.2f}s early; native mode holds the final source frame.')
        segments.append({'start_frame':boundaries[i],'end_frame':boundaries[i+1],
                         'source_index':src_idx,'source_start':src_start,
                         'source_end':round(src['duration'],6),'speed_mode':mode,
                         'speed_keyframes':[]})
    return {'project_version':1,'reference':analysis['reference'],
            'source_files':sources,'reference_analysis':analysis,
            'fps':fps,'width':analysis['video']['width'],'height':analysis['video']['height'],
            'duration':duration,'segments':segments,'audio':audio,
            'audio_alignment':sync,
            'effects':[], 'warnings':warnings,
            'notes':['Source-to-shot assignment is chronological, not semantic. Edit segments[].source_index to choose a different clip.',
                     'Add supported effects in effects[] only when verified against reference.']}


def write_project(project,path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(project,ensure_ascii=False,indent=2),encoding='utf-8')
    return path
