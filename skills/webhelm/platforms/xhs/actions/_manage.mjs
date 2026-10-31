import { sleep } from "../../_action_helpers.mjs";
export default async function manage(
  { config: c, helpers: h, log = console.log },
) {
  const op = c.operation,
    targetId = c.note_id || "",
    targetTitle = c.title || "";
  const out = (x) => {
    log(JSON.stringify(x));
    return x;
  };
  await h.goto_url("https://creator.xiaohongshu.com/new/note-manager");
  await h.wait_for_load();
  let row = null;
  for (let i = 0; i < 20; i++) {
    await sleep(500);
    const rows = await h.js(
      `(()=>[...document.querySelectorAll('.note-card')].map(card=>{const t=card.querySelector('.note-card__title'),imp=card.dataset.impression||'';let id=null;try{id=JSON.parse(imp)?.noteTarget?.value?.noteId||null}catch{}return{title:(t?.innerText||t?.textContent||'').trim(),note_id:id,text:(card.innerText||'').trim()}}))()`,
    );
    row = rows?.find((x) =>
      targetId ? x.note_id === targetId : x.title === targetTitle
    );
    if (row) break;
  }
  if (!row) {
    return out({
      ok: false,
      operation: op,
      error: "post_not_found",
      note_id: targetId || null,
      title: targetTitle || null,
    });
  }
  if (op === "status") {
    const status = row.text.includes("审核中")
      ? "reviewing"
      : row.text.includes("未通过")
      ? "rejected"
      : row.text.includes("已发布")
      ? "published"
      : "unknown";
    return out({
      ok: true,
      operation: "status",
      note_id: row.note_id,
      title: row.title,
      status,
      status_label: status === "unknown"
        ? "unknown"
        : ({ reviewing: "审核中", rejected: "未通过", published: "已发布" })[
          status
        ],
      card_text: row.text,
    });
  }
  if (op === "update") {
    const clicked = await h.js(
      `(()=>{const c=[...document.querySelectorAll('.note-card')].find(c=>{const t=c.querySelector('.note-card__title'),im=c.dataset.impression||'';return ${
        JSON.stringify(!!targetId)
      }?im.includes(${
        JSON.stringify(targetId)
      }):(t?.textContent||'').trim()===${
        JSON.stringify(row.title)
      }});const b=c?.querySelectorAll('.note-card__action-btn')[3];if(!b)return false;b.click();return true})()`,
    );
    if (!clicked) {
      return out({ ok: false, operation: op, error: "missing-edit" });
    }
    for (let i = 0; i < 30; i++) {
      await sleep(500);
      if ((await h.page_info()).url.includes("/publish/update")) break;
    }
    const kind = await h.js(
      `(()=>{const a=[...document.querySelectorAll('input[type=file]')].map(x=>x.accept||'').join('|');return /\\.(mp4|mov|mkv|mpeg)/i.test(a)?'video':/\\.(jpg|jpeg|png|webp)/i.test(a)?'image':'unknown'})()`,
    );
    if (c.video) {
      if (kind !== "video") {
        return out({
          ok: false,
          operation: op,
          error: "media_type_mismatch_video",
        });
      }
      await h.upload_file(
        'input[type=file][accept*=".mp4"],input.upload-input',
        c.video,
      );
    }
    if (c.images) {
      if (kind !== "image") {
        return out({
          ok: false,
          operation: op,
          error: "media_type_mismatch_image",
        });
      }
      for (const image of c.images) {
        await h.upload_file(
          'input[type=file][accept*=".jpg"],input[type=file][accept*=".jpeg"],input[type=file][accept*=".png"]',
          image,
        );
      }
    }
    if (c.new_title !== undefined) {
      await h.fill_input(
        'input[placeholder="填写标题会有更多赞哦"]',
        c.new_title,
        { clear_first: true, timeout: 20 },
      );
    }
    if (c.body !== undefined) {
      await h.fill_input(".tiptap.ProseMirror,[contenteditable=true]", c.body, {
        clear_first: true,
        timeout: 20,
      });
    }
    let clickedPublish = false;
    for (let i = 0; i < 180; i++) {
      clickedPublish = await h.js(
        '(()=>{const b=[...document.querySelectorAll("button,[role=button]")].find(e=>e.offsetParent&&e.textContent.trim()==="发布"&&!e.disabled&&e.getAttribute("aria-disabled")!=="true");if(!b)return false;b.click();return true})()',
      );
      if (clickedPublish) break;
      await sleep(1000);
    }
    if (!clickedPublish) {
      return out({
        ok: false,
        operation: op,
        error: "publish_button_missing_or_disabled",
        note_id: row.note_id,
      });
    }
    for (let i = 0; i < 30; i++) {
      await sleep(1000);
      if (
        (await h.js("location.href")).includes("/publish/success") ||
        (await h.js("location.href")).includes("published=true")
      ) break;
    }
    await h.goto_url("https://creator.xiaohongshu.com/new/note-manager");
    await h.wait_for_load();
    await sleep(2000);
    const exists = await h.js(
      `(()=>[...document.querySelectorAll('.note-card')].some(c=>{const t=c.querySelector('.note-card__title'),im=c.dataset.impression||'';return ${
        JSON.stringify(!!row.note_id)
      }?im.includes(${
        JSON.stringify(row.note_id)
      }):(t?.textContent||'').trim()===${
        JSON.stringify(c.new_title || row.title)
      }}))()`,
    );
    return out({
      ok: !!exists,
      operation: op,
      note_id: row.note_id,
      old_title: row.title,
      title: c.new_title || row.title,
      media_replaced: !!(c.video || c.images),
      verified: !!exists,
    });
  }
  if (["comments", "comment", "reply"].includes(op)) {
    const profile = await h.js(
      `(()=>[...document.querySelectorAll('a[href*="/user/profile/"]')].find(a=>(a.innerText||a.textContent||'').trim()==='我')?.href||'')()`,
    );
    if (!profile) {
      return out({ ok: false, operation: op, error: "own_profile_not_found" });
    }
    await h.goto_url(profile);
    await sleep(3000);
    const detail = await h.js(
      `(()=>{const e=document.querySelector(${
        JSON.stringify(`section.note-item[data-note-id="${row.note_id}"]`)
      });return e?.querySelector('a.cover,a.title')?.href||''})()`,
    );
    if (!detail) {
      return out({
        ok: false,
        operation: op,
        error: "post_not_visible_in_my_posts",
      });
    }
    await h.goto_url(detail);
    await sleep(3000);
    if (!(await h.js('!!document.querySelector(".note-container")'))) {
      return out({ ok: false, operation: op, error: "post_detail_not_opened" });
    }
    for (let i = 0; i < 8; i++) {
      const n = await h.js(
        `(()=>{const e=[...document.querySelectorAll('.comments-el *')].filter(x=>x.offsetParent&&x.children.length===0&&(/^展开\\s*\\d+\\s*条回复$/.test(x.textContent.trim())||['展开更多回复','展开更多'].includes(x.textContent.trim())));e.slice(0,20).forEach(x=>x.click());return e.length})()`,
      );
      if (!n) break;
      await sleep(800);
    }
    const comments = await h.js(
      `(()=>[...document.querySelectorAll('.comment-item')].map((c,i)=>{const q=s=>c.querySelector(s);return{dom_index:i,comment_id:(c.id||'').replace(/^comment-/,''),author:(q('.author .name')?.textContent||'').trim(),text:(q('.content .note-text')?.textContent||'').trim(),date:(q('.date > span:first-child')?.textContent||'').trim(),location:(q('.date .location')?.textContent||'').trim(),is_reply:c.classList.contains('comment-item-sub'),reply_label:(q('.reply .count')?.textContent||'').trim(),replyable:!!q('.reply')}}))()`,
    );
    if (op === "comments") {
      return out({
        ok: true,
        operation: op,
        note_id: row.note_id,
        title: row.title,
        source: "my_posts_detail",
        detail_url: (await h.page_info()).url,
        count: (comments || []).slice(0, Number(c.limit || 50)).length,
        comments: (comments || []).slice(0, Number(c.limit || 50)),
      });
    }
    let target;
    if (op === "comment") {
      await h.js(
        'document.querySelector(".content-edit .inner-when-not-active, .content-edit .inner")?.click()',
      );
    } else {
      target = c.comment_id
        ? comments.find((x) => x.comment_id === c.comment_id)
        : c.comment_index !== undefined
        ? comments[Number(c.comment_index)]
        : comments.filter((x) => (x.text || "").includes(c.contains || ""))[0];
      if (!target) {
        return out({ ok: false, operation: op, error: "comment_not_found" });
      }
      if (!target.replyable) {
        return out({
          ok: false,
          operation: op,
          error: "comment_not_replyable",
          comment: target,
        });
      }
      await h.js(
        `document.getElementById(${
          JSON.stringify("comment-" + target.comment_id)
        })?.querySelector('.reply')?.click()`,
      );
    }
    await sleep(400);
    if (
      !(await h.js(
        '!!document.querySelector("p.content-input[contenteditable=true]")',
      ))
    ) return out({ ok: false, operation: op, error: "comment_editor_missing" });
    await h.type_text(c.text);
    if (
      !(await h.js(
        '(()=>{const b=document.querySelector("button.btn.submit,button.submit");if(!b||b.disabled)return false;b.click();return true})()',
      ))
    ) {
      return out({
        ok: false,
        operation: op,
        error: "comment_submit_missing_or_disabled",
      });
    }
    await sleep(1500);
    const verified = await h.js(
      `[...document.querySelectorAll('.comment-item .content .note-text')].some(e=>e.textContent.trim()===${
        JSON.stringify(c.text)
      })`,
    );
    return out({
      ok: !!verified,
      operation: op,
      note_id: row.note_id,
      title: row.title,
      text: c.text,
      verified: !!verified,
      ...(target ? { replied_to: target } : {}),
    });
  }
  return out({ ok: false, error: "unsupported_operation", operation: op });
}
