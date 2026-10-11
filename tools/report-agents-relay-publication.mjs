const mode = process.argv[2] || 'success';
const token = process.env.GITHUB_TOKEN;
const repository = process.env.SOURCE_REPOSITORY || process.env.GITHUB_REPOSITORY;
const sha = process.env.SOURCE_SHA || process.env.GITHUB_SHA;
if (!token || !repository || !sha) throw new Error('GITHUB_TOKEN, repository, and sha are required');

async function github(path, init = {}) {
  const response = await fetch('https://api.github.com' + path, {
    ...init,
    headers: {
      accept: 'application/vnd.github+json',
      authorization: `Bearer ${token}`,
      'content-type': 'application/json',
      'x-github-api-version': '2022-11-28',
      ...(init.headers || {}),
    },
  });
  if (!response.ok) throw new Error(`GitHub API ${response.status}: ${await response.text()}`);
  return response.status === 204 ? null : await response.json();
}

async function publicationIssue() {
  const title = '[Agents Relay] Publication events';
  for (let page = 1; ; page++) {
    const issues = await github(`/repos/${repository}/issues?state=open&per_page=100&page=${page}`);
    const found = issues.find(issue => !issue.pull_request && issue.title === title);
    if (found) return found.number;
    if (issues.length < 100) break;
  }
  const issue = await github(`/repos/${repository}/issues`, {
    method: 'POST',
    body: JSON.stringify({ title, body: 'Durable transport for Agents Relay publication markers.' }),
  });
  return issue.number;
}

async function target() {
  const pulls = await github(`/repos/${repository}/commits/${sha}/pulls`);
  const pr = Array.isArray(pulls) ? (pulls.find(p => p.merged_at) || pulls[0]) : null;
  if (pr?.number) return { issue: pr.number, jobId: null };
  return { issue: await publicationIssue(), jobId: `unmanaged-main-${sha.slice(0,12).toLowerCase()}` };
}

async function commentOnce(issue, body, identities) {
  for (let page = 1; ; page++) {
    const comments = await github(`/repos/${repository}/issues/${issue}/comments?per_page=100&page=${page}`);
    if (comments.some(c => typeof c.body === 'string' && identities.every(x => c.body.includes(x)))) return false;
    if (comments.length < 100) break;
  }
  await github(`/repos/${repository}/issues/${issue}/comments`, { method: 'POST', body: JSON.stringify({ body }) });
  return true;
}

const dst = await target();
if (mode === 'failure') {
  const runId = String(process.env.SOURCE_RUN_ID || process.env.GITHUB_RUN_ID || '');
  const attempt = Number(process.env.SOURCE_RUN_ATTEMPT || process.env.GITHUB_RUN_ATTEMPT || '1');
  const stage = process.env.PUBLISH_STAGE || 'publish';
  const marker = { runId, attempt, sha, stage, ...(dst.jobId ? { jobId: dst.jobId } : {}) };
  const body = `<!-- agents-relay:package-publish-failed:v1 ${JSON.stringify(marker)} -->\nPublish failed at **${stage}** for commit \`${sha}\`.\nWorkflow: https://github.com/${repository}/actions/runs/${runId}`;
  const written = await commentOnce(dst.issue, body, ['agents-relay:package-publish-failed:v1', `\"runId\":\"${runId}\"`, `\"attempt\":${attempt}`]);
  console.log(JSON.stringify({ mode, written, issue: dst.issue, jobId: dst.jobId }));
} else {
  const artifact = process.env.ARTIFACT_NAME || process.env.PACKAGE_NAME;
  const version = process.env.ARTIFACT_VERSION || process.env.PACKAGE_VERSION;
  const registry = process.env.RELEASE_CHANNEL || process.env.PACKAGE_REGISTRY || null;
  if (!artifact || !version) throw new Error('artifact and version are required');
  const marker = { package: artifact, version, registry, sha, ...(dst.jobId ? { jobId: dst.jobId } : {}) };
  const body = `<!-- agents-relay:package-published:v1 ${JSON.stringify(marker)} -->\nPublished \`${artifact}@${version}\`${registry ? ` to ${registry}` : ''}.`;
  const written = await commentOnce(dst.issue, body, ['agents-relay:package-published:v1', `\"package\":\"${artifact}\"`, `\"version\":\"${version}\"`]);
  console.log(JSON.stringify({ mode, written, issue: dst.issue, jobId: dst.jobId }));
}
