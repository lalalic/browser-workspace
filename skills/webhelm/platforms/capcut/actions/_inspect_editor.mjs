export default async function inspectEditor({ helpers: h, log = console.log }) {
  const info = await h.page_info();
  if (!info.url.toLowerCase().includes("capcut.com")) {
    throw new Error(`Not on CapCut: ${info.url}`);
  }
  const text = await h.js("document.body.innerText") || "";
  const markers = ["Media", "Captions", "Export"];
  const found = markers.filter((x) => text.includes(x));
  log(
    `URL: ${info.url}\nTitle: ${info.title}\nEditor markers: ${
      found.join(", ") || "none"
    }${
      found.length !== markers.length
        ? "\nThe current page may not be the CapCut editor."
        : ""
    }\n${await h.snapshot()}`,
  );
  return { url: info.url, title: info.title, markers: found };
}
