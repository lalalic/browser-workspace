"""Regression coverage for read-only authentication cookie auditing."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'scripts' / 'auth_cookie_audit.py'
spec = importlib.util.spec_from_file_location('auth_cookie_audit', SOURCE)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class CookieAuditTests(unittest.TestCase):
    def test_domain_boundary(self):
        self.assertTrue(audit.domain_matches('.accounts.google.com', 'google.com'))
        self.assertFalse(audit.domain_matches('notgoogle.com', 'google.com'))
        self.assertFalse(audit.domain_matches('google.com.attacker.invalid', 'google.com'))

    def test_date_conversion(self):
        self.assertIsNone(audit.utc_cookie_time(0))
        self.assertEqual(audit.utc_cookie_time(11644473600 * 1_000_000), 0)

    def test_diff_distinguishes_renewal_and_rotation(self):
        a = {'fingerprint': 'one', 'expires_at': 2000, 'updated_at': 5}
        b = {'fingerprint': 'two', 'expires_at': 3000, 'updated_at': 6}
        change = audit.difference({'wechat': {'a': a}}, {'wechat': {'a': b, 'b': b}})['wechat']
        self.assertEqual(change, dict(added=1, removed=0, value_rotated=1,
            expiry_extended=1, expiry_shortened=0, last_update_changed=1))

    def test_collect_does_not_export_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'Cookies'
            c = sqlite3.connect(path)
            c.execute('''CREATE TABLE cookies(host_key text, name text, path text,
             top_frame_site_key text, encrypted_value blob, value text,
             expires_utc integer, creation_utc integer, last_update_utc integer,
             last_access_utc integer, is_secure integer, is_httponly integer,
             samesite integer, is_persistent integer)''')
            c.execute('INSERT INTO cookies VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                ('.google.com', 'SECRET-COOKIE-NAME', '/', '', b'SECRET-AUTH-VALUE', '',
                 0, 0, 0, 0, 1, 1, 1, 0))
            c.commit()
            c.close()
            collected = audit.collect(path, b'a'*32)
            data = json.dumps(collected)
            self.assertNotIn('SECRET-COOKIE-NAME', data)
            self.assertNotIn('SECRET-AUTH-VALUE', data)
            self.assertEqual(len(collected['google_store']), 1)
            self.assertEqual(len(collected['wechat']), 0)


if __name__ == '__main__':
    unittest.main()
