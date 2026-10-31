# Z.ai WebHelm lifecycle

Both ordinary chat actions use the single _lifecycle_common.py module, which
installs an in-page observer of the **website's own** streaming
/api/chat/completions or /api/v2/chat/completions fetch response. No direct
API requests, cookie extraction, or authentication token handling.

- new-thread accepts a text message and optionally source_thread_id.
- new-turn accepts a canonical /c/{thread_id} plus a text message.
- wait defaults to true. Successful completion requires the webpage's
  chat:completion SSE events, an explicit data.done=true, nonempty final
  content, a verified user submission, and a durable /c/{id} route.
  Returns status=completed, answer and thread_id.
- wait=false returns status=submitted after verified receipt.
- response_format=json parses the final answer into data; parse errors are
  returned separately without claiming JSON success.
- timeouts or missing completion evidence return status=pending. Never infer
  success from HTTP 200 alone or merely the existence of a user message.
- resume=true, with optional thread_id, reads the latest observed stream
  **only in the same live Browser Workspace session**; never resubmits.
  A closed session or missing observer cannot be resumed from the network
  with this action. Do not re-send ambiguous pending messages automatically.

Both actions protect unsent drafts and selected attachments before changing
threads. Responses longer than 1.5 MB are not retained by the observer.

Z.ai's frontend (observed Oct 31, 2026) uses type=chat:completion events
with data.delta_content, data.content and data.done; this differs from
DeepSeek's stream envelope. Do not use DeepSeek's FINISHED/close parser.

Live completed-answer, JSON output, and no-resubmission resume were verified
on 2026-10-31 with GLM-5.3-Flash and one owned browser session. Other models,
advanced Agent modes, WebSocket transports, and future frontend event formats
remain unverified.
