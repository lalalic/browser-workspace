import { sleep } from "../../_action_helpers.mjs";
import {
  chooseManagerRow,
  extractStableId,
  MANAGER_URL,
  managerScanExpression,
  statusLabel,
} from "./_common.mjs";
export default async function manage(
  { config: c, helpers: h, log = console.log },
) {
  const op = c.operation;
  if (op !== "status") {
    const r = {
      ok: false,
      platform: "wechat-channels",
      operation: op,
      error: "unsupported_operation",
      supported_operations: ["status"],
    };
    log(JSON.stringify(r));
    throw Object.assign(new Error("unsupported_operation"), { result: r });
  }
  await h.goto_url(MANAGER_URL);
  await h.wait_for_load();
  const end = Date.now() + 30000, contentEnd = Date.now() + 12000;
  let row = null;
  while (Date.now() < end) {
    const raw = await h.js(managerScanExpression(c.post_id, c.title, c.desc)) ||
      "[]";
    let rows = [];
    try {
      rows = JSON.parse(raw);
    } catch {}
    row = chooseManagerRow(rows, c.post_id, c.title, c.desc);
    if (row) break;
    const body = await h.js(
      '(document.querySelector("wujie-app")?.shadowRoot?.querySelector("body")?.innerText||"").trim()',
    );
    if (body && Date.now() >= contentEnd) break;
    await sleep(1000);
  }
  const state = row
    ? statusLabel(row.text || {})
    : { status: null, label: null };
  const result = {
    ok: !!state.status,
    platform: "wechat-channels",
    operation: "status",
    status: state.status || "not_found",
    post_id: row ? extractStableId(row) || c.post_id : null,
    status_label: state.label,
    target: {
      post_id: c.post_id || null,
      title: c.title || null,
      desc: c.desc || null,
    },
    reason: row
      ? (state.status ? null : "status_label_not_found")
      : "no_matching_manager_row",
    row,
  };
  log(JSON.stringify(result));
  return result;
}
