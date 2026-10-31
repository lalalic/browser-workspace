import { sleep, waitUntilStable } from "./_action-common.mjs";
export async function run({ helpers: h, config: c = {} }) {
  const { js, goto_url, wait_for_load } = h;
  const app_name = String(c.app_name || "").trim(),
    operation = String(c.operation || "status").trim();
  if (!app_name) throw new Error("app_name is required");
  if (!["status", "open", "refresh-tools"].includes(operation)) {
    throw new Error("operation must be status, open, or refresh-tools");
  }
  const exists = () =>
    js(
      `(() => {const n=${
        JSON.stringify(app_name)
      };return [...document.querySelectorAll('button,a')].some(e=>{const t=(e.innerText||'').trim();return t===n||t.startsWith(n+'\\n');});})()`,
    );
  await goto_url("https://chatgpt.com/settings/plugins-settings");
  await wait_for_load();
  await waitUntilStable(
    () => js(`document.body?.innerText?.includes('Plugins')`),
    Boolean,
    { timeout: 30, phase: "ChatGPT Plugins settings", sleep },
  );
  await waitUntilStable(exists, Boolean, {
    timeout: 30,
    phase: `installed plugin ${app_name}`,
    sleep,
  });
  let opened = false;
  if (
    operation !== "status" ||
    !await js(
      `document.body?.innerText?.includes('Refresh tools')||document.body?.innerText?.includes('Disconnect')`,
    )
  ) {
    const clicked = await js(
      `(() => {const n=${
        JSON.stringify(app_name)
      },e=[...document.querySelectorAll('button,a')].find(x=>{const t=(x.innerText||'').trim();return t===n||t.startsWith(n+'\\n')});if(!e)return false;e.click();return true;})()`,
    );
    if (!clicked) {
      throw new Error(`installed ChatGPT plugin not found: ${app_name}`);
    }
    opened = true;
  }
  if (opened || operation !== "status") {
    await waitUntilStable(
      () =>
        js(
          `document.body?.innerText?.includes('Refresh tools')||document.body?.innerText?.includes('Disconnect')`,
        ),
      Boolean,
      { timeout: 30, phase: "plugin detail controls", sleep },
    );
  }
  if (operation === "refresh-tools") {
    if (
      !await js(
        `(() => {const b=[...document.querySelectorAll('button')].find(x=>(x.innerText||'').trim()==='Refresh tools');if(!b||b.disabled)return false;b.click();return true;})()`,
      )
    ) throw new Error("Refresh tools control is unavailable");
    await sleep(500);
  }
  const state = await js(
    `(() => {const body=document.body?.innerText||'',texts=[...document.querySelectorAll('button,a')].map(e=>(e.innerText||e.getAttribute('aria-label')||'').trim()).filter(Boolean);return {connected:body.includes('Disconnect'),permissions:body.includes('Permissions'),refresh_tools:texts.includes('Refresh tools'),editable:texts.includes('Edit'),uninstallable:texts.includes('Uninstall'),url:location.href};})()`,
  );
  return { app_name, operation, ...state };
}
