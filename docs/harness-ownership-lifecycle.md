# Browser Workspace Session and Harness ownership — 2026-10-10

## Root cause and implementation
Session Daemon previously started a detached Harness during module import, before singleton locking; its shutdown cleanup never stopped the Harness, and SIGKILL left it orphaned. Managed Chrome uses explicit CDP, whose ensure_daemon path lacked the other path's process-spawn lock and PID generation guard.

Now Session Daemon starts the Harness after singleton lock acquisition, passing an ownership token, parent process identity, and a POSIX pipe read descriptor. The pipe write descriptor belongs only to Session Daemon. EOF after parent SIGKILL, re-exec, or exit terminates that Harness process without signalling another PID, closing Chrome, or deleting profiles. On Windows, creation-time fingerprint plus PID is used. Normal shutdown sends a token-checked owner_shutdown RPC, waits briefly for graceful exit, then closes its pipe. Both CDP and local modes share canonical spawn lock and pending-generation guard.

## Compatibility and deployment risks
Canonical Harness socket and runtime layout remain unchanged. Healthy legacy/other-runtime Harnesses without a matching token remain reusable and are not forcibly replaced, killed, or claimed. Consequently, an existing legacy Harness may survive upgrade until a separately validated safe retirement and subsequent new spawn. Before deployment: resolve the current durable branch head; verify existing canonical socket, PID generation, and other live owners before retiring legacy instances. Source SHA from this implementation alone must not be assumed current.

Current predeployment runtime v0.4.4: Session PID 9656; associated Harness PID 9659; an additional preexisting Harness PID 77009 has PPID 1. Ownership of PID 77009 was not verified; it was deliberately not killed. Chrome PID 8450 is reused. NeoY, Chrome, existing daemons and profiles were neither restarted nor deleted.

## Validation
- Ownership unit and real subprocess SIGKILL regression tests: 10 passed, including normal owner RPC, PID reuse refusal, parent EOF/re-exec, duplicate explicit CDP pending child, and PyPI copy equivalence.
- Other Python tests: 51 passed and one known unrelated CLI skill-path assertion fails due to existing SKILL.md mismatch. System default Python 3.9 lacks tomllib; Python 3.11 PyPI-package test passed via uv.
- Node tests: 31 passed.
- Live browser-workspace status and session list passed, 0 sessions, with process PIDs stable before and after smoke.
- git diff --check passed.

## Changed code
session_daemon.py, src/browser_harness/admin.py, src/browser_harness/daemon.py, their PyPI mirrors, test/test_session_execution.py, and new test/test_harness_ownership.py. No deployment performed.
