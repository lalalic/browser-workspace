# DeepSeek

Reusable actions for https://chat.deepseek.com. A signed-in account is required.

`validate` checks the message composer and native attachment input without
changing the conversation or uploading files.

## Thread Lifecycle

`new-thread` accepts `{"message":"Remember the test marker WEBHELM-4826."}`.
It starts a fresh ordinary chat, submits once, waits for the assistant answer,
and returns it. Optional `source_thread_id` records provenance but does not copy
conversation history.

`new-turn` accepts `{"thread_id":"<canonical UUID>","message":"What was the test marker?"}`.
It opens that exact thread, waits for an active response to finish, submits one
continuation, and returns the new answer. Both actions preserve unsent drafts
and queued attachments, accept `timeout_seconds` (1-600, default 120), and
support an optional absolute `image` path. Projects and Temporary Chat are
unsupported. `user_message_id` is null because the live DOM does not expose a
verified stable user-message ID.

Result (one JSON object):

```json
{"status":"completed","mode":"new-turn","thread_id":"<uuid>",
 "thread_url":"https://chat.deepseek.com/a/chat/s/<uuid>","answer":"plain text"}
```

- `answer` is the rendered `innerText` of the new final answer, excluding the
  reasoning panel. Only an answer that appears after this submission counts.
- `"response_format":"json"` also parses the answer (a fenced ```json block or
  the whole text) into `data`; on failure `data` is null and `parse_error` is
  set. Ask for JSON in the message itself; DeepSeek has no enforced schema.
- `"wait": false` returns the old `status: "submitted"` receipt immediately.
- On timeout the result is `status: "pending"`. Rerun with
  `{"resume":true,"thread_id":"<uuid>"}` to read the latest answer without
  resending. A timeout is not proof that the submission failed.

Invoke either action through the same local platform runner shown below,
replacing `understand-image` with `new-thread` or `new-turn`. After an uncertain
submission error, inspect the same session before retrying; neither action
automatically resends.

## Image Understanding

`understand-image` is `new-thread` with a required `image` and a default
`prompt`; it returns the same result plus `url` (and `screenshot` when
`screenshot_path` is set). All waiting logic lives in the shared lifecycle.
Configuration is a JSON object:

```json
{
	"image": "/absolute/path/image.png",
	"prompt": "Describe the image and transcribe its visible text.",
	"timeout_seconds": 120,
	"screenshot_path": "/tmp/deepseek-result.png"
}
```

Only `image` is required. Supported formats are PNG, JPEG, WebP, GIF, BMP, TIFF,
and AVIF, subject to the live file input's accepted extensions. Only PNG has
been exercised against the live site. Site size limits and quotas still apply.

Run the local adapter with the root skill directory as the package source:

```bash
uvx --no-cache --from ~/.agents/skills/webhelm webhelm platform run deepseek understand-image \
	--session-id SESSION_ID --config /absolute/path/config.json
```

The published PyPI package does not contain this local addition yet. `--no-cache`
also avoids stale locally built wheels after editing platform files.

If the result is `pending`, retain the same tab and use `{"resume": true}` to
read the answer without uploading or submitting again. A timeout is not proof
that submission failed. This action never automatically retries a submission.

The final answer is read from the **signed-in webpage's own** completion
response (fetch/XHR observed without changing or issuing any request). The
observer requires a matching user submission and durable thread URL, an SSE
`ready` receipt, explicit `response/status = FINISHED`, a `close` event,
and nonempty `RESPONSE` fragments. A DOM-rendered assistant answer remains a
fallback. HTTP 200, a thread title, partial tokens, or a cleared composer alone
are never treated as a completed answer. Browser background pages are woken via
CDP lifecycle without foregrounding Chrome; React draft input uses the native
value setter + bubbling input event so hidden-tab keyboard loss cannot submit
an empty prompt. No developer API key is needed. Attachment preview readiness
is checked before submission; DeepSeek handles server-side processing.

Actions use semantic DOM controls, not screen coordinates. Callers must explicitly
choose which local images to disclose to DeepSeek. Never upload private project
screenshots or documents merely to test the adapter.