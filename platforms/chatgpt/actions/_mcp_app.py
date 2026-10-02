import json
import time

CFG = json.load(open("__CFG_PATH__", encoding="utf-8"))
APP_NAME = str(CFG.get("app_name") or "").strip()
OP = str(CFG.get("operation") or "status").strip()

if not APP_NAME:
    raise ValueError("app_name is required")
if OP not in {"status", "open", "refresh-tools"}:
    raise ValueError("operation must be status, open, or refresh-tools")


def wait_until(pred, label, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = pred()
        if value:
            return value
        time.sleep(0.2)
    raise RuntimeError(f"{label} not observed")


def app_button_exists():
    return js(f"""(() => {{
      const name={json.dumps(APP_NAME)};
      return Array.from(document.querySelectorAll('button,a')).some(el => {{
        const text=(el.innerText||'').trim();
        return text===name || text.startsWith(name+'\\n');
      }});
    }})()""")


def open_app():
    ok = js(f"""(() => {{
      const name={json.dumps(APP_NAME)};
      const el=Array.from(document.querySelectorAll('button,a')).find(el => {{
        const text=(el.innerText||'').trim();
        return text===name || text.startsWith(name+'\\n');
      }});
      if(!el)return false; el.click(); return true;
    }})()""")
    if not ok:
        raise RuntimeError(f"installed ChatGPT plugin not found: {APP_NAME}")
    wait_until(lambda: js(f"document.querySelector('h1')?.innerText?.trim()==={json.dumps(APP_NAME)}"), "plugin detail page")


def detail_state():
    return js("""(() => {
      const texts=Array.from(document.querySelectorAll('button,a')).map(el=>(el.innerText||el.getAttribute('aria-label')||'').trim()).filter(Boolean);
      return {
        connected:texts.includes('Disconnect'),
        permissions:texts.includes('Permissions'),
        refresh_tools:texts.includes('Refresh tools'),
        editable:texts.includes('Edit'),
        uninstallable:texts.includes('Uninstall'),
        url:location.href
      };
    })()""")


goto_url("https://chatgpt.com/settings/plugins-settings")
wait_for_load()
wait_until(lambda: js("document.body?.innerText?.includes('Plugins')"), "ChatGPT Plugins settings")
wait_until(app_button_exists, f"installed plugin {APP_NAME}")
open_app()

if OP == "refresh-tools":
    ok = js("""(() => {
      const b=Array.from(document.querySelectorAll('button')).find(x=>(x.innerText||'').trim()==='Refresh tools');
      if(!b||b.disabled)return false; b.click(); return true;
    })()""")
    if not ok:
        raise RuntimeError("Refresh tools control is unavailable")
    time.sleep(0.5)

state = detail_state()
print(json.dumps({"app_name": APP_NAME, "operation": OP, **state}, ensure_ascii=False), flush=True)
