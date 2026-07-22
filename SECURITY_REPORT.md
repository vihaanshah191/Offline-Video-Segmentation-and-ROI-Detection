# Security Report

Snapshot of the security posture at the end of this pass. Findings are
categorized as **Fixed this pass**, **Pre-existing / verified**, and
**Known limitations (not fixed, documented)** — the last category is not
a euphemism for "broken," it's an explicit statement of what's out of
scope and why, consistent with this project's stated goal of never
overclaiming.

## Fixed this pass

| Issue | Severity | Detail |
|---|---|---|
| CORS `allow_headers` missing `Authorization` | High | Broke every authenticated cross-origin request (see `BUG_REPORT.md` #1). Fixed, regression-tested. |
| CORS `allow_methods` missing `PUT` | High | Broke the Settings-page save endpoint cross-origin (see `BUG_REPORT.md` #2). Fixed, regression-tested. |
| `max_concurrent_analyses` unenforced | Medium (availability) | Unbounded concurrent analysis threads, exploitable via batch upload to exhaust host CPU/memory. Fixed with a semaphore (see `PERFORMANCE_REPORT.md`). |

## Authentication & authorization (new this pass)

- **JWT (HS256)**, hand-rolled with stdlib `hmac`/`hashlib` rather than a
  third-party library — deliberate choice, documented in
  `app/core/security.py`'s module docstring (avoids a real dependency
  hazard: several JWT libraries probe for `cryptography` at import time,
  which crashed in this sandboxed environment on an unrelated broken
  system package). Signature verification uses `hmac.compare_digest`
  (constant-time).
- **Passwords**: bcrypt via the `bcrypt` package directly (not `passlib`,
  which is unmaintained and incompatible with modern bcrypt — see the
  module docstring), with defensive 72-byte truncation (bcrypt's own
  limit) handled explicitly rather than raising.
- **Fail-fast config validation**: `AUTH_ENABLED=true` with the placeholder
  `JWT_SECRET_KEY` or `ADMIN_PASSWORD` still set raises at startup
  (`Settings._validate_auth_secret`), rather than silently running with an
  insecure default.
- **RBAC**: three roles (admin/investigator/viewer) via a static
  `ROLE_PERMISSIONS` mapping, checked per-route via `require_permission()`.
  Verified with role-specific tests (`test_auth.py`): a viewer cannot
  upload, an investigator can upload but cannot change settings, only
  admin can.
- **Session timeout**: JWT expiry (`JWT_EXPIRY_MINUTES`, default 30) —
  stateless, no server-side session store to leak or need invalidating.
  A deactivated user's existing token is still rejected on the next
  request (`get_current_principal` re-checks `is_active` against the DB,
  not just the token claims) — verified by
  `test_auth.py::test_deactivated_user_token_rejected`.
- **No-op-by-default design**: every auth dependency degrades to a
  full-access anonymous principal when `AUTH_ENABLED=false` (the default),
  so the entire pre-existing unauthenticated API surface is provably
  unaffected unless an operator opts in — this is the load-bearing design
  decision that let this pass add auth without risking any regression to
  the base (auth-off) demo flow, and it's verified by running the full
  test suite with auth untouched (still the default in every test except
  `test_auth.py`'s own scoped fixture).
- **Audit log**: every login/login_failed/upload/analyze/delete/cancel/
  settings_update is recorded, including with `username=None` when auth is
  disabled (so a single-operator deployment still gets a useful activity
  log). Writing an audit entry never raises or rolls back the action it's
  recording (`AuthService.record_audit` swallows its own failures).

## Pre-existing / verified unchanged

- **Upload validation**: extension allow-list + `Content-Length` pre-check
  + streamed size enforcement + magic-byte signature check (the file's
  actual bytes must match its claimed container format, not just its
  extension).
- **Path traversal**: verified the SQLite database file is not reachable
  through the public `/storage` static mounts, including via `../`
  traversal attempts against each mounted subdirectory
  (`test_database_file_not_reachable_via_storage_mount`).
- **Rate limiting**: present, single-process in-memory (documented
  limitation, unchanged — see below).
- **DB isolation**: only `storage/{videos,clips,heatmaps,thumbnails}` are
  mounted over HTTP; the SQLite file lives outside all of them.

## Known limitations (not fixed — documented, not hidden)

- **Rate limiting is single-process, in-memory.** Correct for the default
  single-node thread-backend deployment; would need a shared store (Redis)
  to be correct behind multiple app processes/replicas. Unchanged from the
  prior pass's documented limitation.
- **No CSRF protection.** Not applicable as designed: the API is a
  stateless Bearer-token API (no cookies, no ambient browser credentials
  sent automatically), so CSRF — which relies on a browser automatically
  attaching credentials to a cross-site request — doesn't apply to this
  auth model.
- **No HTTPS enforcement at the application layer.** This is a deployment
  concern (reverse proxy / TLS termination), not something the FastAPI app
  itself should own; documented here so it isn't assumed to be handled.
- **JWT has no revocation list.** A token is valid until it expires; there
  is no way to invalidate a single issued token early (e.g. on password
  change) short of rotating `JWT_SECRET_KEY`, which invalidates *all*
  tokens. Acceptable for the target deployment (short-lived tokens, small
  trusted user base) but a real limitation of the stateless design.
- **No bulk/multi-video export endpoint** — not a security issue, but
  noted here since it means there's no bulk-export code path to have
  under-secured either.
- **Demo Mode has no additional access restriction** beyond the normal
  `upload` permission — a viewer role (which lacks `upload`) correctly
  cannot trigger it; verified by the same RBAC test pattern used for
  regular uploads, not a separate test (Demo Mode reuses
  `require_permission("upload")` directly, so it inherits the same
  guarantee rather than needing its own).

## Explicitly not audited this pass

- Dependency CVE scanning (`pip-audit` / `npm audit`) was not run as part
  of this pass — recommend running both before a real deployment.
- No penetration testing or fuzzing was performed against the API surface.
