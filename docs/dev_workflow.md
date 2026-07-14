# BioAgent Development Workflow

Use this branch-and-pull-request workflow when developing BioAgent with the team.
The example below adds this documentation file to the project.

## 1. Prepare The Repository

Clone the repository once:

```bash
git clone https://github.com/ai2lifescience/BioAgent.git
cd BioAgent
```

Before every new task, update the stable branch:

```bash
git switch main
git pull --ff-only origin main
```

## 2. Create A Task Branch

Use a short branch name that describes the task:

```bash
git switch -c docs/git-workflow-example
```

Examples for other work:

```text/
feature/add-uniprot-tool
fix/pipeline-input-path
docs/update-web-guide
```

## 3. Make And Review Changes

Edit the files, then inspect the workspace:

```bash
git status --short
git diff
```

For this example, the new file is `docs/dev_workflow.md`.

## 4. Run Tests

Run the checks before committing:

```bash
python -m evals.smoke_architecture
python -m evals.smoke_session_artifacts
```

Add focused tests for new behavior when smoke checks are not enough.

## 5. Commit The Change

Stage only the files that belong to the task:

```bash
git add docs/dev_workflow.md
git diff --cached
git commit -m "Add team development workflow"
```

## 6. Push And Open A Pull Request

Push the task branch:

```bash
git push -u origin docs/git-workflow-example
```

Open a pull request with GitHub CLI:

```bash
gh pr create \
  --base main \
  --head docs/git-workflow-example \
  --title "Add team development workflow" \
  --body "Documents the BioAgent branch, test, review, and merge workflow."
```

A teammate reviews the files and tests. Address requested changes on the same
branch, commit them, and push again; the pull request updates automatically.

## 7. Merge The Pull Request

After approval and successful tests, merge it on GitHub or run:

```bash
gh pr merge --squash --delete-branch
```

### Resolve A Merge Conflict

If GitHub says the merge cannot be cleanly created, first check whether the pull
request is duplicate or no longer needed. Close a redundant pull request:

```bash
gh pr close <PR_NUMBER> --delete-branch
```

For a required pull request, merge the latest `main` into its task branch:

```bash
git switch <TASK_BRANCH>
git fetch origin
git merge origin/main
```

Edit each conflicted file, choose the correct content, and remove Git's conflict
markers. Then update the pull request and retry the merge:

```bash
git add <CONFLICTED_FILE>
git commit -m "Resolve merge conflict with main"
git push
gh pr merge <PR_NUMBER> --squash --delete-branch
```

The `--auto` option can wait for reviews or checks, but it cannot resolve file
conflicts.

Use repository branch protection if review must be mandatory.

## 8. Update The Local Repository

Return to the latest `main` after the merge:

```bash
git switch main
git pull --ff-only origin main
git branch --list
git status
```

The task is complete when `main` contains the change and the working tree is
clean.

### Local Changes Block Pulling

Git refuses to pull when an incoming commit would overwrite uncommitted local
changes:

```text
error: Your local changes would be overwritten by merge
```

Inspect the changes before choosing how to proceed:

```bash
git status
git diff
```

#### Keep The Changes

The recommended solution is to move the work onto a task branch:

```bash
git switch -c docs/update-readme
git add README.md
git commit -m "Update README"

git switch main
git pull --ff-only origin main

git switch docs/update-readme
git rebase main
```

If the rebase reports a conflict, edit the conflicted file, remove the conflict
markers, and continue:

```bash
git add README.md
git rebase --continue
```

Push the updated task branch when it is ready:

```bash
git push -u origin docs/update-readme
```

#### Stash Unfinished Changes

Use a stash when the work is not ready to commit:

```bash
git stash push -u -m "Temporary local work"
git pull --ff-only origin main
git switch -c docs/update-readme
git stash pop
```

Resolve any conflicts from `git stash pop`, then commit the work normally.

#### Discard Unwanted Changes

Only discard a local edit after confirming that it is not needed:

```bash
git restore README.md
git pull --ff-only origin main
```

Avoid this problem by updating `main` and creating a task branch before editing:

```bash
git switch main
git pull --ff-only origin main
git switch -c feature/my-task
```

## Team Responsibilities

The principal sets priorities and approves important architecture changes.
Team members use focused branches, implement and test tasks, and review pull
requests. Keep `main` stable and do not develop directly on it.
