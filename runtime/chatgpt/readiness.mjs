export class SubmissionVerificationError extends Error {
  constructor(message, diagnostic = {}) {
    super(`${message}: ${JSON.stringify(diagnostic)}`);
    this.name = "SubmissionVerificationError";
    this.diagnostic = diagnostic;
  }
}

export function waitUntilStable(
  readState,
  ready,
  {
    timeout = 15,
    interval = 0.25,
    stableSamples = 2,
    phase = "readiness",
    sleep = (ms) => new Promise((r) => setTimeout(r, ms)),
  } = {},
) {
  return (async () => {
    const end = Date.now() + timeout * 1000;
    let stable = 0, previous;
    while (Date.now() < end) {
      let state;
      try {
        state = await readState();
      } catch {
        stable = 0;
        await sleep(interval * 1000);
        continue;
      }
      if (ready(state)) {
        const key = JSON.stringify(state);
        if (key === previous) stable++;
        else {
          previous = key;
          stable = 1;
        }
        if (stable >= stableSamples) return state;
      } else {
        stable = 0;
        previous = undefined;
      }
      await sleep(interval * 1000);
    }
    throw new Error(`ChatGPT ${phase} was not observed ready`);
  })();
}

export function promptTextMatches(observed, expected) {
  const norm = (value) =>
    String(value || "").replace(/\s+/g, " ").replace(/>\s+/g, ">").replace(
      /\s+</g,
      "<",
    ).trim();
  const a = norm(observed), b = norm(expected);
  if (a.includes(b)) return true;
  if (!b) return !a;
  const span = Math.min(256, Math.max(48, Math.floor(b.length / 8)));
  return a.length >= Math.floor(b.length * 0.9) &&
    a.includes(b.slice(0, span)) && a.includes(b.slice(-span));
}

export function sendReady(state, { prompt, attachments = [] } = {}) {
  const button = state?.send;
  const enabled = typeof button === "object" ? !!button.enabled : !!button;
  if (!enabled) return false;
  if (prompt !== undefined && !promptTextMatches(state.text || "", prompt)) {
    return false;
  }
  const names = Array.isArray(state.attachments?.names)
    ? state.attachments.names
    : [];
  return attachments.every((name) => names.includes(name));
}

export function submissionReceipt(
  turns,
  beforeCount,
  prompt,
  composerText,
  { allowComposerCleared = false } = {},
) {
  for (const turn of turns.slice(beforeCount)) {
    if (promptTextMatches(turn.text, prompt)) {
      return { verified_by: "user-turn", turn };
    }
  }
  if (allowComposerCleared && !String(composerText || "").trim()) {
    return {
      verified_by: "composer-cleared",
      turn: { id: null, text: prompt },
    };
  }
  return null;
}

export function submissionFailureDiagnostic(
  turns,
  beforeCount,
  prompt,
  composerText,
  uiBefore,
  uiAfter,
) {
  return {
    accepted: false,
    reason: "no_accepted_user_turn",
    user_turn_matched: false,
    before_user_turn_count: beforeCount,
    user_turn_count: turns.length,
    composer_populated: !!String(composerText || "").trim(),
    composer_text_length: String(composerText || "").trim().length,
    ui_changed: uiBefore == null || uiAfter == null
      ? null
      : JSON.stringify(uiBefore) !== JSON.stringify(uiAfter),
    ui_before: uiBefore,
    ui_after: uiAfter,
  };
}
