export default async function open(
  { config: cfg, helpers: h, log = console.log },
) {
  const url = cfg.url || "";
  if (!url.startsWith("https://www.iyf.tv/play/")) {
    throw new TypeError("Only IYF desktop play URLs are allowed");
  }
  await h.new_tab(url);
  await h.wait_for_load();
  const info = await h.page_info(),
    player = await h.js('!!document.querySelector("video")'),
    result = { url: info.url, title: info.title, player };
  log(JSON.stringify(result));
  return result;
}
