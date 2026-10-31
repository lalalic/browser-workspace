import { sleep } from "../../_action_helpers.mjs";
import {
  chooseManagerRow,
  extractStableId,
  MANAGER_URL,
  managerScanExpression,
  statusLabel,
} from "./_common.mjs";
export default async function post(
  { config: c, helpers: h, log = console.log },
) {
  const open = async (url) => {
    const info = await h.page_info();
    if (!info.url.includes("channels.weixin.qq.com")) await h.new_tab(url);
    else if (info.url !== url) await h.goto_url(url);
  };
  await open("https://channels.weixin.qq.com/platform/post/create");
  await h.wait_for_load();
  await sleep(4000);
  if ((await h.page_info()).url.toLowerCase().includes("login")) {
    throw new Error(
      "Not logged in. Scan QR at https://channels.weixin.qq.com/",
    );
  }
  if (
    !(await h.wait_for_element("wujie-app", { timeout: 10, visible: true }))
  ) throw new Error("Shadow DOM not found after 10s.");
  const sb =
    'document.querySelector("wujie-app").shadowRoot.querySelector("body")';
  if (!(await h.js(`!!${sb}.querySelector('.upload')`))) {
    throw new Error("Upload area not found.");
  }
  const sr = await h.cdp("DOM.performSearch", {
    query: 'input[type="file"][accept*="video"]',
  });
  if (!sr.resultCount) throw new Error("Cannot find video file input.");
  const ns = await h.cdp("DOM.getSearchResults", {
    searchId: sr.searchId,
    fromIndex: 0,
    toIndex: 1,
  });
  await h.cdp("DOM.setFileInputFiles", {
    files: [c.video],
    nodeId: ns.nodeIds[0],
  });
  await h.cdp("DOM.discardSearchResults", { searchId: sr.searchId });
  let completed = false;
  for (let i = 0; i < 120; i++) {
    await sleep(5000);
    const raw = await h.js(
      `(()=>{const t=${sb}.innerText||'',m=t.match(/(?:^|\\n)(\\d{1,3})%(?:\\n|$)/);return JSON.stringify({percent:m?+m[1]:null,uploading:t.includes('取消上传')})})()`,
    );
    let state = {};
    try {
      state = JSON.parse(raw);
    } catch {}
    if (state.percent == null && !state.uploading) {
      completed = true;
      break;
    }
  }
  if (!completed) {
    throw new Error("Upload did not reach a completed state before timeout");
  }
  let desc = c.desc;
  if (c.tags?.length) desc += " " + c.tags.map((t) => "#" + t).join(" ");
  await h.js(`${sb}.querySelector('.input-editor')?.focus()`);
  await h.js(
    `${sb}.querySelector('.input-editor').textContent=${JSON.stringify(desc)}`,
  );
  await h.js(
    `${sb}.querySelector('.input-editor').dispatchEvent(new Event('input',{bubbles:true}))`,
  );
  const actual = await h.js(
    `${sb}.querySelector('.input-editor')?.textContent?.substring(0,50)||''`,
  );
  if (!actual) {
    await h.js(
      `${sb}.querySelector('.input-editor').textContent=${
        JSON.stringify(c.desc)
      }`,
    );
    await h.js(
      `${sb}.querySelector('.input-editor').dispatchEvent(new Event('input',{bubbles:true}))`,
    );
  }
  if (c.title) {
    await h.js(
      `(()=>{const e=${sb}.querySelector('.weui-desktop-form__input');if(!e)return false;Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,${
        JSON.stringify(c.title)
      });e.dispatchEvent(new Event('input',{bubbles:true}));return true})()`,
    );
  }
  await h.capture_screenshot();
  const label = c.publish ? "发表" : "保存草稿";
  const clicked = await h.js(
    `(()=>{const b=[...${sb}.querySelectorAll('.weui-desktop-btn')].find(x=>x.textContent.trim()===${
      JSON.stringify(label)
    }&&!x.disabled&&!x.classList.contains('weui-desktop-btn_disabled'));if(!b)return false;b.click();return true})()`,
  );
  if (!clicked) {
    throw new Error(
      `${label} button disabled/not found. Check manager before retrying.`,
    );
  }
  await sleep(3000);
  if (c.publish) {
    await h.js(
      `${sb}.querySelectorAll('.weui-desktop-dialog__wrp').forEach(d=>{if(d.style.display!=='none')d.querySelector('.weui-desktop-btn_primary')?.click()})`,
    );
    await sleep(3000);
  }
  await h.goto_url(MANAGER_URL);
  await h.wait_for_load();
  const end = Date.now() + 40000, contentEnd = Date.now() + 15000;
  let row = null;
  while (Date.now() < end) {
    const raw = await h.js(managerScanExpression("", c.title, c.desc)) || "[]";
    let rows = [];
    try {
      rows = JSON.parse(raw);
    } catch {}
    row = chooseManagerRow(rows, null, c.title, c.desc);
    if (row) break;
    const body = await h.js(
      '(document.querySelector("wujie-app")?.shadowRoot?.querySelector("body")?.innerText||"").trim()',
    );
    if (body && Date.now() >= contentEnd) break;
    await sleep(1000);
  }
  const status = row
    ? statusLabel(row.text || {})
    : { status: "unknown", label: null };
  const result = {
    ok: c.publish
      ? ["published", "reviewing"].includes(status.status)
      : status.status === "draft",
    platform: "wechat-channels",
    operation: c.publish ? "publish" : "draft",
    status: status.status || "unknown",
    status_label: status.label,
    post_id: row ? extractStableId(row) : null,
    title: c.title,
    desc: c.desc,
    verified: ["published", "reviewing", "rejected", "draft"].includes(
      status.status,
    ),
    reason: row ? null : "no_matching_manager_row",
    row,
    retry_safe: false,
  };
  log(JSON.stringify(result));
  await h.capture_screenshot();
  if (!result.ok) {
    throw Object.assign(
      new Error(result.reason || "manager verification failed"),
      { result },
    );
  }
  return result;
}
