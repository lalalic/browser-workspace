import { readFile } from "node:fs/promises";
import { inflateRawSync } from "node:zlib";
import { sleep } from "../../_action_helpers.mjs";
const STATES = new Set([
  "draft",
  "submitted",
  "pending",
  "rejected",
  "published",
  "unknown",
]);
async function updateListing(c, h, evidence, fail) {
  const market = c.market_package || {},
    required = [
      "title",
      "short_description",
      "long_description",
      "support_url",
    ];
  const missing = required.filter((k) => !String(market[k] || "").trim());
  if (missing.length) {
    return fail("market_package missing: " + missing.join(", "));
  }
  if (!c.commit) {
    return evidence("draft", {
      dry_run: true,
      fields: Object.keys(market).sort(),
    });
  }
  const aliases = {
    short_description: ["short description", "summary"],
    long_description: ["long description", "description"],
    release_notes: ["release notes", "what's new"],
    reviewer_test_instructions: ["reviewer", "test instructions"],
    support_url: ["support url", "support website"],
    privacy_policy_url: ["privacy policy", "privacy url"],
    privacy_practices: ["privacy practices", "privacy"],
    data_use: ["data use", "data usage"],
    distribution: ["distribution", "visibility"],
    payment: ["payment", "paid"],
    permissions: ["permissions", "permission justification"],
    host_permissions: ["host permissions", "host permission"],
    host_permission_justifications: [
      "host permission justification",
      "host permissions",
    ],
    title: ["title", "name"],
  };
  const skip = new Set([
    "screenshots",
    "posters",
    "feature_graphic",
    "promotional_graphic",
    "demo_video",
  ]);
  for (const [key, value] of Object.entries(market)) {
    if (
      value === null || value === "" || Array.isArray(value) && !value.length ||
      skip.has(key)
    ) continue;
    const keys = aliases[key] || [key.replaceAll("_", " ")];
    const selector = await h.js(
      `(()=>{const keys=${
        JSON.stringify(keys.map((x) => x.toLowerCase()))
      },controls=[...document.querySelectorAll('input,textarea,select,[role=combobox],[contenteditable=true]')],label=n=>{const ids=(n.getAttribute('aria-labelledby')||'').split(/\\s+/).filter(Boolean),labelled=ids.map(id=>document.getElementById(id)?.innerText||'').join(' '),explicit=n.id?document.querySelector('label[for="'+CSS.escape(n.id)+'"]')?.innerText||'':'',parent=n.closest('label')?.innerText||n.parentElement?.innerText||'';return[n.getAttribute('aria-label'),n.getAttribute('placeholder'),n.name,n.id,labelled,explicit,parent].filter(Boolean).join(' ').toLowerCase()},n=controls.find(n=>keys.some(k=>label(n).includes(k)));return n?.id?'#'+CSS.escape(n.id):null})()`,
    );
    if (!selector && ["title", "short_description"].includes(key)) continue;
    if (!selector) return fail(`listing field not observed: ${key}`);
    const changed = await h.js(
      `(()=>{const n=document.querySelector(${
        JSON.stringify(selector)
      });if(!n)return false;n.focus();const v=${
        JSON.stringify(value)
      };if(n.type==='checkbox'||n.type==='radio')n.checked=Boolean(v);else if(n.tagName==='SELECT'){const o=[...n.options].find(x=>(x.text||x.value).toLowerCase()===String(v).toLowerCase());if(!o)return false;n.value=o.value}else if('value'in n)n.value=String(v);else n.textContent=String(v);n.dispatchEvent(new Event('input',{bubbles:true}));n.dispatchEvent(new Event('change',{bubbles:true}));return true})()`,
    );
    if (changed !== true) return fail(`listing field not observed: ${key}`);
  }
  for (const key of skip) {
    for (
      const media of (Array.isArray(market[key]) ? market[key] : [market[key]])
    ) if (media) await h.upload_file("input[type=file]", String(media));
  }
  // Avoid saving if any labeled edit could not be mapped. Save is an external draft mutation.
  if (
    !(await h.js(
      `(()=>{const a=['Save draft','Save'];const b=[...document.querySelectorAll('button,[role=button]')].find(x=>a.includes((x.innerText||'').trim()));if(!b)return false;b.click();return true})()`,
    ))
  ) return fail("save control not observed");
  return evidence("draft", { fields: Object.keys(market).sort() });
}
function packageVersion(bytes) {
  const b = Buffer.from(bytes);
  for (let i = b.length - 22; i >= Math.max(0, b.length - 65557); i--) {
    if (b.readUInt32LE(i) === 0x06054b50) {
      const count = b.readUInt16LE(i + 10);
      let p = b.readUInt32LE(i + 16);
      for (let n = 0; n < count; n++) {
        if (b.readUInt32LE(p) !== 0x02014b50) break;
        const method = b.readUInt16LE(p + 10),
          size = b.readUInt32LE(p + 20),
          nameLen = b.readUInt16LE(p + 28),
          extra = b.readUInt16LE(p + 30),
          comment = b.readUInt16LE(p + 32),
          off = b.readUInt32LE(p + 42),
          name = b.toString("utf8", p + 46, p + 46 + nameLen);
        if (name === "manifest.json") {
          const localName = b.readUInt16LE(off + 26),
            localExtra = b.readUInt16LE(off + 28),
            start = off + 30 + localName + localExtra,
            compressed = b.subarray(start, start + size),
            json = JSON.parse(
              (method === 0 ? compressed : inflateRawSync(compressed)).toString(
                "utf8",
              ),
            );
          if (!json.version) throw Error("package manifest is missing version");
          return String(json.version);
        }
        p += 46 + nameLen + extra + comment;
      }
    }
  }
  throw Error("invalid extension package: manifest.json not found");
}
export default async function chromeWebStore(
  { config: c, helpers: h, log = console.log },
) {
  let action = c.action,
    itemId = (c.item_id || "").trim(),
    name = (c.product_name || "").trim(),
    expected = (c.expected_version || "").trim();
  const fail = (error) => {
    const result = { action, status: "unknown", error };
    log(JSON.stringify(result));
    const e = new Error(error);
    e.result = result;
    throw e;
  };
  const page = () => h.page_info();
  const js = h.js;
  const textExists = async (needles) =>
    js(
      `(()=>{const t=(document.body?.innerText||'').toLowerCase();return ${
        JSON.stringify(needles.map((x) => x.toLowerCase()))
      }.some(x=>t.includes(x))})()`,
    );
  const evidence = async (status, extra = {}) => {
    if (!STATES.has(status)) return fail("invalid evidence status: " + status);
    const r = {
      action,
      status,
      item_id: itemId || null,
      url: (await page()).url,
      ...extra,
    };
    log(JSON.stringify(r));
    return r;
  };
  const clickText = async (label) =>
    js(
      `(()=>{const q=${
        JSON.stringify(label.toLowerCase())
      },n=[...document.querySelectorAll('button,[role=button],a')].find(e=>{const t=(e.innerText||e.getAttribute('aria-label')||'').trim().toLowerCase();return t===q||t.includes(q)});if(!n)return false;n.click();return true})()`,
    );
  const version = async () => {
    const text = await js('document.body?.innerText||""') || "";
    const v = text.match(/\b\d+\.\d+(?:\.\d+){1,2}\b/g) || [];
    return expected && v.includes(expected) ? expected : v[0] || null;
  };
  const login = async () => {
    if (
      (await page()).url.includes("accounts.google.com") ||
      await textExists(["sign in", "log in"])
    ) return fail("authenticated Chrome Web Store publisher login required");
  };
  const publisher = (url) =>
    (url.match(
      /https:\/\/(?:chrome\.google\.com\/webstore\/devconsole|chromewebstore\.google\.com\/devconsole)\/([^/]+)/,
    ) || [])[1];
  const openItem = async () => {
    let url;
    if (action === "verify-published") {
      url = c.public_listing_url ||
        `https://chromewebstore.google.com/detail/${itemId}`;
    } else {
      url = c.listing_url;
      if (!url) {
        let pid = publisher((await page()).url);
        if (!pid) {
          await h.goto_url("https://chromewebstore.google.com/devconsole");
          await h.wait_for_load();
          await login();
          pid = publisher((await page()).url);
        }
        if (!pid) {
          return fail("publisher-scoped developer console route not observed");
        }
        url =
          `https://chrome.google.com/webstore/devconsole/${pid}/${itemId}/edit`;
      }
    }
    await h.goto_url(url);
    await h.wait_for_load();
    await login();
    if (itemId && !(await page()).url.includes(itemId)) {
      return fail("observed URL does not contain the requested item id");
    }
    return evidence("unknown", { observed_item_id: itemId || null });
  };
  if (
    ![
      "open-item",
      "resolve-item",
      "create-item",
      "verify-draft",
      "save-draft",
      "upload-package",
      "update-listing",
      "submit-review",
      "check-status",
      "verify-published",
    ].includes(action)
  ) return fail("unsupported action: " + action);
  const packagePath = (c.package_path || "").trim();
  let observedPackage;
  if (
    ["resolve-item", "create-item", "upload-package", "verify-draft"].includes(
      action,
    )
  ) {
    if (!packagePath) return fail("package_path is required");
    if (!expected) return fail("expected_version is required");
    try {
      observedPackage = packageVersion(await readFile(packagePath));
    } catch (e) {
      return fail(`invalid extension package: ${e.message}`);
    }
    if (observedPackage !== expected) {
      return fail(
        `package version ${observedPackage} does not match expected_version ${expected}`,
      );
    }
  }
  if (
    [
      "verify-draft",
      "save-draft",
      "upload-package",
      "update-listing",
      "submit-review",
      "check-status",
      "verify-published",
    ].includes(action) && !itemId
  ) return fail("item_id is required for this action");
  if (action === "open-item" && !itemId && !c.listing_url) {
    return fail("item_id or listing_url is required for open-item");
  }
  if (action === "resolve-item" || action === "create-item") {
    if (!itemId && !name) {
      return fail("product_name is required when item_id is not supplied");
    }
    if (!itemId) {
      await h.goto_url("https://chromewebstore.google.com/devconsole");
      await h.wait_for_load();
      await login();
      const links = await js(
        `(()=>[...document.querySelectorAll('a[href]')].map(a=>({href:a.href,text:(a.innerText||a.getAttribute('aria-label')||'').trim()})).filter(x=>/\\/devconsole\\/[^/]+\\/[a-z]{32}/.test(x.href)))()`,
      ) || [];
      const found = links.find((x) =>
        x.text.toLowerCase().includes(name.toLowerCase())
      );
      if (found) {
        itemId = (found.href.match(/\/([a-z]{32})\//) || [])[1];
        return evidence("draft", {
          observed_item_id: itemId,
          reused_item: true,
          listing_url: found.href,
        });
      }
      if (!c.commit) {
        return evidence("draft", {
          dry_run: true,
          would_create: true,
          product_name: name,
        });
      }
      if (
        !(await clickText("New item")) && !(await clickText("Add a new item"))
      ) return fail("new item control not observed");
      await h.upload_file("input[type=file]", packagePath);
      await h.wait_for_load();
      await login();
      if (await textExists(["key field is not allowed"])) {
        return fail(
          "new item upload rejected: manifest key field is not allowed",
        );
      }
      if (await textExists(["there was a problem uploading your file"])) {
        return fail("new item upload rejected by Chrome Web Store");
      }
      const id =
        ((await page()).url.match(/\/devconsole\/[^/]+\/([^/]+)\/edit/) || [])[
          1
        ];
      if (!id) return fail("created item editor route not observed");
      itemId = id;
      return evidence("draft", {
        created_item_id: id,
        package_version: observedPackage,
        browser_version: await version(),
      });
    }
    return await openItem();
  }
  if (action === "verify-published") {
    const url = (await page()).url;
    if (!url.startsWith("https://chromewebstore.google.com/detail/")) {
      return evidence("unknown", { reason: "public listing URL not observed" });
    }
    if (itemId && !url.includes(itemId)) {
      return evidence("unknown", {
        reason: "public URL does not match item id",
      });
    }
    const v = await version();
    if (expected && v !== expected) {
      return evidence("unknown", { reason: "expected version not observed" });
    }
    return evidence("published", {
      expected_version: expected || null,
      observed_version: v,
    });
  }
  if (action !== "save-draft") await openItem();
  if (action === "save-draft") {
    if (!(await clickText("Save draft")) && !(await clickText("Save"))) {
      return fail("save draft control not observed");
    }
    return evidence("draft", { saved: true, observed_item_id: itemId });
  }
  if (action === "upload-package") {
    if (!c.commit) {
      return evidence("draft", {
        dry_run: true,
        would_upload: packagePath,
        package_version: observedPackage,
      });
    }
    if (
      !(await clickText("Package")) && !(await clickText("Upload new package"))
    ) return fail("package upload control not observed");
    await h.upload_file("input[type=file]", packagePath);
    await sleep(2000);
    const v = await version();
    if (v !== observedPackage) {
      return fail(
        `uploaded package version ${
          v || "unknown"
        } does not match expected_version ${observedPackage}`,
      );
    }
    return evidence("draft", {
      uploaded_package: packagePath,
      package_version: observedPackage,
      browser_version: v,
    });
  }
  if (action === "verify-draft") {
    const t = await textExists(["status: draft", "draft"]);
    if (!t) return fail("draft status not observed after reopening exact item");
    const v = await version();
    if (v !== expected) {
      return fail(
        `reopened draft version ${
          v || "unknown"
        } does not match expected_version ${expected}`,
      );
    }
    return evidence("draft", {
      observed_item_id: itemId,
      observed_version: v,
      exact_version_verified: true,
      reopened: true,
    });
  }
  if (action === "submit-review") {
    if (!c.commit || !c.allow_external_submit) {
      return evidence("draft", {
        blocked: "explicit submit authorization required",
      });
    }
    if (!(await clickText("Submit for review"))) {
      return fail("submit-for-review control not observed");
    }
    await sleep(2000);
    return evidence("submitted");
  }
  if (action === "check-status") {
    if (await textExists(["rejected", "needs changes"])) {
      return evidence("rejected", { observed_version: await version() });
    }
    if (await textExists(["published", "public"])) {
      return evidence("published", { observed_version: await version() });
    }
    if (await textExists(["submitted", "under review", "pending"])) {
      return evidence("pending", { observed_version: await version() });
    }
    return evidence("unknown", { observed_version: await version() });
  }
  if (action === "update-listing") {
    const market = c.market_package || {},
      required = [
        "title",
        "short_description",
        "long_description",
        "support_url",
      ],
      missing = required.filter((k) => !String(market[k] || "").trim());
    if (missing.length) {
      return fail("market_package missing: " + missing.join(", "));
    }
    if (!c.commit) {
      return evidence("draft", {
        dry_run: true,
        fields: Object.keys(market).sort(),
      });
    }
    return updateListing(c, h, evidence, fail);
  }
  return fail("unsupported action: " + action);
}
