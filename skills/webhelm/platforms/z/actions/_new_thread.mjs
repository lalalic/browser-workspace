import { run } from "./_lifecycle_common.mjs";
export default async function newThread(
  { config, helpers, log = console.log },
) {
  const result = await run(config, "new-thread", helpers);
  log(JSON.stringify(result));
  return result;
}
