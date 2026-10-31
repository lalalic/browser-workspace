import { currentLifecycle } from "./_load_lifecycle.mjs";
export default async function newThread(
  { config, helpers, log = console.log },
) {
  const { run } = await currentLifecycle();
  const result = await run(config, "new-thread", helpers);
  log(JSON.stringify(result));
  return result;
}
