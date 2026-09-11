# BioAgent Development Workflow

Use one short-lived branch and one pull request for each task. This example
updates `README.md`.

## 1. Prepare The Repository

Clone the repository once:

```bash
git clone https://github.com/ai2lifescience/BioAgent.git
cd BioAgent
```

Before each task, update the stable branch:

```bash
git switch main
git pull --ff-only origin main
```

### Troubleshooting: Local Changes Block Pulling

> Skip this subsection if `git pull --ff-only origin main` succeeds.

Git stops a pull when it would overwrite local changes. Inspect them first:

```bash
git status
git diff
```

The common solution for unfinished work is to stash it, update `main`, create a
task branch, and restore the work there:

```bash
git stash push -u -m "Temporary README work"
git pull --ff-only origin main
git switch -c docs/update-readme
git stash pop
```

Resolve any conflicts from `git stash pop`, then continue at step 3.

#### Danger: Discarding Local Work

> **Warning:** `git restore README.md` immediately deletes every uncommitted
> change in the local `README.md`. Git normally cannot recover those edits. Do
> not use this command as the default solution to a blocked pull; use the stash
> method above when the work might be needed.

Run the following commands only after `git diff` confirms that every displayed
local change can be permanently discarded:

```bash
git diff -- README.md
git restore README.md
git pull --ff-only origin main
```

## 2. Create A Task Branch

Use a unique name that describes the work:

```bash
git switch -c docs/update-readme
```

Other examples:

```text
feature/add-uniprot-tool
fix/pipeline-input-path
docs/update-web-guide
```

## 3. Make And Review Changes

Edit `README.md`, then inspect the workspace:

```bash
git status --short
git diff -- README.md
```

Keep the change focused on the task. Do not include unrelated generated files
or local runtime data.

## 4. Run Tests

Run the project checks before committing:

```bash
python -m evals.smoke_architecture
python -m evals.smoke_session_artifacts
```

Add focused tests when the change affects behavior not covered by smoke checks.

## 5. Commit The Change

Stage only the files that belong to the task:

```bash
git add README.md
git diff --cached
git commit -m "Update README"
```

## 6. Push And Open A Pull Request

Push the current task branch:

```bash
git branch --show-current
git push -u origin "$(git branch --show-current)"
```

Create a pull request from the current branch:

```bash
gh pr create --base main --fill
```

### Troubleshooting: A Pull Request Already Exists

> Skip this subsection if `gh pr create --base main --fill` creates the PR.

GitHub allows only one open pull request from the same branch into `main`. If a
PR already exists, open it instead of creating another one:

```bash
gh pr view --web
```

Push new commits to the same branch and the existing PR updates automatically.
Use a new branch for a different task.

If the PR is obsolete, confirm that it has no unique work before closing it:

```bash
gh pr close "$(git branch --show-current)" --delete-branch
```

## 7. Merge The Pull Request

> **BioAgent policy:** Only the principal repository administrator merges pull
> requests into `main`. Contributors create branches, open PRs, and review
> changes, but they do not run the merge command.

After review and successful tests, merge the PR associated with the current
branch:

```bash
gh pr merge --squash --delete-branch
```

No PR number is needed when the current branch has an open pull request.

### Troubleshooting: Pull Request Merge Conflicts

> Skip this subsection if `gh pr merge --squash --delete-branch` succeeds.

If GitHub says the merge cannot be cleanly created, update the task branch with
the latest `main`:

```bash
git fetch origin
git merge origin/main
```

Edit each conflicted file, choose the correct content, and remove Git's conflict
markers. Then finish the merge and update the PR:

```bash
git add README.md
git commit -m "Resolve README conflict with main"
git push
gh pr merge --squash --delete-branch
```

The `--auto` option can wait for reviews or checks, but it cannot resolve file
conflicts. If the PR duplicates work already merged, close it instead of
resolving an unnecessary conflict.

## 8. Update The Local Repository

Return to the latest `main` after the PR is merged:

```bash
git switch main
git pull --ff-only origin main
git status
```

The task is complete when `main` contains the change and the working tree is
clean.

## Team Responsibilities

The principal sets priorities and approves important architecture changes.
Team members implement focused tasks, run tests, and review pull requests. Keep
`main` stable and do not develop directly on it.

## Admin: Send a Change From dev/architecture to main

Do not open a PR from `dev/architecture` directly into `main`. The branches
intentionally have different pipeline trees, so that PR would show the missing
pipeline files as deletions.

First commit and push the change on `dev/architecture`:

```bash
git switch dev/architecture
git add <changed-files>
git diff --cached
git commit -m "Describe the change"
git push origin dev/architecture
git log -1 --oneline dev/architecture
```

Create a temporary branch from the latest `main`:

```bash
git switch main
git pull --ff-only origin main
git switch -c fix/copy-architecture-change
```

For a single file, copy it from `dev/architecture`:

```bash
git restore --source=origin/dev/architecture -- docs/dev_workflow.md
```

For a complete non-pipeline commit, cherry-pick its commit instead:

```bash
git cherry-pick <FEATURE_COMMIT_SHA>
```

Review the result and confirm that no pipeline files are changed:

```bash
git status
git diff origin/main...HEAD
git diff origin/main...HEAD -- pipelines/
```

Push the temporary branch and open a PR into `main`:

```bash
git push -u origin fix/copy-architecture-change
gh pr create --base main --head fix/copy-architecture-change --fill
```

After the PR is merged, update local branches and remove stale remote
references:

```bash
git switch main
git pull --ff-only origin main
git fetch --prune
git switch dev/architecture
git pull --ff-only origin dev/architecture
```

## Admin: Merge main Into dev/architecture Except pipelines

Use this workflow whenever `main` has new commits and
`dev/architecture` must keep its own `pipelines/` directory. Git cannot exclude
a path from a normal merge, so pause the merge before committing and restore
that directory from `dev/architecture`.

Start with a clean working tree and update both remote-tracking branches:

```bash
git status --short
git fetch origin
git switch dev/architecture
git pull --ff-only origin dev/architecture
```

Start the merge without creating its commit:

```bash
git merge --no-commit --no-ff origin/main
```

Keep the `dev/architecture` version of `pipelines/`. If the merge reports
pipeline conflicts, mark those conflicts as deleted first, then restore the
complete pipeline tree from the pre-merge `HEAD`:

```bash
git diff --name-only --diff-filter=U -z -- pipelines/ | \
  xargs -0 -r git rm --
git restore --source=HEAD --staged --worktree -- pipelines/
```

If Git reports conflicts outside `pipelines/`, resolve those files and stage
them with `git add`. Then verify that the merge contains no `pipelines/`
changes before committing:

```bash
git diff --name-only --diff-filter=U
git diff --cached -- pipelines/
git status
git commit -m "Merge main into dev/architecture excluding pipelines"
git push origin dev/architecture
```

The first verification command must print no unresolved files, and the second
must print no changes. To cancel the in-progress merge instead, run:

```bash
git merge --abort
```

Repeat the restore and verification steps during future merges from `main` when
`pipelines/` must remain unchanged. A normal merge without this step can
reintroduce `main`'s pipeline files or create conflicts.
