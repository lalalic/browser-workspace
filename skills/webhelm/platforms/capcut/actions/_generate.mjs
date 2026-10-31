import { selectMediaType, selectModel } from "./_capcut_common.mjs";
export default async function generate(
  { config: cfg, helpers: h, log = console.log },
) {
  const prompt = String(cfg.prompt || "").trim(),
    mediaType = cfg.media_type,
    model = String(cfg.model || "").trim();
  if (!prompt) throw new TypeError("prompt is required");
  if (!["image", "video"].includes(mediaType)) {
    throw new TypeError("media_type must be 'image' or 'video'");
  }
  if (!model) {
    throw new TypeError(
      "model is required; run the models action to list choices",
    );
  }
  if (cfg.confirm_generation !== true) {
    throw new TypeError(
      "Set confirm_generation to true to submit and potentially consume CapCut credits",
    );
  }
  const info = await h.page_info();
  if (
    !info.url.toLowerCase().includes("capcut.com") ||
    !info.url.toLowerCase().includes("/editor")
  ) throw new Error("Open the CapCut editor before running generate");
  await selectMediaType(mediaType, h);
  const selected = await selectModel(model, h);
  await h.fill_input('[role="textbox"][contenteditable="true"]', prompt);
  if (
    !(await h.js(
      "(()=>{const b=document.querySelector('button[aria-label=\"Generate\"]');return !!b&&!b.disabled})()",
    ))
  ) {
    throw new Error(
      "CapCut Generate is unavailable; inspect the editor state before retrying",
    );
  }
  await h.click('button[aria-label="Generate"]');
  log(
    `Submitted ${mediaType} generation with ${selected}.\nGeneration completion is not inferred; inspect the CapCut Generated tab.\n${await h
      .snapshot()}`,
  );
  return { status: "submitted", media_type: mediaType, model: selected };
}
