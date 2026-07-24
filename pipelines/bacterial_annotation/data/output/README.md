# Mock bacterial annotation outputs

These files illustrate the output names and formats exposed by the
`bacterial_annotation` pipeline. They were created as deterministic fixtures;
Prokka was not run to produce them, and they must not be used for scientific
interpretation.

A real BioAgent run writes its results under the active session directory:

```text
runtime/sessions/<session_id>/artifacts/pipelines/bacterial_annotation/<run_id>/output/
```

The runtime also creates `prokka_outputs.zip`, containing Prokka's complete raw
output set. A ZIP fixture is intentionally not committed here.
