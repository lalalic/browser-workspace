export default async function find(
  { config: cfg, helpers: h, log = console.log },
) {
  const query = String(cfg.query || "").trim();
  if (!query) throw new TypeError("config.query is required");
  if (!(await h.page_info()).url.startsWith("https://www.iyf.tv/")) {
    await h.goto_url("https://www.iyf.tv/");
    await h.wait_for_load();
  }
  const matches = await h.js(
    `(()=>{const q=${
      JSON.stringify(query)
    };return Array.from(document.querySelectorAll('a[href*="/play/"]')).filter(a=>a.textContent.includes(q)).map(a=>({title:a.textContent.trim().slice(0,120),url:a.href})).filter((a,i,all)=>all.findIndex(b=>b.url===a.url)===i).slice(0,15)})()`,
  );
  const out = { query, matches };
  log(JSON.stringify(out));
  return out;
}
