import { sleep } from "../../_action_helpers.mjs";
export default async function post(
  { config: c, helpers: h, log = console.log },
) {
  let step = 0;
  const total = 7 + (c.tags?.length ? 1 : 0) + (c.thumbnail ? 1 : 0),
    next = (s) => log(`[${++step}/${total}] ${s}`);
  const clickBtn = async (text) => {
    for (let i = 0; i < 5; i++) {
      if (
        await h.js(
          `(()=>{const b=[...document.querySelectorAll('ytcp-button')].find(x=>x.textContent.trim()===${
            JSON.stringify(text)
          }&&!x.disabled);if(!b)return false;b.click();return true})()`,
        )
      ) return true;
      await sleep(1000);
    }
    return false;
  };
  next("Opening YouTube Studio upload...");
  await h.new_tab("https://www.youtube.com/upload");
  await h.wait_for_load();
  await sleep(3000);
  if ((await h.page_info()).url.includes("accounts.google.com")) {
    throw new Error("Not logged in");
  }
  next("Uploading video...");
  await h.upload_file("input[type=file]", c.video);
  await sleep(5000);
  next("Waiting for processing...");
  await sleep(3000);
  next("Setting title: " + c.title);
  await h.js(
    `(()=>{const b=document.querySelectorAll('#textbox')[0];if(!b)return false;b.textContent=${
      JSON.stringify(c.title)
    };b.dispatchEvent(new Event('input',{bubbles:true}));return true})()`,
  );
  await sleep(500);
  next("Setting description...");
  await h.js(
    `(()=>{const b=document.querySelectorAll('#textbox')[1];if(!b)return false;b.textContent=${
      JSON.stringify(c.desc || "")
    };b.dispatchEvent(new Event('input',{bubbles:true}));return true})()`,
  );
  await sleep(500);
  if (c.thumbnail) {
    next("Uploading thumbnail...");
    await h.js(
      'document.querySelector("#still-picker ytcp-button,#upload-prompt")?.click()',
    );
    await sleep(1000);
    await h.upload_file(
      "#file-loader input[type=file],input[accept*=image]",
      c.thumbnail,
    );
    await sleep(3000);
  }
  if (c.tags?.length) {
    next("Adding tags: " + c.tags.join(", "));
    await h.js(
      'document.querySelector("#toggle-button ytcp-button,ytcp-button#toggle-button")?.click()',
    );
    await sleep(1000);
    const tagstr = c.tags.join(",");
    await h.js(
      `(()=>{const i=document.querySelector('input.tags-input,input[aria-label*=Tag],input[placeholder*=Tag]');if(i){const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;set.call(i,${
        JSON.stringify(tagstr)
      });i.dispatchEvent(new Event('input',{bubbles:true}));i.dispatchEvent(new Event('change',{bubbles:true}))}})()`,
    );
    await sleep(500);
  }
  next(
    "Setting audience" + (c.made_for_kids ? " (MADE FOR KIDS)" : "") +
      " + advancing wizard...",
  );
  if (c.made_for_kids) {
    await h.js(
      'document.querySelector("tp-yt-paper-radio-button[name=VIDEO_MADE_FOR_KIDS_MFK]")?.click()',
    );
  } else {await h.js(
      'document.querySelector(".made-for-kids-group")?.querySelectorAll("tp-yt-paper-radio-button")[1]?.click()',
    );}
  await sleep(1000);
  for (const s of ["Video elements", "Initial check", "Visibility"]) {
    log("  -> " + s);
    if (!(await clickBtn("Next"))) {
      throw new Error("YouTube Next button was not found");
    }
    await sleep(2000);
  }
  const vis = c.vis || c.visibility || "PRIVATE";
  next("Setting visibility to " + vis + " and saving...");
  for (let i = 0; i < 5; i++) {
    if (
      await h.js(
        `(()=>{const e=document.querySelector(${
          JSON.stringify(`[name=${vis}]`)
        });if(!e)return false;e.click();return true})()`,
      )
    ) {
      await sleep(1000);
      break;
    }
    await sleep(1000);
  }
  if (!(await clickBtn("Save"))) {
    throw new Error("YouTube Save button was not found");
  }
  await sleep(5000);
  await h.capture_screenshot();
  log("Done! Video saved as " + vis + ".");
  return { status: "submitted", visibility: vis };
}
