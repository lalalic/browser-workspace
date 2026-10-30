# Z.ai

Reusable lifecycle actions for https://chat.z.ai. A signed-in account is required.

`new-thread` accepts `{"message":"Start a new conversation."}` and returns the
durable thread ID after the user message appears in the chat and the composer is
cleared. Optional `source_thread_id` records provenance only; it does not copy
conversation history.

`new-turn` accepts `{"thread_id":"<chat id>","message":"Continue the conversation."}`
and submits one turn to that exact chat. Both actions are text-only, reject
unsent drafts or selected files, and return without waiting for the assistant
answer. A submission timeout is ambiguous: inspect the same session before
retrying because the action never resends automatically.

Actions use the semantic textarea and send button, and verify acceptance using
the matching user message, cleared composer, and durable `/c/{id}` URL. The
lifecycle actions have not yet been live-verified by submitting a message.