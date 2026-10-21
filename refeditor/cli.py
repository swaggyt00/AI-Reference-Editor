"""CLI entrypoint: python -m refeditor [analyze|pipeline|render|doctor]."""
import argparse
import json
import shutil
import sys
from pathlib import Path


def main(argv=None):
    ap=argparse.ArgumentParser(description='Reference-driven automated video editor, MVP')
    commands=ap.add_subparsers(dest='command',required=True)
    a=commands.add_parser('analyze',help='Extract cuts, masks and flash candidates')
    a.add_argument('--reference',required=True);a.add_argument('--output',required=True)
    p=commands.add_parser('pipeline',help='Analyze, build project, render, inspect')
    p.add_argument('--reference',required=True);p.add_argument('--sources',nargs='+',required=True)
    p.add_argument('--output-dir',default='output');p.add_argument('--mode',choices=['fit','native'],default='fit')
    p.add_argument('--max-seconds',type=float,default=None)
    r=commands.add_parser('render',help='Render an already-authored project.json')
    r.add_argument('--project',required=True);r.add_argument('--output',required=True)
    r.add_argument('--max-seconds',type=float,default=None)
    commands.add_parser('doctor',help='Check Python dependencies and FFmpeg')
    args=ap.parse_args(argv)
    if args.command=='doctor':
        print('Python:',sys.version.split()[0])
        import cv2,numpy
        print('OpenCV:',cv2.__version__,'NumPy:',numpy.__version__)
        for name in ['ffmpeg','ffprobe']:
            path=shutil.which(name)
            print(name, ':',path or 'NOT INSTALLED')
        return 0 if all(shutil.which(p) for p in ('ffmpeg','ffprobe')) else 2
    from .analyzer import analyze_video
    if args.command=='analyze':
        res=analyze_video(args.reference,args.output)
        print('Detected cuts:',[x['time'] for x in res['hard_cuts']]);print('Saved:',args.output)
        return 0
    from .project import build_project,write_project
    from .renderer import stream_render
    from .qa import qa_report,contact_sheet
    if args.command=='pipeline':
        out=Path(args.output_dir).resolve();out.mkdir(parents=True,exist_ok=True)
        print('1/4 ANALYZING REFERENCE',flush=True)
        analysis=analyze_video(args.reference,out/'analysis.json')
        print('High-confidence cuts:',[c['time'] for c in analysis['hard_cuts']],flush=True)
        project=build_project(analysis,args.sources,mode=args.mode)
        write_project(project,out/'project.json')
        for warning in project['warnings']:print('WARNING:',warning,flush=True)
        print('2/4 RENDERING',flush=True)
        mp4=stream_render(project,out/'final.mp4',max_seconds=args.max_seconds)
        print('3/4 QC',flush=True)
        report=qa_report(project,mp4,out/'qa_report.json')
        print('4/4 COMPARISON',flush=True)
        sheet=contact_sheet(args.reference,mp4,out/'comparison.jpg')
        print(json.dumps({'video':mp4,'contact_sheet':sheet,'cut_points':report['reference_cuts_s'],
                          'warnings':report['warnings']},ensure_ascii=False,indent=2))
        return 0
    project=json.loads(Path(args.project).read_text(encoding='utf-8'))
    mp4=stream_render(project,args.output,max_seconds=args.max_seconds)
    report=qa_report(project,mp4,str(Path(args.output).with_suffix('.qa.json')))
    print('Created:',mp4,'Warnings:',report['warnings'])
    return 0

if __name__=='__main__':sys.exit(main())
