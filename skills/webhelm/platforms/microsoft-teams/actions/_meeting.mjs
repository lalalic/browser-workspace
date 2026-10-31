import { sleep } from "../../_action_helpers.mjs";
const URL = "https://teams.cloud.microsoft/";
export default async function meeting(
  { config: cfg, helpers: h, log = console.log },
) {
  const action = cfg.action || "status",
    allowed = ["start-instant-meeting", "status", "leave"];
  const fail = async (error, extra = {}) => {
    const x = { action, ok: false, error, ...extra };
    log(JSON.stringify(x));
    const e = new Error(error);
    e.result = x;
    throw e;
  };
  const evidence = async (extra = {}) => {
    const x = { action, ok: true, url: (await h.page_info()).url, ...extra };
    log(JSON.stringify(x));
    return x;
  };
  const status = () =>
    h.js(
      `(()=>({title:document.title,prejoin:!!document.querySelector('#prejoin-join-button'),duration:document.querySelector('#call-duration-custom,[data-tid="call-duration"]')?.textContent||null,hangup:!!document.querySelector('#hangup-button'),profile:document.querySelector('#idna-me-control-avatar-trigger')?.getAttribute('aria-label')||''}))()`,
    );
  const until = async (check, timeout, message) => {
    const end = Date.now() + timeout * 1000;
    while (Date.now() < end) {
      const v = await check();
      if (v) return v;
      await sleep(250);
    }
    return fail(message, {
      title: (await h.page_info()).title,
      url: (await h.page_info()).url,
    });
  };
  if (!allowed.includes(action)) return fail(`unsupported action: ${action}`);
  if (action === "status") return evidence({ state: await status() });
  if (action === "leave") {
    const before = await status();
    if (!before.duration && !before.hangup) {
      return evidence({ left: false, state: before });
    }
    const ok = await h.js(
      `(()=>{const b=document.querySelector('#hangup-button')||[...document.querySelectorAll('button')].find(b=>/leave|hang up/i.test(b.getAttribute('aria-label')||b.innerText||''));if(!b)return false;b.click();return true})()`,
    );
    if (!ok) {
      return fail(
        "in-call state observed but leave/hangup control was not clickable",
        { state: before },
      );
    }
    await until(
      async () => {
        const s = await status();
        return !s.duration && !s.hangup;
      },
      20,
      "meeting did not exit after leave",
    );
    return evidence({ left: true, before, after: await status() });
  }
  const target = await h.new_tab(URL);
  await until(
    () =>
      h.js(
        `!![...document.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'').startsWith('Calendar'))`,
      ),
    40,
    "Teams app bar did not expose Calendar",
  );
  const initial = await status();
  if (
    !(await h.js(
      `(()=>{const b=[...document.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'').startsWith('Calendar'));if(!b)return false;b.click();return true})()`,
    ))
  ) return fail("Calendar button was not clickable");
  const cal = await until(
    async () => {
      const xs = (await h.cdp("Target.getTargets")).targetInfos || [];
      return xs.find((t) =>
        t.type === "iframe" &&
        t.url.includes("outlook.office.com/hosted/calendar") &&
        t.parentId === target
      )?.targetId;
    },
    30,
    "Teams Calendar iframe did not become ready",
  );
  await until(
    () =>
      h.js(
        `!![...document.querySelectorAll('button')].find(b=>b.getAttribute('aria-label')==='Start an instant Teams meeting.')`,
        { target_id: cal },
      ),
    30,
    "Meet now button did not appear",
  );
  if (
    !(await h.js(
      `(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.getAttribute('aria-label')==='Start an instant Teams meeting.');if(!b)return false;b.click();return true})()`,
      { target_id: cal },
    ))
  ) return fail("Meet now button was not clickable");
  try {
    await until(
      () =>
        h.js(
          `!![...document.querySelectorAll('button')].find(b=>(b.innerText||'').includes('Start meeting'))`,
          { target_id: cal },
        ),
      8,
      "Start meeting dialog did not appear",
    );
    await h.js(
      `(()=>{const b=[...document.querySelectorAll('button')].find(b=>(b.innerText||'').includes('Start meeting'));if(b)b.click()})()`,
      { target_id: cal },
    );
  } catch {}
  const prejoin = await until(
    () => h.js("!!document.querySelector('#prejoin-join-button')"),
    40,
    "Meet now did not reach Teams pre-join",
  );
  if (
    !(await h.js(
      `(()=>{const b=document.querySelector('#prejoin-join-button');if(!b)return false;b.click();return true})()`,
    ))
  ) return fail("Join now button was not clickable");
  const inCall = await until(
    async () => {
      const s = await status();
      return s.duration || s.hangup ? s : null;
    },
    40,
    "Teams did not reach in-call state after Join now",
  );
  return evidence({ target_id: target, initial, prejoin, in_call: inCall });
}
