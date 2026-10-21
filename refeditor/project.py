"""Reference-time timeline, with reliable audio-overlap matching when available."""
import json
from pathlib import Path
from .analyzer import video_metadata


def assign_source_to_scene(start, end, source_meta, audio_matches, fallback):
    """Choose source sharing the strongest time-aligned audio with this shot.

    Fall back to the user's source order rather than speculating when no
    high-confidence shared audio has been established.
    """
    scores = []
    for idx, (meta, match) in enumerate(zip(source_meta, audio_matches)):
        if not match or float(match.get('score', 0)) < .43:
            continue
        offset = float(match['reference_offset_s'])
        overlap = max(0., min(end, offset + meta['duration']) - max(start, offset))
        coverage = overlap / max(1e-5, end - start)
        if coverage < .12:
            continue
        scores.append((coverage * float(match['score']), idx, coverage, offset))
    scores.sort(reverse=True)
    if scores and scores[0][0] >= .12 and (
            len(scores) == 1 or scores[0][0] - scores[1][0] >= .07):
        score, idx, coverage, offset = scores[0]
        return idx, (f'shared audio @ reference {offset:.3f}s '
                     f'(coverage {coverage:.0%}; confidence {score:.2f})')
    return fallback, 'user source order (no unambiguous shared audio match)'


def build_project(analysis, sources, *, mode='fit', audio='reference', align_audio=True):
    if mode not in ('fit', 'native'):
        raise ValueError('mode must be fit or native')
    sources = [str(Path(s).resolve()) for s in sources]
    if not sources:
        raise ValueError('At least one source is required')
    source_meta = [video_metadata(s) for s in sources]
    fps = analysis['video']['fps']
    duration = analysis['video']['duration']
    if align_audio:
        from .alignment import audio_offset
        sync = [audio_offset(analysis['reference'], src) for src in sources]
    else:
        sync = [None] * len(sources)
    boundaries = [0] + [c['frame'] for c in analysis['hard_cuts']] + [analysis['video']['frames']]
    segments = []
    warnings = []
    for i in range(len(boundaries) - 1):
        start, end = boundaries[i] / fps, boundaries[i+1] / fps
        # The final source is NOT forcibly selected for the final reference shot.
        fallback = min(i, len(sources) - 1)
        src_idx, reason = assign_source_to_scene(start, end, source_meta, sync, fallback)
        src = source_meta[src_idx]
        match = sync[src_idx]
        src_start = max(0., start - match['reference_offset_s']) if (
            match and reason.startswith('shared audio')) else 0.
        src_start = min(src_start, max(0., src['duration'] - .1))
        available = src['duration'] - src_start
        target = end - start
        if mode == 'fit' and available / max(.001, target) < .8:
            warnings.append(
                f'Segment {i+1}: source {src_idx+1} is only {available:.2f}s '
                f'for {target:.2f}s; it must slow to {available/target:.2f}x. '
                'Missing actions cannot be invented.')
        if mode == 'native' and target > available:
            warnings.append(
                f'Segment {i+1}: source {src_idx+1} ends {target-available:.2f}s early; '
                'native mode holds the final source frame.')
        segments.append({
            'start_frame': boundaries[i], 'end_frame': boundaries[i+1],
            'source_index': src_idx, 'source_selection': reason,
            'source_start': src_start, 'source_end': round(src['duration'], 6),
            'speed_mode': mode, 'speed_keyframes': []
        })
    if not any(s['source_selection'].startswith('shared audio') for s in segments):
        warnings.append('No confidently shared audio found: scenes use input order, '
                        'NOT semantic video matching. Verify source order before rendering.')
    return {
        'project_version': 1, 'reference': analysis['reference'], 'source_files': sources,
        'reference_analysis': analysis, 'fps': fps, 'width': analysis['video']['width'],
        'height': analysis['video']['height'], 'duration': duration,
        'segments': segments, 'audio': audio, 'audio_alignment': sync,
        'effects': [], 'warnings': warnings,
        'notes': ['Audio-aligned selection needs actual overlapping soundtracks.',
                  'Semantic shot matching and complex VFX replication remain unimplemented.']
    }


def write_project(project, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding='utf-8')
    return path
