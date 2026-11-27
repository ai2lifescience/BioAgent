# User model design: separate startup modes

## Core principle

BioAgent selects **one access mode per server process** with `AGENT_AUTH_MODE`.
`singleuser`, `multiuser`, and `oauth` are independent ways to enter BioAgent.
Starting in another mode must not convert an account, reuse its login, or merge
its conversations. In particular, a password account and an OAuth account must
not be linked because their usernames or email addresses match.

There is one intentional identity match **inside OAuth mode**: MSCAN's embedded
assistant and a standalone BioAgent OAuth tab use the same verified CNCB SSO
user ID. They therefore see the same SSO-owned conversations. This does not
connect either view to `singleuser` or `multiuser`.

| Startup mode | Identity and login | Conversation owner | MSCAN SSO bridge |
| --- | --- | --- | --- |
| `singleuser` | No login; one local user for everyone allowed onto that listener | Reserved user ID `local` | Rejected |
| `multiuser` | BioAgent username and password; registration if enabled | BioAgent-generated user ID for each password account | Rejected |
| `oauth` | CNCB OAuth broker verifies SSO login | Verified SSO user ID | Accepted; MSCAN and standalone OAuth use that same owner |

`cas` remains a legacy code mode with its own login tokens. It is outside this
three-mode MSCAN design.

## Required boundaries

1. **Startup decides the mode.** Run one server command at a time and select
   `AGENT_AUTH_MODE` explicitly for network access. OAuth settings belong to an
   OAuth startup; direct `singleuser` and `multiuser` startups do not derive
   OAuth URLs. A public origin left in the environment can still constrain a
   direct LAN listener, so clear it when switching to direct access.
2. **A login works only in its issuing mode.** Password, OAuth, CAS, and website
   login records carry a `mode`. The server compares it with the current
   `AGENT_AUTH_MODE` on authenticated requests. Switching modes requires a new
   login; an old cookie cannot cross the boundary. `singleuser` uses its local
   principal without an account login.
3. **Ownership follows the user ID.** Conversations, runs, files, and bridge
   records are checked against the authenticated principal. Switching the
   startup command does not change an existing record's owner. A foreign
   conversation is unavailable to the new principal.
4. **MSCAN enters through OAuth only.** The MSCAN connector authenticates as a
   trusted backend, supplies the verified SSO subject and username, and
   exchanges a short-lived browser grant. The subject must equal the supplied
   SSO user ID. Shared SSO identities cannot be explicitly linked to password
   accounts, and a legacy mismatched mapping is rejected until migrated.
   MSCAN service requests and browser exchanges are rejected when BioAgent is
   in `singleuser` or `multiuser` mode.
5. **Other website clients follow their own account policy.** A website without
   shared SSO may map to a password account in `multiuser` mode. Its website
   login is a `multiuser` login and cannot be used in OAuth mode. This policy
   does not grant MSCAN SSO access to password accounts.
6. **No automatic cross-mode migration.** Moving old conversations between
   owners requires an explicit, backed-up migration of session ownership,
   runs, and related bridge data. Revoke old grants, cookies, and bindings
   afterward. A frontend refresh only displays records already owned by the
   current account; it never changes ownership.

## Current implementation

- [`auth/context.py`](../auth/context.py) selects the access mode and defines
  the reserved local principal.
- [`auth/store.py`](../auth/store.py) stores account logins and checks the
  issuing `mode` on every authenticated request.
- [`interfaces/auth.py`](../interfaces/auth.py) chooses the request principal
  and applies host and origin rules for the selected mode.
- [`web_bridge/identity.py`](../web_bridge/identity.py) enforces the MSCAN
  shared SSO mapping and website mode boundary.
- The [MSCAN startup guide](mscan_web_bridge.md) and [web usage guide](web_usage.md)
  show the commands for each mode. The [live identity test report](test_reports/identity_modes_mscan_sync_2026-11-27.md)
  records the verified OAuth/MSCAN match and password-account separation.

## Remaining storage boundary

The current modes share the `users` table in `runtime/auth.sqlite3`. The
`logins.mode` check isolates credentials, and the current local, password, and
SSO accounts have different user IDs, but the account table does **not** yet
namespace `user_id` or `username` by mode. A username collision can block
creation or login in another mode; a coincident user ID is not distinguished
at the ownership layer. Full account-namespace independence would require
mode-scoped account keys (or separate account stores) and a migration of
existing ownership records. Until that work is done, the enforced separation
is the login-mode boundary plus distinct user IDs in the present data, not
physically separate account storage.

For complete namespace separation, use an immutable internal principal ID as
the owner of sessions and runs. Resolve external identities with a separate
`(mode, subject)` key: `oauth` stores the verified SSO subject there, while
`multiuser` stores its password-account ID. Scope username uniqueness to the
appropriate mode. MSCAN and standalone OAuth must resolve to the *same* OAuth
principal; a password account with the same username or subject text must
resolve to a *different* principal. Migrating to this model requires remapping
existing ownership records and website identities together.
