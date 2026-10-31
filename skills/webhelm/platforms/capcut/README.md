---
name: capcut-platform
description: "CapCut web editor navigation and inspection."
---

# CapCut

The platform supports listing CapCut's current image/video models and submitting
prompt-based image or video generation requests. Use the caller's authenticated
browser context; never store credentials.

Start one session, then keep using its ID for each command:

```bash
webhelm session start --url https://www.capcut.com/editor
webhelm platform run capcut models --session-id SESSION_ID
webhelm platform run capcut generate --session-id SESSION_ID --config prompt.json
webhelm session stop SESSION_ID
```

`prompt.json` must contain `media_type` (`image` or `video`), an exact `model`
name from the `models` action, `prompt`, and `confirm_generation: true`. That
confirmation is required because generation may consume account credits. The
action submits the prompt but does not infer completion or download the result;
generated media remains in CapCut.

Example:

```json
{
	"media_type": "video",
	"model": "Seedance 2.5",
	"prompt": "A slow aerial view over a misty mountain lake at sunrise",
	"confirm_generation": true
}
```

Existing timeline editing and reference-media editing are not implemented.

The skills.sh search surfaced browser/editor guidance, local draft-file CLI
tools, and a cloud video-generation skill. This adapter uses CapCut's own
browser model picker so model availability is read live instead of hard-coded.