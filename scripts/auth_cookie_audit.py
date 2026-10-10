#!/usr/bin/env python3
"""Read-only Chrome cookie metadata audit. Never exports credential values.

Snapshots are HMAC-keyed so they support longitudinal comparisons without
storing recoverable cookies. Chrome remains running; no browser commands issued.
"""
import argparse
import datetime as dt
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import time

SITES = {
    'wechat': ('weixin.qq.com',),
    'xiaohongshu': ('xiaohongshu.com',),
    'google_store': ('google.com', 'googleusercontent.com'),
}
CHROME_EPOCH_OFFSET = 11644473600
# Non-secret cookie names, never values. Watch the known WeChat session pair.
WATCHED_COOKIES = {'wechat': {'sessionid', 'wxuin'}}


def utc_cookie_time(micros):
    if not micros:
        return None
    return int(micros / 1_000_000 - CHROME_EPOCH_OFFSET)


def domain_matches(host, domain):
    return host.lstrip('.').lower() == domain or host.lstrip('.').lower().endswith('.' + domain)


def load_key(path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    except FileNotFoundError:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.write(fd, secrets.token_bytes(32))
            finally:
                os.close(fd)
        except FileExistsError:
            pass
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        if os.fstat(fd).st_mode & 0o077:
            raise PermissionError('HMAC key must be readable only by owner')
        key = os.read(fd, 128)
        if len(key) != 32:
            raise ValueError('invalid HMAC key')
        return key
    finally:
        os.close(fd)


def collect(db_path, key):
    # Opening immutable databases ignores WAL; mode=ro sees committed WAL data.
    connection = sqlite3.connect(f'{db_path.resolve().as_uri()}?mode=ro', uri=True, timeout=5)
    try:
        connection.execute('PRAGMA query_only=ON')
        rows = connection.execute('''SELECT host_key, name, path, top_frame_site_key,
          encrypted_value, value, expires_utc, creation_utc, last_update_utc,
          last_access_utc, is_secure, is_httponly, samesite, is_persistent
          FROM cookies''')
        result = {}
        for (host, name, path, partition, encrypted, value, expires,
             created, updated, accessed, secure, httponly, samesite, persistent) in rows:
            sites = [site for site, domains in SITES.items()
                     if any(domain_matches(host, d) for d in domains)]
            if not sites:
                continue
            # Never persist (or print) raw cookie values, or unhashed plaintext.
            raw = encrypted if encrypted else (value or '').encode()
            digest = hmac.new(key, raw, hashlib.sha256).hexdigest()[:24]
            # Stable ID hides cookie names and paths as well: logs expose counts,
            # metadata and opaque identifiers, not domain-scoped auth cookie names.
            identity = '\0'.join((host, name, path, partition or '')).encode()
            identifier = hmac.new(key, identity, hashlib.sha256).hexdigest()[:24]
            record = {
                'id': identifier, 'host': host, 'fingerprint': digest,
                'expires_at': utc_cookie_time(expires),
                'created_at': utc_cookie_time(created),
                'updated_at': utc_cookie_time(updated),
                'last_access_at': utc_cookie_time(accessed),
                'persistent': bool(persistent), 'secure': bool(secure),
                'http_only': bool(httponly), 'same_site': samesite,
                'partitioned': bool(partition),
                'watched_name': name if any(name in WATCHED_COOKIES.get(site, set()) for site in sites) else None,
            }
            for site in sites:
                result.setdefault(site, {})[identifier] = record
        return {site: result.get(site, {}) for site in SITES}
    finally:
        connection.close()


def difference(previous, current):
    result = {}
    for site, data in current.items():
        old = previous.get(site, {})
        before, after = set(old), set(data)
        changes = {'added': len(after - before), 'removed': len(before - after),
                   'value_rotated': 0, 'expiry_extended': 0,
                   'expiry_shortened': 0, 'last_update_changed': 0}
        for identifier in before & after:
            a, b = old[identifier], data[identifier]
            changes['value_rotated'] += a['fingerprint'] != b['fingerprint']
            if a['expires_at'] is not None and b['expires_at'] is not None:
                changes['expiry_extended'] += b['expires_at'] > a['expires_at']
                changes['expiry_shortened'] += b['expires_at'] < a['expires_at']
            changes['last_update_changed'] += a['updated_at'] != b['updated_at']
        result[site] = changes
    return result


def append_jsonl(path, event):
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        os.write(fd, (json.dumps(event, ensure_ascii=False, sort_keys=True) + '\n').encode())
        os.fsync(fd)
    finally:
        os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, default=Path.home() / '.config/browser-workspace/chrome')
    parser.add_argument('--data-dir', type=Path, default=Path.home() / '.config/browser-workspace/auth-audit')
    parser.add_argument('--status', choices=['unknown', 'logged_in', 'login_required', 'page_error'], default='unknown',
                        help='Optional manually confirmed status; not inferred from cookie presence')
    parser.add_argument('--site', choices=list(SITES), help='Site to attach an observed status to')
    parser.add_argument('--page-evidence', choices=['backend_visible', 'login_redirect', 'page_load_failed', 'feed_only', 'unknown'], default='unknown',
                        help='Optional observable reason (never URLs, user content, or credentials)')
    args = parser.parse_args(argv)
    args.data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(args.data_dir, 0o700)
    db = args.profile / 'Default' / 'Cookies'
    if not db.is_file():
        parser.error('Chrome Cookie database not found; refusing to start Chrome or change profiles')
    key = load_key(args.data_dir / 'audit.key')
    with (args.data_dir / 'collector.lock').open('a+') as guard:
        os.chmod(args.data_dir / 'collector.lock', 0o600)
        fcntl.flock(guard, fcntl.LOCK_EX)
        return sample_locked(args, db, key)


def sample_locked(args, db, key):
    now = int(time.time())
    current = collect(db, key)
    state_path = args.data_dir / 'latest.json'
    previous = {}
    if state_path.exists():
        previous = json.loads(state_path.read_text()).get('sites', {})
    change = difference(previous, current)
    summary = {site: {
        'count': len(cookies),
        'expired': sum(item['expires_at'] is not None and item['expires_at'] <= now for item in cookies.values()),
        'session_cookies': sum(not item['persistent'] for item in cookies.values()),
        'next_expiry_at': min((item['expires_at'] for item in cookies.values()
                               if item['expires_at'] is not None and item['expires_at'] > now), default=None),
        **change[site],
    } for site, cookies in current.items()}
    watched = {site: {name: {'expires_at': item['expires_at'],
                 'updated_at': item['updated_at'],
                 'created_at': item['created_at']}
                 for item in cookies.values() if (name := item.get('watched_name'))}
               for site, cookies in current.items() if site in WATCHED_COOKIES}
    event = {'schema': 2, 'watched_cookie_metadata': watched, 'timestamp': now, 'utc': dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(),
             'profile': str(args.profile), 'sites': summary,
             'observed_status': {args.site: args.status} if args.site else {},
             'page_evidence': {args.site: args.page_evidence} if args.site else {}}
    append_jsonl(args.data_dir / 'events.jsonl', event)
    state = {'timestamp': now, 'sites': current}
    tmp_path = args.data_dir / f'.latest-{os.getpid()}.tmp'
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(state, f, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, state_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    print(json.dumps(event, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
