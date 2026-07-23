# Pipeline Results Skill

## Purpose

Collect and display outputs from the latest completed pipeline run only after
the user explicitly requests a review.

## Workflow

1. Use session artifacts from completed `pipeline_runner` calls.
2. Select the latest run, optionally filtered by pipeline name.
3. Call `pipeline_results_collect` to build a ZIP and structured previews.
4. Return key metrics, table previews, an output manifest, and result figures.

## Rules

- Do not rerun the pipeline.
- Do not collect artifacts from another session.
- State clearly when the session has no completed pipeline outputs.
- Keep raw files available in the ZIP bundle.
