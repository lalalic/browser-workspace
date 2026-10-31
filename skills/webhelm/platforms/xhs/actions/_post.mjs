import { sleep } from "../../_action_helpers.mjs";
export default async function post(
  { config: c, helpers: h, log = console.log },
) {
  const mode = c.mode || "image",
    images = c.images || [c.image || ""],
    video = c.video || "",
    tags = c.tags || [],
    collection = (c.collection || "").trim();
  const open = async (url) => {
    const t = await h.current_tab();
    if ((t.url || "").includes("xiaohongshu.com")) {
      if (t.url !== url) await h.goto_url(url);
    } else await h.new_tab(url);
  };
  await open("https://creator.xiaohongshu.com/publish/publish");
  await h.wait_for_load();
  await sleep(3000);
  if ((await h.page_info()).url.includes("login")) {
    throw new Error("Not logged in. Log in at creator.xiaohongshu.com first.");
  }
  if (mode === "video") {
    if (
      !(await h.wait_for_element(".upload-input,input[type=file]", {
        timeout: 10,
        visible: true,
      }))
    ) throw new Error("XHS video upload input missing");
    try {
      await h.upload_file(
        ".upload-input,input[type=file][accept*=video],input[type=file]",
        video,
      );
    } catch {
      const s = await h.cdp("DOM.performSearch", {
        query: 'input[type="file"]',
      });
      if (!s.resultCount) {
        throw new Error("Cannot find file input for video upload.");
      }
      const n = await h.cdp("DOM.getSearchResults", {
        searchId: s.searchId,
        fromIndex: 0,
        toIndex: 1,
      });
      await h.cdp("DOM.setFileInputFiles", {
        files: [video],
        nodeId: n.nodeIds[0],
      });
      await h.cdp("DOM.discardSearchResults", { searchId: s.searchId });
    }
    let ready = false;
    for (let i = 0; i < 180; i++) {
      await sleep(1000);
      const state = await h.js(
        '(()=>{const t=document.body.innerText||"";if(/上传中\\s*\\d*%?/.test(t)||t.includes("取消上传"))return"uploading";if(t.includes("重新上传")||t.includes("检测为高清视频"))return"ready";return"waiting"})()',
      );
      if (state === "ready") {
        ready = true;
        break;
      }
    }
    if (!ready) {
      throw new Error("video upload never reached the editor-ready state");
    }
  } else {
    await h.js(
      '(()=>{const t=document.querySelectorAll(".creator-tab-item,.tab-item,[class*=publishTypeTabs] span,[class*=publish-type] span");if(t.length>=2)t[1].click();else [...document.querySelectorAll("span")].find(x=>x.textContent.includes("图文"))?.click()})()',
    );
    await sleep(2000);
    if (!(await h.js('!!document.querySelector(".upload-input")'))) {
      await h.js(
        '[...document.querySelectorAll("span,div,a")].find(x=>x.textContent.includes("图文")&&x.offsetWidth>0)?.click()',
      );
    }
    await sleep(1000);
    await h.upload_file(".upload-input", images[0]);
    await sleep(4000);
    for (const image of images.slice(1)) {
      await h.upload_file(
        ".add-upload,.upload-more,.add-btn,[class*=addImage] input[type=file],.upload-input",
        image,
      );
      await sleep(3000);
    }
  }
  const title = c.title;
  if (!title) throw new TypeError("title is required");
  const ok = await h.js(
    `(()=>{const e=document.querySelector('input[placeholder="填写标题会有更多赞哦"],.c-input_inner input,input[placeholder]');if(!e)return false;Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,${
      JSON.stringify(title)
    });e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));return true})()`,
  );
  if (!ok) throw new Error("title input not found");
  const body = (c.body || "") +
    (tags.length ? " " + tags.map((t) => "#" + t).join(" ") : "");
  if (
    !(await h.js(
      '(()=>{const e=document.querySelector(".tiptap.ProseMirror,#post-textarea,.ql-editor,[contenteditable=true]");if(!e)return false;e.focus();e.click();return true})()',
    ))
  ) throw new Error("body editor not found");
  await h.type_text(body);
  if (collection) {
    if (
      !(await h.js(
        '[...document.querySelectorAll("*")].find(e=>e.children.length===0&&e.textContent.trim()==="选择合集")?.click(),true',
      ))
    ) throw new Error("collection chooser not found");
    await sleep(500);
    const selected = await h.js(
      `(()=>{const e=[...document.querySelectorAll('*')].find(x=>x.offsetParent&&x.children.length===0&&x.textContent.trim()===${
        JSON.stringify(collection)
      });if(e){e.click();return'selected'}return'absent'})()`,
    );
    if (selected === "absent") {
      await h.js(
        '[...document.querySelectorAll("button,*")].find(e=>e.offsetParent&&e.children.length===0&&e.textContent.trim()==="创建合集")?.click()',
      );
      await sleep(500);
      await h.fill_input(
        'input[placeholder="好的合集名称能吸引更多用户"]',
        collection,
        { clear_first: true, timeout: 20 },
      );
      if (c.collection_description) {
        await h.fill_input(
          'input[placeholder="简单介绍你的合集"],textarea[placeholder="简单介绍你的合集"]',
          c.collection_description,
          { clear_first: true, timeout: 20 },
        );
      }
      if (
        !(await h.js(
          '(()=>{const b=[...document.querySelectorAll("button")].find(e=>e.offsetParent&&e.textContent.trim()==="创建并加入"&&!e.disabled);if(b){b.click();return true}return false})()',
        ))
      ) throw new Error("create-and-join collection control unavailable");
      let joined = false;
      for (let i = 0; i < 20; i++) {
        await sleep(500);
        joined = !!(await h.js(
          `document.body.innerText.includes(${
            JSON.stringify(collection)
          })&&!document.body.innerText.includes('创建并加入')`,
        ));
        if (joined) break;
      }
      if (!joined) throw new Error("collection creation was not verified");
    }
  }
  await h.capture_screenshot();
  const publishing = c.action === "publish";
  if (publishing) {
    let clicked = false;
    for (let i = 0; i < 180; i++) {
      const state = await h.js(
        '(()=>{const b=[...document.querySelectorAll("button,[role=button]")].find(x=>x.offsetParent&&x.textContent.trim()==="发布")||document.querySelector(".publishBtn,.publish-btn,button.css-k01wfk,[class*=submit]");if(!b)return"missing";if(b.disabled||b.getAttribute("aria-disabled")==="true"||b.classList.contains("disabled"))return"disabled";b.click();return"clicked"})()',
      );
      if (state === "clicked") {
        clicked = true;
        break;
      }
      await sleep(1000);
    }
    if (!clicked) {
      throw new Error(
        "publish button not found; inspect creator manager before retrying",
      );
    }
    let redirect = false;
    for (let i = 0; i < 20; i++) {
      await sleep(1000);
      redirect = await h.js(
        'location.href.includes("publish/success")||/发布成功|成功发布/.test(document.body.innerText||"")',
      );
      if (redirect) break;
    }
    await h.goto_url("https://creator.xiaohongshu.com/new/note-manager");
    await h.wait_for_load();
    let row = null;
    for (let i = 0; i < 30; i++) {
      await sleep(500);
      const raw = await h.js(
        `(()=>[...document.querySelectorAll('.note-card')].map(c=>{const t=c.querySelector('.note-card__title'),imp=c.dataset.impression||'';return{title:(t?.innerText||t?.textContent||'').trim(),text:(c.innerText||'').trim(),impression:imp}}).filter(x=>x.title===${
          JSON.stringify(title)
        }))()`,
      );
      if (raw?.length) {
        row = raw[0];
        break;
      }
    }
    if (!row) {
      await h.capture_screenshot();
      throw new Error("publish was not verified in creator manager");
    }
    let noteId = null;
    try {
      noteId = JSON.parse(row.impression)?.noteTarget?.value?.noteId || null;
    } catch {}
    if (!noteId) {
      throw new Error(
        "creator manager row found but stable note ID was not available",
      );
    }
    const status = row.text.includes("审核中")
      ? "reviewing"
      : row.text.includes("未通过")
      ? "rejected"
      : "published";
    const receipt = {
      note_id: noteId,
      title,
      status,
      duplicate_count: 1,
      card_text: row.text,
      redirect_verified: !!redirect,
      collection: collection || null,
    };
    log("XHS_RECEIPT " + JSON.stringify(receipt));
    if (!["published", "reviewing"].includes(status)) {
      throw new Error("creator manager reports " + status);
    }
    await h.capture_screenshot();
    return receipt;
  }
  await h.js(
    '([...document.querySelectorAll("button")].find(b=>b.textContent.includes("暂存"))||{}).click()',
  );
  await sleep(3000);
  await h.capture_screenshot();
  log("Done! Post saved as draft.");
  return { status: "draft", title };
}
