"""Read-only Send availability plus explicit, visible ChatGPT page errors."""
import json
import _lifecycle_common as common

common.js = js

config_path = __OPTIONAL_CONFIG_PATH__
cfg = json.load(open(config_path, encoding="utf-8")) if config_path else {}
probe = "BrowserWorkspaceValidateProbe20261020"
goto_url(common.target_url(
    project_id=str(cfg.get("project_id") or "").strip() or None,
    thread_id=str(cfg.get("thread_id") or "").strip() or None,
    temporary=bool(cfg.get("temporary", False)),
    prompt=probe,
))
wait_for_load()

# Error classification is separate from readiness. Reuse the delivery-page
# evidence already consumed by new-turn/new-thread rather than guessing from
# an empty or disabled composer.
error = common.visible_delivery_error()
if error:
    result = error
else:
    # An explicit login screen is evidence; a missing/disabled Send button is not.
    login_required = bool(js("""(() => {
      const visible = e => !!e.getClientRects().length;
      const login = [...document.querySelectorAll('a,button')].some(e =>
        visible(e) && /^(log in|sign in)$/i.test((e.innerText||'').trim()));
      const page = (document.body?.innerText||'').toLowerCase();
      return login && (page.includes('log in to chatgpt') || page.includes('sign in to chatgpt'));
    })()"""))
    result = 'authentication_required' if login_required else bool(common.prefilled_submit(probe, send=False)["send_enabled"])
print(json.dumps(result), flush=True)
