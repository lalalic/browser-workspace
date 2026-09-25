import runpy
import sys
import types
import unittest
from pathlib import Path

HELPER = Path(__file__).resolve().parents[1] / "browser-harness" / "agent_helpers.py"


def load_helper():
    helpers = types.ModuleType("browser_harness.helpers")
    helpers.switch_tab = lambda *args, **kwargs: None
    helpers.current_tab = lambda: {"targetId": "current"}
    helpers.goto_url = lambda url: url
    helpers.cdp = lambda *args, **kwargs: {"targetInfos": []}
    helpers.js = lambda *args, **kwargs: None
    package = types.ModuleType("browser_harness")
    package.helpers = helpers
    old_package = sys.modules.get("browser_harness")
    old_helpers = sys.modules.get("browser_harness.helpers")
    sys.modules["browser_harness"] = package
    sys.modules["browser_harness.helpers"] = helpers
    try:
        return runpy.run_path(str(HELPER))
    finally:
        if old_package is None:
            sys.modules.pop("browser_harness", None)
        else:
            sys.modules["browser_harness"] = old_package
        if old_helpers is None:
            sys.modules.pop("browser_harness.helpers", None)
        else:
            sys.modules["browser_harness.helpers"] = old_helpers


class WorkspaceMappingTest(unittest.TestCase):
    def test_ensure_uses_workspace_ensure(self):
        module = load_helper()
        calls = []

        def manager_call(method, args=None):
            calls.append((method, args))
            return {"initialized": True, "poolSize": 4}

        ensure = module["_ensure_workspace"]
        ensure.__globals__["_manager_call"] = manager_call
        ensure.__globals__["_WORKSPACE_NAME"] = "Research"
        ensure.__globals__["_POOL_SIZE"] = 4
        self.assertEqual(ensure()["poolSize"], 4)
        self.assertEqual(
            calls,
            [("workspace.ensure", {"name": "Research", "poolSize": 4})],
        )

    def test_worker_waits_for_rpc_ready(self):
        module = load_helper()
        calls = {"js": 0}

        class Helpers:
            @staticmethod
            def cdp(method, **kwargs):
                if method == "Target.getTargets":
                    return {
                        "targetInfos": [{
                            "targetId": "worker",
                            "type": "service_worker",
                            "url": "chrome-extension://kgbghhigmbpefppgkocgjgnnnbhjchic/service-worker.mjs",
                        }]
                    }
                return {}

            @staticmethod
            def js(_expression, target_id=None):
                calls["js"] += 1
                return calls["js"] >= 2

        module["_bh"].cdp = Helpers.cdp
        module["_bh"].js = Helpers.js
        self.assertEqual(module["_worker_target"](), "worker")
        self.assertGreaterEqual(calls["js"], 2)

    def test_unique_mapping_and_ambiguous_drop(self):
        module = load_helper()
        mapper = module["_map_workspace_tabs"]
        chrome_tabs = [
            {"tabId": 1, "groupId": 7, "url": "https://one.test/", "title": "One"},
            {"tabId": 2, "groupId": 7, "url": "https://dup.test/", "title": "Same"},
        ]
        targets = [
            {"targetId": "a", "type": "page", "url": "https://one.test/", "title": "One"},
            {"targetId": "b", "type": "page", "url": "https://dup.test/", "title": "Same"},
            {"targetId": "c", "type": "page", "url": "https://dup.test/", "title": "Same"},
        ]
        self.assertEqual(
            mapper(chrome_tabs, targets),
            [{
                "targetId": "a",
                "target_id": "a",
                "tabId": 1,
                "groupId": 7,
                "title": "One",
                "url": "https://one.test/",
            }],
        )

    def test_remembered_mapping_survives_identical_url_and_title(self):
        module = load_helper()
        module["_remember_mapping"](1, "b")
        module["_remember_mapping"](2, "c")
        chrome_tabs = [
            {"tabId": 1, "groupId": 7, "url": "https://dup.test/", "title": "Same"},
            {"tabId": 2, "groupId": 7, "url": "https://dup.test/", "title": "Same"},
        ]
        targets = [
            {"targetId": "b", "type": "page", "url": "https://dup.test/", "title": "Same"},
            {"targetId": "c", "type": "page", "url": "https://dup.test/", "title": "Same"},
        ]
        mapped = module["_map_workspace_tabs"](chrome_tabs, targets)
        self.assertEqual(
            [(tab["tabId"], tab["targetId"]) for tab in mapped],
            [(1, "b"), (2, "c")],
        )

    def test_new_tab_learns_mapping_without_changing_caller_url(self):
        module = load_helper()
        calls = []
        target = {"targetId": "target-1", "type": "page", "url": "", "title": ""}

        def manager_call(method, args=None):
            calls.append((method, args))
            if method == "workspace.acquire":
                target["url"] = args["url"]
                return {"tabId": 42}
            return {"released": True}

        new_tab = module["new_tab"]
        new_tab.__globals__["_manager_call"] = manager_call
        new_tab.__globals__["_page_targets"] = lambda: [target.copy()]
        new_tab.__globals__["_original_switch_tab"] = (
            lambda target_id, activate=False: calls.append(("switch", target_id, activate))
        )
        new_tab.__globals__["_original_goto_url"] = lambda url: calls.append(("goto", url))

        target_id = new_tab("https://chatgpt.com/?model=test")
        self.assertEqual(target_id, "target-1")
        acquire_url = calls[0][1]["url"]
        self.assertIn("__browser_workspace_lease=", acquire_url)
        self.assertIn("model=test", acquire_url)
        self.assertEqual(calls[-1], ("goto", "https://chatgpt.com/?model=test"))
        self.assertEqual(module["_tab_to_target"], {42: "target-1"})
        self.assertEqual(module["_target_to_tab"], {"target-1": 42})


if __name__ == "__main__":
    unittest.main()
