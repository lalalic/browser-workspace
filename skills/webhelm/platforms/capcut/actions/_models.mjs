import { availableModels } from "./_capcut_common.mjs";
export default async function models({ helpers, log = console.log }) {
  const result = {};
  for (const mediaType of ["image", "video"]) {
    result[mediaType] = (await availableModels(mediaType, helpers)).map((
      { name },
    ) => name);
  }
  log(JSON.stringify(result, null, 2));
  return result;
}
