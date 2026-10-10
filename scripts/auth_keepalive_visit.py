#!/usr/bin/env python3
"""Proactive authenticated page visits using an existing Browser Workspace Chrome session.

Never copies or edits cookies, logs only redacted page status, and stops only sessions
created by this run. It cannot bypass Google or WeChat reauthentication.
"""
import json
from pathlib import Path
import subprocess
import sys
import time

CLI = ['/opt/homebrew/bin/uvx', '--from', 'browser-workspace', 'browser-workspace', 'session']
AUDIT = ['/usr/bin/python3', str(Path.home() / '.config/browser-workspace/tasks/auth-cookie-audit.py')]
SITES = (
    ('wechat', 'https://channels.weixin.qq.com/platform/post'),
    ('xiaohongshu', 'https://www.xiaohongshu.com/explore?channel_id=homefeed_recommend'),
    ('google_store', 'https://chrome.google.com/webstore/devconsole'),
)
CODE = "print(page_info())\nprint(str(snapshot())[:2000])\nprint(str(snapshot())[-1500:])\n"


def run(command, *, input=None, timeout=20):
    result = subprocess.run(command, input=input, capture_output=True,
                            text=True, timeout=timeout, check=True)
    return json.loads(result.stdout)


def classify(site, output):
    text = output.lower()
    if site == 'wechat':
        if '内容管理' in output and '数据中心' in output:
            return 'logged_in', 'backend_visible'
        if '加载失败，点击重试' in output:
            return 'page_error', 'page_load_failed'
    if site == 'google_store':
        if 'Switch Publisher Account Menu' in output and 'Add a new item' in output:
            return 'logged_in', 'backend_visible'
    if site == 'xiaohongshu':
        if '发布' in output and '消息' in output and '我' in output:
            return 'unknown', 'feed_only'
    if 'signin/confirmidentifier' in text or '/login.html' in text:
        return 'login_required', 'login_redirect'
    return 'unknown', 'unknown'


def visit(site, url):
    session_id = None
    status, evidence = 'unknown', 'unknown'
    retries = 0
    error = None
    cleanup = None
    try:
        started = run(CLI + ['start', '--url', url], timeout=25)
        session_id = started['session_id']
        for i in range(3):
            result = run(CLI + ['exec', session_id], input=CODE, timeout=25)
            status, evidence = classify(site, result.get('stdout', ''))
            if status != 'unknown' or evidence != 'unknown':
                break
            if i < 2:
                retries += 1
                time.sleep(2)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, KeyError) as exc:
        error = type(exc).__name__
    finally:
        if session_id:
            for i in range(3):
                try:
                    stopped = run(CLI + ['stop', session_id], timeout=20)
                    cleanup = stopped.get('release_error') is None
                    if cleanup:
                        break
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
                    cleanup = False
        try:
            run(AUDIT + ['--site', site, '--status', status,
                         '--page-evidence', evidence], timeout=20)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
            error = error or 'AuditFailed'
    return {'site': site, 'status': status, 'evidence': evidence, 'retries': retries,
            'session_closed': cleanup, 'error': error}


def main():
    # Capture a fresh before-visit baseline even if sampling cron was delayed.
    try:
        run(AUDIT, timeout=20)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
        pass
    results = []
    for site, url in SITES:
        results.append(visit(site, url))
    print(json.dumps({'timestamp': int(time.time()), 'results': results},
                     sort_keys=True))
    return 1 if any(item['session_closed'] is not True for item in results) else 0


if __name__ == '__main__':
    sys.exit(main())
