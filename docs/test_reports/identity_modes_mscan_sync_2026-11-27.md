# Login modes and MSCAN conversation sync — 2026-11-27

## Result

The live MSCAN website credential and a standalone OAuth credential now resolve
to the same BioAgent account. The existing MSCAN conversation, including a new
completed agent reply, returned identical messages through both credentials.
The SSO account owns 35 active conversations. The independent local password
account owns 152. Singleuser uses its separate local identity.

## Fix and data preservation

- MSCAN's SSO subject had a legacy link to the `fuhaoyi` password account. The
  earlier OAuth-to-password alias was removed. OAuth now uses the verified SSO
  user ID directly; shared SSO website clients reject password-account links.
- With the services stopped, 34 MSCAN embedded conversations and one original
  OAuth conversation were moved to the `xiaomimi` SSO account. Session owners,
  run owners and related website transfer records were updated together. The
  152 other `fuhaoyi` conversations stayed with that password account.
- Old website tokens, OAuth alias logins and bindings were revoked so browsers
  obtain credentials for the correct account at next login. The current backup
  of all four changed SQLite databases is in
  `runtime/backups/separate-login-modes-20261127T030835Z/`. The backup made
  before the earlier alias migration remains in
  `runtime/backups/shared-sso-20261127T025134Z/`.
- The auth database was backed up again immediately before adding the login-mode
  column: `runtime/backups/access-mode-schema-20261127T032044Z/`.
- The standalone frontend refreshes its conversation list and selected chat
  when its tab regains focus. The frontend production build passed.
- The production build's default public path was corrected to `/` for direct
  port-8000 access. A prefixed deployment still opts in with `VITE_PUBLIC_PATH`.
- Existing login cookies are checked against the selected startup mode.
  MSCAN's shared SSO service and browser exchange are enabled only in OAuth
  mode, so local and password-account startups cannot enter that identity.
  The auth database records the issuing mode for each new login. On first
  upgrade, old OAuth and CAS logins keep their mode; ambiguous old website
  logins are revoked and must be exchanged again.
- MSCAN's development profile now defaults its backend connector to
  `127.0.0.1:8000` and derives its browser URL from the request host. The
  backend JAR was rebuilt and restarted with exact LAN URL and origin settings.

## Checks performed

| Check | Result |
| --- | --- |
| Singleuser on a temporary real HTTP listener with LAN host header | No-login status, session creation, a completed `gpt-5.6-sol` run and saved message read passed. |
| Multiuser on a temporary real HTTP listener with LAN host header | Anonymous access denied; registration, login, a completed `gpt-5.6-sol` run and owned message read passed. |
| OAuth broker and BioAgent HTTP listeners | Running; BioAgent login redirected to broker authorization, then to the broker login page. Bypass was disabled. |
| MSCAN website service bootstrap and browser token exchange | Passed against the running BioAgent service using the configured MSCAN client and LAN origin. |
| Cross-view account and history | Website and OAuth credentials returned the same SSO account ID, 35 conversations and identical messages for the MSCAN conversation. |
| Password-account separation | The local account retained 152 conversations and received HTTP 404 for the migrated MSCAN chat and its runs. |
| Startup-mode isolation | A live password-account token received HTTP 401 in OAuth mode. Automated HTTP checks rejected OAuth and MSCAN cookies in multiuser mode, MSCAN service bootstrap in singleuser and multiuser modes, and a pending MSCAN browser exchange after a switch to multiuser mode. |
| Live agent reply | `gpt-5.6-sol` run succeeded; the MSCAN conversation grew from 2 to 4 messages, identical through both credentials. |
| Frontend and embed asset | MSCAN frontend and BioAgent embed script returned HTTP 200; frontend production build passed. |
| Direct singleuser page | A fresh production build served JavaScript and CSS at `/static/...` with HTTP 200. Headless Chrome rendered the workspace rather than an empty root. The temporary test server was stopped afterward. |
| Focused automated checks | 27 OAuth, CAS, startup environment, website federation and host checks passed. |

## Limits

The external CNCB CAPTCHA login was not automated. The OAuth callback path was
tested through the code and a live account credential; both browser views must
sign in again after their old credentials were revoked. MSCAN's authenticated Java endpoint
was not called with a browser JWT; its backend was running with the matching
BioAgent service URL, browser URL, client secret and origins. No Cromwell
pipeline was submitted for this identity and conversation test.

Services were running on ports 8090 (broker), 8000 (BioAgent), 8080
(MSCAN backend) and 8848 (MSCAN frontend) during validation. All four were
later stopped on request for manual testing. Do not enable
`OAUTH_AGENT_LOGIN_BYPASS` when expecting a shared MSCAN SSO account: it issues
a fixed test identity for BioAgent login.
