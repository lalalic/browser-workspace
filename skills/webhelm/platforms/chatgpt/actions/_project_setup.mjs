import {
  COMPOSER_JS,
  pathThreadId,
  setField,
  sleep,
  waitUntilStable,
} from "./_action-common.mjs";
const projectId = (url) =>
  String(url || "").match(/\/g\/(g-p-[A-Za-z0-9]{32})/)?.[1] || null;
const fire =
  `const fire=e=>{for(const type of ['pointerdown','mousedown','pointerup','mouseup','click'])e.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,button:0,buttons:type.includes('down')?1:0}));};`;
export async function run({ helpers: h, config: c = {} }) {
  const name = String(c.project_name || "").trim(),
    instructions = String(c.instructions || "").trim();
  if (!name) throw new Error("project_name is required");
  if (!instructions) throw new Error("Project Instructions are empty");
  await h.new_tab("https://chatgpt.com/");
  await h.wait_for_load();
  const norm = (s) => String(s || "").replace(/\s+/g, " ").trim();
  await waitUntilStable(
    () =>
      h.js(
        `(() => {const rows=document.querySelectorAll('[data-app-action-sidebar-project-row]');if(rows.length)return 'rows';const add=[...document.querySelectorAll('button,[role="button"]')].find(e=>(e.getAttribute('aria-label')||'').toLowerCase().includes('add new project'));if(add)return 'add';const show=[...document.querySelectorAll('button,[role="button"]')].find(e=>(e.getAttribute('aria-label')||'').toLowerCase()==='show sidebar');if(show){show.click();return 'opening'}return '';})()`,
      ),
    Boolean,
    { timeout: 20000, phase: "ChatGPT Projects sidebar", sleep },
  );
  const readExisting = () =>
    h.js(
      `(() => {const wanted=${
        JSON.stringify(norm(name).toLowerCase())
      };const row=[...document.querySelectorAll('[data-app-action-sidebar-project-row]')].find(e=>(e.getAttribute('data-app-action-sidebar-project-label')||'').replace(/\\s+/g,' ').trim().toLowerCase()===wanted);return row?{projectId:row.getAttribute('data-app-action-sidebar-project-id')||'',label:row.getAttribute('data-app-action-sidebar-project-label')||''}:null;})()`,
    );
  let existing = null;
  const existingDeadline = Date.now() + 10000;
  while (Date.now() < existingDeadline) {
    existing = await readExisting();
    if (existing?.projectId) break;
    await sleep(200);
  }
  let project;
  if (existing?.projectId) {
    const url = `https://chatgpt.com/g/${existing.projectId}/project`;
    await h.goto_url(url);
    await h.wait_for_load();
    project = {
      project_id: existing.projectId,
      project_url: (await h.page_info()).url || url,
      reused: true,
    };
  } else {
    const legacy = await h.js(
      `(() => [...document.querySelectorAll('a[href]')].map(a=>({text:(a.innerText||a.textContent||'').replace(/\\s+/g,' ').trim(),href:new URL(a.getAttribute('href'),location.origin).href})).find(x=>x.text.toLowerCase()===${
        JSON.stringify(norm(name).toLowerCase())
      }&&x.href.includes('/g/g-p-'))||null)()`,
    );
    if (legacy) {
      const pid = new URL(legacy.href).pathname.split("/").find((part) =>
          part.startsWith("g-p-")
        ),
        url = pid ? `https://chatgpt.com/g/${pid}/project` : legacy.href;
      await h.goto_url(url);
      await h.wait_for_load();
      project = {
        project_id: pid,
        project_url: (await h.page_info()).url || url,
        reused: true,
      };
    } else {
      const clicked = await h.js(
        `(() => {const b=[...document.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'').toLowerCase().includes('add new project'));if(b){b.click();return true;}const e=[...document.querySelectorAll('button,a,[role="button"]')].find(x=>/new project|create project/i.test((x.innerText||x.textContent||x.getAttribute('aria-label')||'').replace(/\\s+/g,' ').trim()));if(!e)return false;e.click();return true;})()`,
      );
      if (!clicked) {
        throw new Error(
          `ChatGPT New Project control was not found for ${name}`,
        );
      }
      const input = await waitUntilStable(
        () =>
          h.js(
            `(() => {const vis=e=>{const r=e.getBoundingClientRect();return r.width&&r.height};const xs=[...document.querySelectorAll('input[type="text"],input:not([type]),textarea')],e=xs.find(e=>vis(e)&&/project name|copenhagen trip/i.test((e.getAttribute('aria-label')||'')+' '+(e.getAttribute('placeholder')||'')))||xs.find(vis);if(!e)return null;e.setAttribute('data-neoy-project-name','1');return '[data-neoy-project-name="1"]';})()`,
          ),
        Boolean,
        { timeout: 15, phase: "ChatGPT project name field", sleep },
      );
      await h.fill_input(input, name, { clear_first: true });
      await h.js(
        `(() => {${fire}const b=[...document.querySelectorAll('button,[role="button"]')].find(e=>e.getBoundingClientRect().width&&/default memory/i.test(e.innerText||e.textContent||e.getAttribute('aria-label')||''));if(b)fire(b);return !!b;})()`,
      );
      await sleep(150);
      await h.js(
        `(() => {${fire}const e=[...document.querySelectorAll('[role="menuitem"],button,[role="button"],label')].find(e=>/project[- ]only/i.test((e.innerText||e.textContent||e.getAttribute('aria-label')||'').replace(/\\s+/g,' ').trim()));if(e)fire(e);return !!e;})()`,
      );
      if (
        !await h.js(
          `(() => {const es=[...document.querySelectorAll('button,[role="button"]')].filter(e=>e.getBoundingClientRect().width&&e.getBoundingClientRect().height),b=es.find(e=>['create project','create','continue','done'].includes((e.innerText||e.textContent||e.getAttribute('aria-label')||'').replace(/\\s+/g,' ').trim().toLowerCase()));if(!b||b.disabled||b.getAttribute('aria-disabled')==='true')return false;b.click();return true;})()`,
        )
      ) throw new Error("ChatGPT Create Project button not found");
      const end = Date.now() + 30000;
      let pid = null;
      while (Date.now() < end) {
        pid = projectId((await h.page_info()).url);
        if (!pid) {
          pid = await h.js(
            `(() => {const n=${
              JSON.stringify(norm(name).toLowerCase())
            };const e=[...document.querySelectorAll('[data-app-action-sidebar-project-row]')].find(x=>(x.getAttribute('data-app-action-sidebar-project-label')||'').replace(/\\s+/g,' ').trim().toLowerCase()===n);return e?.getAttribute('data-app-action-sidebar-project-id')||null;})()`,
          );
        }
        if (pid) break;
        await sleep(250);
      }
      if (!pid) throw new Error(`ChatGPT Project ${name} was not created`);
      const url = `https://chatgpt.com/g/${pid}/project`;
      if (!new URL((await h.page_info()).url).pathname.includes("/project")) {
        await h.goto_url(url);
        await h.wait_for_load();
      }
      project = {
        project_id: pid,
        project_url: (await h.page_info()).url || url,
        reused: false,
      };
    }
  }
  const openSettings = async () => {
    if (
      await h.js(
        `(() => {const d=document.querySelector('[role="dialog"]');return !!d&&/project settings/i.test(d.innerText||d.textContent||'');})()`,
      )
    ) return;
    await waitUntilStable(
      () =>
        h.js(
          `(() => {${fire}const b=[...document.querySelectorAll('button')].find(x=>x.getAttribute('aria-label')==='Project actions');if(!b)return false;fire(b);return true;})()`,
        ),
      Boolean,
      { timeout: 15000, phase: "ChatGPT Project actions control", sleep },
    );
    await waitUntilStable(
      () =>
        h.js(
          `(() => {${fire}const es=[...document.querySelectorAll('[role="menuitem"],button,[role="button"],a')],e=es.find(x=>/project settings|edit project|project instructions/i.test((x.innerText||x.textContent||x.getAttribute('aria-label')||'').replace(/\\s+/g,' ').trim().toLowerCase()));if(e){fire(e);return true}return false;})()`,
        ),
      Boolean,
      { timeout: 8000, phase: "ChatGPT Project settings menu item", sleep },
    );
    await waitUntilStable(
      () =>
        h.js(
          `(() => {const d=document.querySelector('[role="dialog"]');return !!d&&/project settings/i.test(d.innerText||d.textContent||'');})()`,
        ),
      Boolean,
      { timeout: 5000, phase: "ChatGPT Project settings dialog", sleep },
    );
  };
  await openSettings();
  const field = await waitUntilStable(
    () =>
      h.js(
        `(() => {const d=document.querySelector('[role="dialog"]');if(!d||!/project settings/i.test(d.innerText||d.textContent||''))return null;const e=d.querySelector('textarea');if(!e)return null;e.setAttribute('data-neoy-project-instructions','1');return '[data-neoy-project-instructions="1"]';})()`,
      ),
    Boolean,
    { timeout: 15000, phase: "ChatGPT Project Instructions field", sleep },
  );
  await setField(h, field, instructions);
  await sleep(1000);
  let memory = await h.js(
    `(() => {const d=document.querySelector('[role="dialog"]');if(!d)return 'missing';const t=(d.innerText||d.textContent||'').replace(/\\s+/g,' ').toLowerCase();if(t.includes('project-only'))return 'project-only';const e=[...d.querySelectorAll('button,[role="button"]')].find(x=>/default memory|memory/i.test(x.innerText||x.textContent||x.getAttribute('aria-label')||''));if(!e)return 'unavailable';${fire}fire(e);return 'opened';})()`,
  );
  if (memory === "opened") {
    await waitUntilStable(
      () =>
        h.js(
          `(() => {${fire}const e=[...document.querySelectorAll('[role="menuitem"],button,[role="button"],label')].find(x=>/project[- ]only/i.test((x.innerText||x.textContent||x.getAttribute('aria-label')||'').replace(/\\s+/g,' ').trim()));if(e){fire(e);return true}return false;})()`,
        ),
      Boolean,
      { timeout: 3000, phase: "Project-only memory option", sleep },
    );
    await sleep(700);
    memory = "project-only";
  }
  await h.js(
    `(() => {const d=document.querySelector('[role="dialog"]');if(!d)return true;const b=[...d.querySelectorAll('button,[role="button"]')].find(x=>x.getAttribute('aria-label')==='Close dialog'||/close dialog/i.test(x.innerText||x.textContent||''));if(b){${fire}fire(b);return true}return false;})()`,
  );
  const url = project.project_url;
  if (!(new URL((await h.page_info()).url).pathname.includes("/project"))) {
    await h.goto_url(url);
    await h.wait_for_load();
  }
  const initial = String(c.initial_prompt || "").trim() ||
    "Initialize this learner's Family Tutor thread from the Project Instructions and reply only with READY.";
  const selector = await waitUntilStable(() => h.js(COMPOSER_JS), Boolean, {
    timeout: 30,
    phase: "ChatGPT Project composer",
    sleep,
  });
  await h.fill_input(selector, initial, { clear_first: true });
  if (
    !await h.js(
      `(() => {const b=document.querySelector('button[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="Send"],form button[type="submit"]');if(!b||b.disabled||b.getAttribute('aria-disabled')==='true')return false;b.click();return true;})()`,
    )
  ) throw new Error("Initial Project thread Send failed");
  const end = Date.now() + 90000;
  let threadUrl = "";
  while (Date.now() < end) {
    threadUrl = (await h.page_info()).url || "";
    if (pathThreadId(threadUrl) && !threadUrl.includes("local-chatgpt")) {
      const assistant = await h.js(
        `(() => [...document.querySelectorAll('h4')].some(e=>(e.innerText||'').trim()==='ChatGPT said:')||!!document.querySelector('[data-message-author-role="assistant"]'))()`,
      );
      if (assistant) break;
    }
    await sleep(250);
  }
  if (!pathThreadId(threadUrl) || threadUrl.includes("local-chatgpt")) {
    throw new Error(
      "ChatGPT Project thread stayed on a temporary local-chatgpt URL",
    );
  }
  return {
    status: "completed",
    project_id: project.project_id,
    project_url: project.project_url,
    project_reused: project.reused,
    memory,
    thread_url: threadUrl.split("?")[0],
    thread_id: pathThreadId(threadUrl),
    target_id: h.target_id || h.targetId,
  };
}
