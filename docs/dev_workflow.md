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

## Team Responsibilities

The principal sets priorities and approves important architecture changes.
Team members use focused branches, implement and test tasks, and review pull
requests. Keep `main` stable and do not develop directly on it.






