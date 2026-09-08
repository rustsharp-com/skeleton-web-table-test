# Reconstructed C# / Rust table trial

Stage 2/6: **1.0.0**, demonstration date **2024-06**.
These dates and versions are simulated, not verified historical releases.
Git commit timestamps record the actual publication time.

| Version | Demonstration month | Added capability |
|---|---|---|
| 0.0.0 | 2023-06 | Text and numeric planes; table identity |
| 1.0.0 | 2024-06 | Row/column metadata and style references |

This stage contains 8 independent C#/Rust bindings in horizontal and
vertical layouts, with 64 required directed source-to-target pairs.
GitHub Actions runs 16 environments: Linux/Windows, .NET 8/10, Debug/Release,
and Rust 1.85/stable. Each environment uses 1,000 valid and 1,000 invalid seeded
inputs, fixed golden cases, return trips, available-version chains and mutation checks.
Cross-version pairs use accepted fixed fixture outputs; random cases exercise
local normalization and same-version language/layout parity.

## Run and inspect

Install Python 3.10+, .NET 8 SDK/runtime and Rust 1.85+ with a linker.

```sh
python tools/evolution_scaffold.py --check
python -m unittest discover -s tools -p 'test_*.py'
python tools/evolution.py --samples 1000
python tools/ci_summary.py
```

Open Actions, select this commit's run, then select an environment job. Its
summary shows expected/executed pairs, assertions, failures, seed and toolchains.
Download the environment artifact for summary.json, coverage.json, junit.xml,
failures.json, compatibility-losses.json and build logs. Missing coverage fails CI.
Change --seed to reproduce or explore inputs; failures.json records expected/actual
values and available input context. Build failures may be reported in failures.json
before a per-build log exists. Hosted status must be checked; this README claims no pass.

## Ownership and scope

Generated from the private central source. Changes belong in that source and
must be regenerated. publication/provenance.json records source identity and
input hashes; publication/recipe.py is the exact exporter. Run it with
--source PRIVATE_CHECKOUT --output NEW_DIRECTORY to regenerate all stages.
The recipe generates files locally and performs no Git operations that change state.

This tests reconstructed JSON table interchange and normalization. It does not
certify production bindings, XLSX fidelity, formula evaluation or browser rendering.
Private heritage, internal documents and Git history are not part of this export.
