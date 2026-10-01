"""Microsoft Teams meeting mechanics for Browser Workspace session.

Executed inside Browser Workspace session. Keep the instant-meeting navigation in one
process so Browser Workspace tab/target identity remains authoritative.
"""

import json
import time

CFG = json.load(open("__CFG_PATH__", encoding="utf-8"))
ACTION = CFG.get("action", "status")
TEAMS_URL = "https://teams.cloud.microsoft/"
ALLOWED_ACTIONS = {"start-instant-meeting", "status", "leave"}


def fail(message, **extra):
    print(json.dumps({"action": ACTION, "ok": False, "error": message, **extra}, ensure_ascii=False))
    raise SystemExit(2)


def evidence(**extra):
    record = {"action": ACTION, "ok": True, "url": page_info().get("url"), **extra}
    print(json.dumps(record, ensure_ascii=False))
    return record


def wait_until(predicate, timeout=30.0, interval=0.25, message="condition not reached"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    fail(message, title=page_info().get("title"), url=page_info().get("url"))


def teams_status():
    return js("""(() => ({
      title: document.title,
      prejoin: !!document.querySelector('#prejoin-join-button'),
      duration: document.querySelector('#call-duration-custom,[data-tid="call-duration"]')?.textContent || null,
      hangup: !!document.querySelector('#hangup-button'),
      profile: document.querySelector('#idna-me-control-avatar-trigger')?.getAttribute('aria-label') || ''
    }))()""")


def wait_app_bar():
    return wait_until(
        lambda: js("""!![...document.querySelectorAll('button')].find(
          b => (b.getAttribute('aria-label') || '').startsWith('Calendar'))"""),
        timeout=40,
        message="Teams app bar did not expose Calendar",
    )


def click_calendar():
    ok = js("""(() => {
      const button = [...document.querySelectorAll('button')].find(
        b => (b.getAttribute('aria-label') || '').startsWith('Calendar'));
      if (!button) return false;
      button.click();
      return true;
    })()""")
    if not ok:
        fail("Calendar button was not clickable")


def calendar_target(parent_target):
    def resolve():
        targets = cdp("Target.getTargets").get("targetInfos", [])
        matches = [
            t for t in targets
            if t.get("type") == "iframe"
            and "outlook.office.com/hosted/calendar" in t.get("url", "")
            and t.get("parentId") == parent_target
        ]
        return matches[0].get("targetId") if matches else None

    return wait_until(resolve, timeout=30, message="Teams Calendar iframe did not become ready")


def click_meet_now(target_id):
    wait_until(
        lambda: js("""!![...document.querySelectorAll('button')].find(
          b => (b.getAttribute('aria-label') || '') === 'Start an instant Teams meeting.')""", target_id=target_id),
        timeout=30,
        message="Meet now button did not appear",
    )
    ok = js("""(() => {
      const button = [...document.querySelectorAll('button')].find(
        b => (b.getAttribute('aria-label') || '') === 'Start an instant Teams meeting.');
      if (!button) return false;
      button.click();
      return true;
    })()""", target_id=target_id)
    if not ok:
        fail("Meet now button was not clickable")




def start_meeting_dialog(target_id):
    """Handle Teams' intermediate 'Start a meeting now' dialog when present."""
    def find_button():
        return js("""(() => {
          const buttons = [...document.querySelectorAll('button')];
          const b = buttons.find(x => (x.innerText || '').includes('Start meeting'));
          return !!b;
        })()""", target_id=target_id)

    try:
        wait_until(find_button, timeout=8, message="Start meeting dialog did not appear")
    except SystemExit:
        return False

    ok = js("""(() => {
      const b = [...document.querySelectorAll('button')].find(
        x => (x.innerText || '').includes('Start meeting'));
      if (!b) return false;
      b.click();
      return true;
    })()""", target_id=target_id)
    if not ok:
        fail("Start meeting button was not clickable")
    return True

def wait_prejoin():
    wait_until(
        lambda: js("!!document.querySelector('#prejoin-join-button')"),
        timeout=40,
        message="Meet now did not reach Teams pre-join",
    )
    return teams_status()


def join_now():
    ok = js("""(() => {
      const button = document.querySelector('#prejoin-join-button');
      if (!button) return false;
      button.click();
      return true;
    })()""")
    if not ok:
        fail("Join now button was not clickable")


def wait_in_call():
    wait_until(
        lambda: (lambda s: s.get("duration") or s.get("hangup"))(teams_status()),
        timeout=40,
        message="Teams did not reach in-call state after Join now",
    )
    return teams_status()


def start_instant_meeting():
    target = new_tab(TEAMS_URL)
    wait_app_bar()
    initial = teams_status()
    click_calendar()
    cal = calendar_target(target)
    click_meet_now(cal)
    start_meeting_dialog(cal)
    try:
        prejoin = wait_prejoin()
    except SystemExit:
        current = teams_status()
        if "in a call" in (current.get("profile") or "").lower():
            fail(
                "account is already in a call; instant Meet now could not reach pre-join",
                profile=current.get("profile"),
            )
        raise
    join_now()
    incall = wait_in_call()
    return evidence(target_id=target, initial=initial, prejoin=prejoin, in_call=incall)


def leave():
    state = teams_status()
    if not state.get("duration") and not state.get("hangup"):
        return evidence(left=False, state=state)

    ok = js("""(() => {
      const button = document.querySelector('#hangup-button') ||
        [...document.querySelectorAll('button')].find(
          b => /leave|hang up/i.test(b.getAttribute('aria-label') || b.innerText || ''));
      if (!button) return false;
      button.click();
      return true;
    })()""")
    if not ok:
        fail("in-call state observed but leave/hangup control was not clickable", state=state)

    wait_until(
        lambda: not (teams_status().get("duration") or teams_status().get("hangup")),
        timeout=20,
        message="meeting did not exit after leave",
    )
    return evidence(left=True, before=state, after=teams_status())


if ACTION not in ALLOWED_ACTIONS:
    fail(f"unsupported action: {ACTION}")

if ACTION == "start-instant-meeting":
    start_instant_meeting()
elif ACTION == "leave":
    leave()
else:
    evidence(state=teams_status())
