#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from session_client import SOCKET_PATH, ensure_daemon, package_version
from platform_runner import PLATFORMS, run_platform_action

def emit(x): print(json.dumps(x,ensure_ascii=False))

def status():
    daemon=ensure_daemon()
    helper=(ROOT/'admin.mjs').resolve()
    return {
        'version': package_version(),
        'platform_dir': str(PLATFORMS),
        'root': str(ROOT.resolve()),
        'cli': str(Path(__file__).resolve()),
        'admin_helper': str(helper),
        'managed_chrome': daemon.get('managed_chrome') if daemon else None,
        'daemon': {
            'running': bool(daemon and daemon.get('ok')),
            'pid': daemon.get('pid') if daemon else None,
            'session_count': daemon.get('session_count') if daemon else None,
            'socket': str(SOCKET_PATH),
        },
    }

def main():
    cli_name = 'webhelm'
    fmt=argparse.RawDescriptionHelpFormatter
    p=argparse.ArgumentParser(
        prog=cli_name,
        description='Control the shared Browser Workspace Chrome, browser sessions, and platform automations.',
        epilog='''Examples:
  webhelm status
  webhelm session start --url https://example.com
  webhelm session list
  webhelm session exec SESSION_ID --code-file script.py
  webhelm session stop SESSION_ID
  webhelm session stop --all
  webhelm platform profile wechat-channels
  webhelm platform run wechat-channels manage --session-id SESSION_ID --config status.json
  webhelm platform run wechat-channels post --session-id SESSION_ID --config post.json
  webhelm platform run wechat-channels manage --auto-session --config status.json
''',
        formatter_class=fmt,
    )
    sp=p.add_subparsers(dest='group',required=True,title='commands',metavar='COMMAND')

    sp.add_parser(
        'status',
        help='Show Browser Workspace runtime, managed Chrome, daemon, and active-session status.',
        description='Show Browser Workspace runtime, managed Chrome, daemon, and active-session status.',
        epilog='Example:\n  webhelm status',
        formatter_class=fmt,
    )

    session=sp.add_parser(
        'session',
        help='Create, inspect, execute code in, and stop browser sessions.',
        description='Manage Browser Workspace sessions.',
        epilog='''Examples:
  webhelm session start --url https://example.com
  webhelm session list
  webhelm session exec SESSION_ID --code-file script.py
  cat script.py | webhelm session exec SESSION_ID
  webhelm session stop SESSION_ID
  webhelm session stop --all
''',
        formatter_class=fmt,
    )
    ssp=session.add_subparsers(dest='cmd',required=True,title='session commands',metavar='COMMAND')

    start=ssp.add_parser(
        'start',
        help='Start a browser session, optionally opening a URL.',
        description='Start a browser session. The shared managed Chrome is reused; this does not launch a separate browser per session.',
        epilog='''Examples:
  webhelm session start
  webhelm session start --url https://example.com
''',
        formatter_class=fmt,
    )
    start.add_argument('--workspace', help=argparse.SUPPRESS)
    start.add_argument('--url', metavar='URL', help='URL to open when the session starts.')

    ssp.add_parser(
        'list',
        help='List currently active Browser Workspace sessions.',
        description='List currently active Browser Workspace sessions and their target tabs.',
        epilog='Example:\n  webhelm session list',
        formatter_class=fmt,
    )

    ex=ssp.add_parser(
        'exec',
        help='Execute Browser Workspace Python helpers inside an existing session.',
        description='Execute Python using Browser Workspace helpers in an existing session. Read code from --code-file or stdin.',
        epilog='''Examples:
  webhelm session exec SESSION_ID --code-file script.py

  webhelm session exec SESSION_ID <<'PY'
  print(page_info())
  print(snapshot(interactive_only=False))
  PY
''',
        formatter_class=fmt,
    )
    ex.add_argument('session_id', metavar='SESSION_ID', help='Session ID returned by "session start" or "session list".')
    ex.add_argument('--code-file', metavar='PATH', help='Read Python code from this file instead of stdin.')

    stop=ssp.add_parser(
        'stop',
        help='Stop one session or all sessions and release their Browser Workspace tabs.',
        description='Stop one Browser Workspace session, or all sessions with --all.',
        epilog='''Examples:
  webhelm session stop SESSION_ID
  webhelm session stop --all
''',
        formatter_class=fmt,
    )
    stop.add_argument('session_id', nargs='?', metavar='SESSION_ID', help='Session ID to stop.')
    stop.add_argument('--all', action='store_true', dest='stop_all', help='Stop all active Browser Workspace sessions.')

    platform=sp.add_parser(
        'platform',
        help='Inspect and run reusable website-specific platform automations.',
        description='Inspect and run reusable Browser Workspace platform automations.',
        epilog='''Examples:
  webhelm platform profile wechat-channels
  webhelm platform source wechat-channels post --config post.json
  webhelm session start --url https://channels.weixin.qq.com/platform/post/list
  webhelm platform run wechat-channels manage --session-id SESSION_ID --config status.json
  webhelm platform run wechat-channels post --session-id SESSION_ID --config post.json
  webhelm platform run chatgpt new-turn --config turn.json
  webhelm platform run chatgpt new-turn --mode sync --session-id SESSION_ID --config turn.json
  webhelm session stop SESSION_ID

One-shot mode (no orchestrator self-heal):
  webhelm platform run wechat-channels manage --auto-session --config status.json
''',
        formatter_class=fmt,
    )
    psp=platform.add_subparsers(dest='pcmd',required=True,title='platform commands',metavar='COMMAND')

    psp.add_parser(
        'list',
        help='List platforms available from WEBHELM_PLATFORM_DIR.',
        description='List platform adapters found in WEBHELM_PLATFORM_DIR.',
        epilog='Example:\n  webhelm platform list',
        formatter_class=fmt,
    )

    profile=psp.add_parser(
        'profile',
        help='Show a platform manifest/profile: fields, media rules, and capabilities.',
        description='Show the declared Browser Workspace profile for a platform.',
        epilog='Example:\n  webhelm platform profile wechat-channels',
        formatter_class=fmt,
    )
    profile.add_argument('platform', metavar='PLATFORM', help='Platform name, for example "wechat-channels".')

    source=psp.add_parser(
        'source',
        help='Print the fully prepared Python source for one platform action without running it.',
        description='Render the action source after injecting the optional JSON config path. No browser action is executed.',
        epilog='''Examples:
  webhelm platform source wechat-channels post --config post.json
  webhelm platform source wechat-channels manage --config status.json
''',
        formatter_class=fmt,
    )
    source.add_argument('platform', metavar='PLATFORM', help='Platform name, for example "wechat-channels".')
    source.add_argument('action', metavar='ACTION', help='Declared action name, for example "post" or "manage".')
    source.add_argument('--config', metavar='PATH', help='JSON configuration file used to prepare the action.')

    run=psp.add_parser(
        'run',
        help='Run one platform action in Browser Workspace.',
        description='Run a declared platform action. ChatGPT new-turn accepts mode async (the default durable queue) or sync (immediate execution in a caller-owned session); both return status submitted. Other actions require a caller-owned --session-id by default so an orchestrator can inspect failures and self-heal in the same browser state. --auto-session is an explicit one-shot mode without orchestrator self-heal.',
        epilog='''Examples:
  webhelm session start --url https://channels.weixin.qq.com/platform/post/list
  webhelm platform run wechat-channels manage --session-id SESSION_ID --config status.json
  webhelm platform run wechat-channels post --session-id SESSION_ID --config post.json
  webhelm platform run chatgpt new-turn --config turn.json
  webhelm platform run chatgpt new-turn --mode sync --session-id SESSION_ID --config turn.json
  webhelm session stop SESSION_ID

One-shot mode (no orchestrator self-heal):
  webhelm platform run wechat-channels manage --auto-session --config status.json
''',
        formatter_class=fmt,
    )
    run.add_argument('platform', metavar='PLATFORM', help='Platform name, for example "wechat-channels".')
    run.add_argument('action', metavar='ACTION', help='Declared action name, for example "post" or "manage".')
    run.add_argument('--config', metavar='PATH', help='JSON configuration file for the platform action.')
    run.add_argument('--url', metavar='URL', help='Optional initial URL for a temporary session.')
    run.add_argument('--mode', choices=('async', 'sync'), help='For chatgpt new-turn: async uses the durable queue (default); sync executes in the caller-owned --session-id. The config may also set mode to exactly async or sync.')
    session_mode = run.add_mutually_exclusive_group()
    session_mode.add_argument('--session-id', metavar='SESSION_ID', help='Required by default. Reuse a caller-owned session so failures can be inspected and self-healed before the session is closed.')
    session_mode.add_argument('--auto-session', action='store_true', help='Explicit one-shot mode: create and clean up a temporary session automatically. No orchestrator self-heal is available after failure.')
    args=p.parse_args()
    if args.group=='status': emit(status()); return
    if args.group=='session' and args.cmd=='list':
        from session_client import request
        emit(request({'op':'list'})); return
    if args.group=='session' and args.cmd=='start':
        from session_client import request
        emit(request({'op':'start','workspace':args.workspace,'url':args.url})); return
    if args.group=='session' and args.cmd=='exec':
        from session_client import request
        if args.code_file: code=Path(args.code_file).read_text()
        elif not sys.stdin.isatty(): code=sys.stdin.read()
        else: p.error('session exec reads Python from stdin (use a heredoc) or --code-file')
        r=request({'op':'exec','session_id':args.session_id,'code':code}); emit(r); raise SystemExit(0 if r.get('ok',False) else 1)
    if args.group=='session' and args.cmd=='stop':
        from session_client import request
        if args.stop_all:
            if args.session_id: p.error('session stop accepts either SESSION_ID or --all, not both')
            emit(request({'op':'stop-all'})); return
        if not args.session_id: p.error('session stop requires SESSION_ID or --all')
        emit(request({'op':'stop','session_id':args.session_id})); return
    if args.group=='platform' and args.pcmd=='source':
        from platform_runner import action_path, prepare_action
        path=action_path(args.platform,args.action); config=Path(args.config) if args.config else None
        sys.stdout.write(prepare_action(path,config)); return
    if args.group=='platform' and args.pcmd=='list':
        from platform_runner import list_platforms
        emit(list_platforms()); return
    if args.group=='platform' and args.pcmd=='profile':
        from platform_runner import platform_profile
        emit(platform_profile(args.platform)); return
    if args.group=='platform' and args.pcmd=='run':
        if args.mode and (args.platform != 'chatgpt' or args.action.replace('_','-') != 'new-turn'):
            p.error('--mode is only supported for chatgpt new-turn')
        if args.mode == 'sync' and not args.session_id:
            p.error("mode 'sync' requires a caller-owned --session-id")
        if not args.session_id and not args.auto_session and not (args.platform == 'chatgpt' and args.action.replace('_','-') == 'new-turn'):
            emit({
                'ok': False,
                'error': 'session_id_required',
                'message': 'platform run requires --session-id by default so the orchestrator can self-heal failures in the same browser session.',
                'suggested_workflow': [
                    f'{cli_name} session start --url <URL>',
                    f'{cli_name} platform run <PLATFORM> <ACTION> --session-id SESSION_ID [--config FILE]',
                    'inspect/self-heal failures in the same SESSION_ID and write successful repairs back to platform code',
                    f'{cli_name} session stop SESSION_ID',
                ],
                'auto_session': 'Use --auto-session only for a one-shot run. It creates and closes its own session and does not provide orchestrator self-heal.',
            })
            raise SystemExit(2)
        r=run_platform_action(args.platform,args.action,config_path=args.config,url=args.url,session_id=args.session_id,auto_session=args.auto_session,mode=args.mode); emit(r); raise SystemExit(0 if (r.get('result') or {}).get('ok',False) else 1)
if __name__=='__main__': main()
