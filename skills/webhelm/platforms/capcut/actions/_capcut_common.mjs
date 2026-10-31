export async function selectMediaType(mediaType, { js, wait_for_element }) {
  if (!["image", "video"].includes(mediaType)) {
    throw new TypeError("media_type must be 'image' or 'video'");
  }
  const mode = mediaType[0].toUpperCase() + mediaType.slice(1);
  if (
    !(await js(
      "(()=>Array.from(document.querySelectorAll('button[aria-label]')).some(x=>['Image','Video'].includes((x.getAttribute('aria-label')||'').trim())))()",
    ))
  ) throw new Error("CapCut media mode selector was not found");
  await js(
    "(()=>{const b=Array.from(document.querySelectorAll('button[aria-label]')).find(x=>['Image','Video'].includes((x.getAttribute('aria-label')||'').trim()));if(b.getAttribute('aria-expanded')!=='true')b.click();return true})()",
  );
  if (
    !(await wait_for_element('[role="menuitemradio"]', {
      timeout: 5,
      visible: true,
    }))
  ) throw new Error("CapCut media mode menu did not open");
  if (
    !(await js(
      `(()=>{const e=Array.from(document.querySelectorAll('[role=menuitemradio]')).find(x=>x.textContent.trim()===${
        JSON.stringify(mode)
      });if(!e)return false;e.click();return true})()`,
    ))
  ) throw new Error(`CapCut ${mode} mode option was not found`);
  if (
    !(await wait_for_element(`button[aria-label*="${mode}"]`, {
      timeout: 5,
      visible: true,
    }))
  ) throw new Error(`CapCut did not switch to ${mode} mode`);
}
export async function setModelPickerOpen(isOpen, { js, wait_for_element }) {
  const find =
    "Array.from(document.querySelectorAll('button[aria-expanded]')).find(x=>/^(Seedance|Seedream|GPT Image|Nano Banana)/i.test((x.getAttribute('aria-label')||x.innerText).trim()))";
  if (!(await js(`(()=>!!${find})()`))) {
    throw new Error("CapCut model picker was not found");
  }
  await js(
    `(()=>{const b=${find};if(b&&(b.getAttribute('aria-expanded')==='true')!==${
      JSON.stringify(isOpen)
    })b.click();return true})()`,
  );
  if (
    isOpen &&
    !(await wait_for_element('[role="listbox"][aria-label="Model"]', {
      timeout: 5,
      visible: true,
    }))
  ) throw new Error("CapCut model list did not open");
}
export async function modelOptions({ js }) {
  return await js(
    `(()=>{const l=document.querySelector('[role=listbox][aria-label="Model"]');if(!l)return [];return Array.from(l.querySelectorAll('[role=option]')).map(e=>({name:(e.querySelector('[title]')||e).getAttribute('title')||e.innerText.trim().split('\\n')[0],key:e.getAttribute('data-model-key')}))})()`,
  ) || [];
}
export async function availableModels(mediaType, deps) {
  await selectMediaType(mediaType, deps);
  await setModelPickerOpen(true, deps);
  const options = await modelOptions(deps);
  await setModelPickerOpen(false, deps);
  if (!options.length) {
    throw new Error(`No CapCut models were found for ${mediaType}`);
  }
  return options;
}
export async function selectModel(model, deps) {
  await setModelPickerOpen(true, deps);
  const options = await modelOptions(deps);
  const matches = options.filter((x) =>
    x.name.toLowerCase() === model.toLowerCase()
  );
  if (matches.length !== 1) {
    await setModelPickerOpen(false, deps);
    throw new TypeError(
      `Model ${JSON.stringify(model)} is not available. Available models: ${
        options.map((x) => x.name).join(", ") || "none"
      }`,
    );
  }
  const ok = await deps.js(
    `(()=>{const l=document.querySelector('[role=listbox][aria-label="Model"]');if(!l)return false;const e=Array.from(l.querySelectorAll('[role=option]')).find(x=>x.getAttribute('data-model-key')===${
      JSON.stringify(matches[0].key)
    });if(!e)return false;e.click();return true})()`,
  );
  if (!ok) {
    throw new Error(`Could not select CapCut model ${JSON.stringify(model)}`);
  }
  await setModelPickerOpen(false, deps);
  return matches[0].name;
}
