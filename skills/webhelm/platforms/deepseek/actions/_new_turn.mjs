import { run } from "./_lifecycle_common.mjs";
export default async function newTurn({ config, helpers, log = console.log }) {
  const result = await run(config, "new-turn", helpers);
  log(JSON.stringify(result));
  return result;
}
