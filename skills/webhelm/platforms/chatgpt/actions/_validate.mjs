import { targetUrl, visibleDeliveryError } from "./_action-common.mjs";
export async function run({ helpers, config = {} }) {
  const { js, goto_url, wait_for_load } = helpers;
  const probe = "BrowserWorkspaceValidateProbe20261020";
  await goto_url(
    targetUrl({
      project_id: String(config.project_id || "").trim() || undefined,
      thread_id: String(config.thread_id || "").trim() || undefined,
      temporary: !!config.temporary,
      prompt: probe,
    }),
  );
  await wait_for_load();
  const error = await visibleDeliveryError(js);
  if (error) return error;
  const login = await js(
    `(() => {const v=e=>!!e.getClientRects().length;const l=[...document.querySelectorAll('a,button')].some(e=>v(e)&&/^(log in|sign in)$/i.test((e.innerText||'').trim()));const p=(document.body?.innerText||'').toLowerCase();return l&&(p.includes('log in to chatgpt')||p.includes('sign in to chatgpt'));})()`,
  );
  if (login) return "authentication_required";
  return !!await js(
    `(() => {const b=document.querySelector('button[data-testid="send-button"],button[aria-label="Send prompt"],button[aria-label="Send"],form button[type="submit"]');return !!b&&!b.disabled&&b.getAttribute('aria-disabled')!=='true';})()`,
  );
}
