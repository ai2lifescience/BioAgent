# Mock bacterial annotation outputs

These files illustrate the output names and formats exposed by the
`bacterial_annotation` pipeline. The files in this directory represent the
normalized Prokka branch. They were created as deterministic fixtures; Prokka
was not run, and they must not be used for scientific interpretation.

A real BioAgent run writes its results under the active session directory:

```text
runtime/sessions/<session_id>/artifacts/pipelines/bacterial_annotation/<run_id>/output/
```

The runtime also creates `annotation_outputs.zip`, containing the selected
annotator's complete raw output set. A ZIP fixture is intentionally not
committed here. Representative Bakta fixtures are in `bakta/`.
