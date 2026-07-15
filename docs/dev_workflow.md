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

## Admin: Copy One File From Another Branch

Use this when the repository administrator needs to bring only one file from
another branch directly into `main`. Do not use this if all changes on the
source branch should be merged; use a normal pull request or branch merge
instead.

Start from the latest `main`:

```bash
git switch main
git pull --ff-only origin main
```

Fetch the source branch:

```bash
git fetch origin dev/architecture
```

This fetch command does not overwrite local files, staged files, local commits,
or the current branch. It only downloads remote branch data into Git.

Copy only `README.md` from the source branch:

```bash
git restore --source=origin/dev/architecture -- README.md
```

The `git restore` command is the command that changes the local `README.md`.
If `README.md` already has uncommitted local edits, commit or stash them before
running it.

Review, commit, and push the single-file change directly to `main`:

```bash
git status --short
git diff -- README.md
git add README.md
git commit -m "Update README from dev architecture branch"
git push origin main
```

## Admin: Copy A Fix From dev/architecture Into main

Use this workflow when a fix was developed on `dev/architecture`, but only that
fix—not every difference between the branches—should be added to `main`. A
cherry-pick preserves files that exist only on `main`, such as
`pipelines/molecular_meta_wdl/`.

First, commit and push the fix on `dev/architecture`:

```bash
git switch dev/architecture
git add <changed-files>
git diff --cached
git commit -m "Describe the fix"
git push origin dev/architecture
```

Record the new commit ID:

```bash
git log -1 --oneline dev/architecture
```

Then create a task branch from the latest `main` and copy that commit onto it:

```bash
git switch main
git pull --ff-only origin main
git switch -c fix/copy-architecture-fix
git cherry-pick <FIX_COMMIT_SHA>
```

Review the result before publishing it:

```bash
git status
git diff origin/main...HEAD
```

Push the task branch and open a pull request into `main`:

```bash
git push -u origin fix/copy-architecture-fix
gh pr create --base main --head fix/copy-architecture-fix --fill
```

Do not merge all of `dev/architecture` into `main` when only one fix is needed.
The branches may have different files and squash-diverged histories.
