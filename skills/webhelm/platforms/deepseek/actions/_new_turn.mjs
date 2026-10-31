import { currentLifecycle } from "./_load_lifecycle.mjs";
export default async function newTurn({ config, helpers, log = console.log }) {
  const { run } = await currentLifecycle();
  const result = await run(config, "new-turn", helpers);
  log(JSON.stringify(result));
  return result;
}
