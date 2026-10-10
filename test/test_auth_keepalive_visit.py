"""Proactive page-check classifier and cleanup guarantees."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

p = Path(__file__).resolve().parents[1] / 'scripts' / 'auth_keepalive_visit.py'
spec = importlib.util.spec_from_file_location('auth_keepalive_visit', p)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class KeepaliveTest(unittest.TestCase):
    def test_login_classification(self):
        self.assertEqual(module.classify('wechat', '内容管理 数据中心'), ('logged_in', 'backend_visible'))
        self.assertEqual(module.classify('wechat', '加载失败，点击重试'), ('page_error', 'page_load_failed'))
        self.assertEqual(module.classify('google_store', 'accounts.google.com/v3/signin/confirmidentifier'), ('login_required', 'login_redirect'))
        self.assertEqual(module.classify('google_store', 'Switch Publisher Account Menu Add a new item'), ('logged_in', 'backend_visible'))
        self.assertEqual(module.classify('xiaohongshu', '发布 消息 我'), ('unknown', 'feed_only'))

    def test_stop_even_if_snapshot_throws(self):
        calls = []
        def fake(command, **kwargs):
            calls.append(command)
            if 'start' in command:
                return {'session_id':'only-our-session'}
            if 'exec' in command:
                raise subprocess.TimeoutExpired(command, 1)
            if 'stop' in command:
                return {'release_error':None}
            return {}
        with patch.object(module, 'run', side_effect=fake):
            result = module.visit('wechat','https://channels.weixin.qq.com/platform/post')
        self.assertTrue(result['session_closed'])
        self.assertEqual(result['error'], 'TimeoutExpired')
        self.assertTrue(any(c[-2:] == ['stop','only-our-session'] for c in calls))

if __name__ == '__main__':
    unittest.main()
