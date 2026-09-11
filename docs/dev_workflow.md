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

## Admin: Merge All dev/architecture Changes Into main Except pipelines

Use this workflow when all development changes are ready for `main`. It
combines the branches on a temporary branch based on `main`, then restores
`main`'s complete `pipelines/` tree before opening a PR. Cherry-pick is not
required for this full synchronization.

### Normal path

1. Commit your changes, pull the latest `dev/architecture`, and push. An `M`
   line means the file is not committed; pull and push transfer commits only.
   Finish with a clean working tree:

   ```bash
   git switch dev/architecture
   git status --short
   git add .
   git diff --cached
   git commit -m "Describe the finished change"
   git status --short
   git pull --ff-only origin dev/architecture
   git push origin dev/architecture
   git status --short
   ```

   The first status check is for review. The status check after `git commit`
   should print nothing before you pull and push. Run `git add .` from the
   repository root only when every uncommitted, unignored change belongs in
   this commit; review `git diff --cached` before committing.

2. Create a temporary branch from the latest `main` and merge all dev changes
   without committing:

   ```bash
   git fetch origin
   git switch -c sync/dev-to-main origin/main
   git merge --no-commit --no-ff origin/dev/architecture
   ```

3. If Git reports `Already up to date.`, stop: there is no merge to
   commit. If `git diff --name-only --diff-filter=U` prints nothing, restore
   `main`'s pipeline tree from the starting `HEAD`:

   ```bash
   git restore --source=HEAD --staged --worktree -- pipelines/
   ```

4. Review the staged result and run the checks from step 4 above:

   ```bash
   git diff --cached -- pipelines/
   git diff --cached
   git status
   ```

   The first command must print nothing. If the merge reported conflicts, stop
   this normal path and use the troubleshooting section at the end instead.

5. Commit the merge and check the committed pipeline diff:

   ```bash
   git commit -m "Merge dev architecture changes while preserving main pipelines"
   git diff --exit-code origin/main...HEAD -- pipelines/
   ```

   The last command must exit successfully and print nothing. Then publish the
   temporary branch and open its PR into `main`:

   ```bash
   git push -u origin sync/dev-to-main
   gh pr create --base main --head sync/dev-to-main --fill
   ```

   Only the principal repository administrator merges the PR. After it is
   merged, update local `main` and follow the merge-back workflow below.

## Admin: Send Selected Files or Commits From dev/architecture to main

Use this alternative when only part of the dev work is ready. A file copy
transfers one file's current contents; cherry-pick transfers one complete
commit. Neither method should be used by opening a PR directly from
`dev/architecture`, because its missing pipeline folders would appear as
deletions.

### Normal path

1. Commit and push the selected change on `dev/architecture`:

   ```bash
   git switch dev/architecture
   git add <changed-files>
   git diff --cached
   git commit -m "Describe the change"
   git push origin dev/architecture
   git log -1 --oneline dev/architecture
   ```

2. Create a clean branch from the latest `main`:

   ```bash
   git fetch origin
   git switch -c fix/copy-architecture-change origin/main
   ```

3. Choose one transfer method.

   To copy one file:

   ```bash
   git restore --source=origin/dev/architecture -- docs/dev_workflow.md
   git diff -- docs/dev_workflow.md
   git add docs/dev_workflow.md
   git diff --cached
   git commit -m "Update development workflow documentation"
   ```

   To transfer one complete non-pipeline commit, use this instead of the file
   copy block:

   ```bash
   git cherry-pick <FEATURE_COMMIT_SHA>
   ```

4. Review the committed result:

   ```bash
   git status
   git diff origin/main...HEAD
   git diff --exit-code origin/main...HEAD -- pipelines/
   ```

   The last command must exit successfully and print nothing. If a copy or
   cherry-pick reports a conflict, stop this normal path and use the
   troubleshooting section at the end.

5. Push the temporary branch and open its PR:

   ```bash
   git push -u origin fix/copy-architecture-change
   gh pr create --base main --head fix/copy-architecture-change --fill
   ```

   After the PR is merged, update local `main` and follow the merge-back
   workflow below.

## Admin: Merge main Into dev/architecture Except pipelines

Use this workflow after `main` advances. It keeps the entire
`pipelines/` directory exactly as it exists on `dev/architecture`.

### Normal path

1. Commit or stash unfinished work. Start with a clean working tree and update
   the branch:

   ```bash
   git status --short
   git fetch origin
   git switch dev/architecture
   git pull --ff-only origin dev/architecture
   ```

2. Merge `main` without creating its commit:

   ```bash
   git merge --no-commit --no-ff origin/main
   ```

3. If Git reports `Already up to date.`, stop: there is no merge to
   commit. If `git diff --name-only --diff-filter=U` prints nothing, restore
   dev's pipeline tree from the pre-merge `HEAD`:

   ```bash
   git restore --source=HEAD --staged --worktree -- pipelines/
   ```

4. Review the staged result and run the checks from step 4 above:

   ```bash
   git diff --cached -- pipelines/
   git diff --cached
   git status
   ```

   The first command must print nothing. If the merge reported conflicts, stop
   this normal path and use the troubleshooting section at the end instead.

5. Commit the merge and verify that the committed result has no pipeline diff:

   ```bash
   git commit -m "Merge main into dev/architecture excluding pipelines"
   git diff --exit-code origin/main...HEAD -- pipelines/
   git push origin dev/architecture
   ```

   The diff command must exit successfully and print nothing.

## After Either PR Is Merged

Update local branches and remove stale remote references:

```bash
git switch main
git pull --ff-only origin main
git fetch --prune
git switch dev/architecture
git pull --ff-only origin dev/architecture
```

To compare the published branches outside `pipelines/`:

```bash
git diff origin/main origin/dev/architecture -- . ':!pipelines/'
```

No output means all non-pipeline files match.

## Troubleshooting: Merge Conflicts

Use this section only when a command in a normal path reports a conflict.
Do not run these steps after a normal merge with no unresolved paths.

### Pipeline conflicts while merging dev into main

If `git merge --no-commit --no-ff origin/dev/architecture` reports
pipeline conflicts, leave the merge in progress and run:

```bash
git diff --name-only --diff-filter=U -- pipelines/
git diff --name-only --diff-filter=U -z -- pipelines/ | \
  xargs -0 -r git rm --
git restore --source=HEAD --staged --worktree -- pipelines/
```

Here `HEAD` is the temporary branch based on `main`, so this restores
`main`'s pipeline tree. Resolve any conflicts outside `pipelines/` by
editing the files, removing conflict markers, and running `git add`.

Then resume at **Step 4** of “Merge All dev/architecture Changes Into main
Except pipelines”:

```bash
git diff --name-only --diff-filter=U
git diff --cached -- pipelines/
git diff --cached
git status
```

The first two checks must print nothing before you commit.

### Pipeline conflicts while merging main into dev

If `git merge --no-commit --no-ff origin/main` reports pipeline conflicts,
leave the merge in progress and run:

```bash
git diff --name-only --diff-filter=U -- pipelines/
git diff --name-only --diff-filter=U -z -- pipelines/ | \
  xargs -0 -r git rm --
git restore --source=HEAD --staged --worktree -- pipelines/
```

Here `HEAD` is the pre-merge `dev/architecture` commit, so this restores
dev's pipeline tree. Resolve any conflicts outside `pipelines/`, then resume
at **Step 4** of “Merge main Into dev/architecture Except pipelines”:

```bash
git diff --name-only --diff-filter=U
git diff --cached -- pipelines/
git diff --cached
git status
```

The first two checks must print nothing before you commit.

### Cherry-pick conflicts

If `git cherry-pick <FEATURE_COMMIT_SHA>` reports a conflict:

```bash
git status
```

Resolve the listed files, remove conflict markers, stage them, and continue:

```bash
git add <resolved-files>
git cherry-pick --continue
```

To abandon the cherry-pick instead:

```bash
git cherry-pick --abort
```

After any troubleshooting path completes, return to the normal path at the
step named above. If you need to cancel an in-progress merge, use:

```bash
git merge --abort
```
