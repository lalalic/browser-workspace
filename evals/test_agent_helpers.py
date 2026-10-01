import ast
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
    def test_rewritten_browser_harness_functions_keep_exact_signatures(self):
        upstream = (
            Path.home()
            / ".local/share/uv/tools/browser-harness/lib/python3.12/site-packages/browser_harness/helpers.py"
        )

        def function_signatures(path):
            tree = ast.parse(path.read_text())
            return {
                node.name: ast.dump(node.args, include_attributes=False)
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }

        upstream_signatures = function_signatures(upstream)
        workspace_signatures = function_signatures(HELPER)
        rewritten = sorted(set(upstream_signatures) & set(workspace_signatures))
        self.assertTrue(rewritten)
        mismatches = {
            name: (upstream_signatures[name], workspace_signatures[name])
            for name in rewritten
            if upstream_signatures[name] != workspace_signatures[name]
        }
        self.assertEqual(mismatches, {})


    def test_snapshot_formats_dom_ref(self):
        module = load_helper()
        line = module["_snapshot_line"]("button", "Meet now", "e7")
        self.assertEqual(line, '- button "Meet now" [ref=e7]')

    def test_click_uses_data_ref_as_normal_css_selector(self):
        module = load_helper()
        calls = []

        def js(expression, target_id=None):
            calls.append((expression, target_id))
            return True

        module["_bh"].js = js
        self.assertTrue(module["click"]('[data-ref="e7"]'))
        self.assertIn('document.querySelector("[data-ref=\\"e7\\"]")', calls[0][0])

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

    def test_workspace_capacity_reports_available_counts(self):
        module = load_helper()
        capacity = module["workspace_capacity"]
        capacity.__globals__["workspace_status"] = lambda: {
            "name": "Research",
            "initialized": True,
            "poolSize": 5,
            "maxCapacity": 5,
            "physicalTabs": 3,
            "idleTabIds": [],
            "leasedTabIds": [1, 2, 3],
        }

        self.assertEqual(
            capacity(),
            {
                "name": "Research",
                "poolSize": 5,
                "maxCapacity": 5,
                "physicalTabs": 3,
                "idle": 0,
                "leased": 3,
                "available": 2,
            },
        )

    def test_workspace_capacity_reports_exhausted_pool(self):
        module = load_helper()
        capacity_probe = module["workspace_capacity"]
        capacity_probe.__globals__["workspace_status"] = lambda: {
            "name": "Harness",
            "initialized": True,
            "poolSize": 2,
            "maxCapacity": 2,
            "physicalTabs": 2,
            "idleTabIds": [],
            "leasedTabIds": [7, 8],
        }

        capacity = capacity_probe()
        self.assertEqual(capacity["idle"], 0)
        self.assertEqual(capacity["leased"], 2)
        self.assertEqual(capacity["available"], 0)

    def test_workspace_capacity_does_not_fabricate_failed_probe(self):
        module = load_helper()

        def unavailable():
            raise RuntimeError("extension unavailable")

        capacity_probe = module["workspace_capacity"]
        capacity_probe.__globals__["workspace_status"] = unavailable
        capacity = capacity_probe()
        self.assertIsNone(capacity["available"])
        self.assertIsNone(capacity["idle"])
        self.assertEqual(capacity["error"], "extension unavailable")

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

    def test_new_tab_learns_mapping_from_tabid_title_not_url(self):
        module = load_helper()
        calls = []
        target = {
            "targetId": "target-1",
            "type": "page",
            "url": "chrome-extension://workspace/workspace.html?role=lease&slot=42",
            "title": "__BW_TAB_42__",
        }

        def manager_call(method, args=None):
            calls.append((method, args))
            if method == "workspace.acquireIdentity":
                return {"tabId": 42, "identityTitle": "__BW_TAB_42__"}
            return {"released": True}

        new_tab = module["new_tab"]
        new_tab.__globals__["_manager_call"] = manager_call
        new_tab.__globals__["_page_targets"] = lambda: [target.copy()]
        new_tab.__globals__["_original_switch_tab"] = (
            lambda target_id, activate=False: calls.append(("switch", target_id, activate))
        )
        new_tab.__globals__["_original_goto_url"] = lambda url: calls.append(("goto", url))

        target_id = new_tab("https://example.com")
        self.assertEqual(target_id, "target-1")
        self.assertEqual(calls[0], ("workspace.acquireIdentity", {"name": "Harness"}))
        self.assertEqual(calls[-1], ("goto", "https://example.com"))
        self.assertEqual(module["_tab_to_target"], {42: "target-1"})
        self.assertEqual(module["_target_to_tab"], {"target-1": 42})

    def test_new_tab_ignores_destination_url_when_identifying_target(self):
        module = load_helper()
        calls = []
        targets = [
            {
                "targetId": "target-1",
                "type": "page",
                "url": "https://example.com/",
                "title": "__BW_TAB_77__",
            },
            {
                "targetId": "wrong-url-match",
                "type": "page",
                "url": "https://example.com",
                "title": "Other page",
            },
        ]

        def manager_call(method, args=None):
            if method == "workspace.acquireIdentity":
                return {"tabId": 77, "identityTitle": "__BW_TAB_77__"}
            return {"released": True}

        new_tab = module["new_tab"]
        new_tab.__globals__["_manager_call"] = manager_call
        new_tab.__globals__["_page_targets"] = lambda: [item.copy() for item in targets]
        new_tab.__globals__["_original_switch_tab"] = lambda *args, **kwargs: None
        new_tab.__globals__["_original_goto_url"] = lambda url: calls.append(url)

        self.assertEqual(new_tab("https://example.com"), "target-1")
        self.assertEqual(calls, ["https://example.com"])


if __name__ == "__main__":
    unittest.main()
