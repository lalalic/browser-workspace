export default async function openEditor({ helpers: h, log = console.log }) {
  await h.new_tab("https://www.capcut.com/editor");
  await h.wait_for_load();
  const info = await h.page_info();
  log(
    `Opened CapCut editor: ${info.url}\nNo media was imported and no project was edited or exported.\n${await h
      .snapshot()}`,
  );
  return info;
}
