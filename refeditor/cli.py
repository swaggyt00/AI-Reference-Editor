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
    ck=commands.add_parser('ai-check',help='Test locally saved Gemini API key (one small API call)')
    ck.add_argument('--model',default='gemini-3.8-flash')
    ck.add_argument('--local-only',action='store_true',help='Check key decryption without a network API request')
    av=commands.add_parser('ai-analyze',help='Opt-in Gemini semantic notes for one supplied video')
    av.add_argument('--video',required=True)
    av.add_argument('--role',choices=['reference','source'],default='reference')
    av.add_argument('--model',default='gemini-3.8-flash')
    av.add_argument('--output',default='output/gemini-analysis.json')
    av.add_argument('--confirm-external-upload',action='store_true')
    w=commands.add_parser('web',help='Start the local upload-and-render browser editor')
    w.add_argument('--host',default='127.0.0.1')
    w.add_argument('--port',type=int,default=8000)
    w.add_argument('--storage',default='output/web')
    w.add_argument('--max-upload-mb',type=int,default=2048)
    args=ap.parse_args(argv)
    if args.command in ('ai-check','ai-analyze'):
        from .ai_gemini import check_connection, check_local_setup, analyze_video as ai_analyze
        try:
            if args.command == 'ai-check':
                if args.local_only:
                    result = check_local_setup()
                    print('LOCAL GEMINI KEY: OK. Decryption and SDK check passed; no API request made.')
                else:
                    print('Gemini local key and SDK check...',flush=True)
                    check_local_setup()
                    print('Gemini API request...',flush=True)
                    result = check_connection(model=args.model)
                    print('Gemini connected:',result['model'],'—',result['response'])
            else:
                target = ai_analyze(args.video,args.output,role=args.role,
                                    model=args.model,
                                    confirm_external_upload=args.confirm_external_upload)
                print('Gemini semantic notes saved:',target)
            return 0
        except Exception as exc:
            # Never print raw SDK errors that can contain request metadata.
            from .ai_gemini import safe_error_reason
            print('Gemini check failed:',safe_error_reason(exc),file=sys.stderr)
            return 2
    if args.command=='web':
        if args.max_upload_mb < 1:ap.error('--max-upload-mb must be positive')
        if not all(shutil.which(p) for p in ('ffmpeg','ffprobe')):
            ap.error('Install ffmpeg and ffprobe before starting the web editor')
        import uvicorn
        from .web import create_app
        app=create_app(args.storage,max_upload_bytes=args.max_upload_mb*1024**2)
        uvicorn.run(app,host=args.host,port=args.port,workers=1)
        return 0
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
