# Main integration into pipeline2agent-v4.0.0

Date: 2026-11-20, Asia/Shanghai.

The latest fetched `origin/main` (`135be9f648cb`) has been applied to
`pipeline2agent-v4.0.0` with `git merge --no-ff --no-commit origin/main`.
The merge and restoration of local work completed without conflicts. At the
validation checkpoint, no commit or push had been performed. `HEAD` was
`92486c546337`, and `MERGE_HEAD` pointed to the fetched main revision.

The merged code retains v4's workflow approval display and workflow reconciler,
alongside main's OAuth environment handling, frontend URL configuration and
website integration changes. The uncommitted `autograph_specialist`, specialist
package refactor, dependency validation, catalog fixes and existing reports
were restored after merging.

## Preservation

Before merging, all 79 changed or untracked paths were backed up, including
tracked binary changes, untracked files, original status and file hashes.
After restoration, 78 paths matched their original content exactly.
`docs/user_isolation.md` was automatically combined with main's documentation
updates and retains the local specialist wording. The three files deleted by
the local package refactor remain deleted.

The backup is retained at
`/media/data/fuhaoyi/codes/.bioagent-merge-backups/20261120T200247`.
The restored stash is also retained as
`48f82daa8723d67d2a93aab3133c1a97a0b35ace`.
[Recorded integration state](main_merge_2026-11-20/integration-state.json).

## Validation

| Check | Result | Evidence |
|---|---|---|
| Pipeline, planner, nested approvals, model adapters, OAuth/CAS and website integration regressions | 161 tests, 144 passed, 17 skipped | [Python regressions](main_merge_2026-11-20/python-regressions.log) |
| Direct-server HTTP routes, assets, approvals and browser smoke check with development build | 9 passed | [Web contract](main_merge_2026-11-20/web-contract-development.log) |
| Architecture and tool-registration smoke check | Passed | [Architecture](main_merge_2026-11-20/architecture.log) |
| Production frontend, TypeScript and embed SDK build | Passed | [Production build](main_merge_2026-11-20/frontend-build.log) |
| Development frontend, TypeScript and embed SDK build | Passed | [Development build](main_merge_2026-11-20/frontend-development-build.log) |
| Unresolved merge entries | None | Git index checked after restoring local work |
| Source and documentation whitespace checks | Passed | `git diff --cached --check` and `git diff --check`, excluding captured `.diff` and `.log` artifacts at publication |

The first direct-server web check used the production build and failed its
root-relative asset assertion. The production configuration deliberately uses
`/OneMicro/agent/`, while this check accesses the Python server directly at `/`.
After rebuilding with the existing development configuration, which uses `/`,
all nine web checks passed. No source or environment configuration was changed
to resolve this mismatch. [Initial production/direct-server check](main_merge_2026-11-20/web-contract.log).
The final generated `frontend/dist` uses the development configuration.
Both builds reported a non-failing bundle-size warning.

These checks exercise local fixtures and mocked service boundaries. They do not
repeat the earlier live Cromwell execution or test a deployed MSCAN instance and
production reverse proxy.

## Validation checkpoint and publication authorization

At the end of validation, the repository remained in a pending merge on
`pipeline2agent-v4.0.0`. Incoming main changes were staged by Git, and the
restored local work was unstaged or untracked. The integration-state evidence
records this checkpoint.

The user subsequently authorized committing and pushing the combined changes,
opening a pull request to `main`, and merging it while retaining
`pipeline2agent-v4.0.0` locally and on GitHub. The validation results above
describe the source prepared for that publication.
