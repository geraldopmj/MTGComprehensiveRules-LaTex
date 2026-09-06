# MTG Rules ETL specification

## Context and current behavior

The batch pipeline uses Pipe-and-Filter with Ports and Adapters:

1. `OfficialRulesSource` discovers and downloads the official TXT release in memory.
2. The parsers validate and transform the TXT into `RulesDocument`.
3. `DuckDBRulesRepository` stores versioned groups and sections.
4. The LaTeX renderer publishes the rules body and updates the main document date.

Before this change, the CLI defaults already targeted `latex/rules.tex` and
`latex/mtg_rules.tex`, but legacy duplicate `.tex` files also remained in the
repository root. The pipeline stopped after publishing the LaTeX sources; it did
not compile the final PDF. The existing 11-test suite is the passing baseline for
parsing, persistence, rendering, source validation, CLI paths, and orchestration.

## Scope

- Keep every maintained LaTeX source under `latex/` and remove the obsolete root
  duplicates.
- Compile `latex/mtg_rules.tex` after the source files are ready, including an
  idempotent run whose remote version is already stored.
- Produce `latex/mtg_rules.pdf` and report compilation in the CLI result and
  structured lifecycle logs.
- Preserve existing extraction, transformation, validation, persistence, and
  rendering contracts.

Non-goals: change the rule parser, download remote `.tex` files, add scheduling,
or introduce a Python LaTeX dependency.

## Functional contracts

- **S-001 — Output location:** CLI defaults shall keep the database in `data/`
  and all LaTeX source and PDF artifacts in `latex/`.
- **S-002 — Compilation adapter:** the external LaTeX engine shall run with
  `latex/` as its working directory and receive only the main `.tex` filename,
  so included files, images, auxiliary files, and the PDF stay together.
- **S-003 — Complete document:** the default engine shall run enough passes to
  resolve the table of contents and cross-references (two passes by default).
- **S-004 — Idempotent orchestration:** compilation shall also run after a
  `skipped` data load, allowing a missing or stale PDF to be rebuilt safely.
- **S-005 — Explicit failures:** a missing engine, timeout, non-zero exit code,
  missing main source, or absent PDF after a successful process shall fail the
  pipeline with an actionable exception. Partial success shall not be reported as
  complete.
- **S-006 — Optional application port:** direct library callers may omit the
  compiler port to preserve the existing data-only use case; the CLI shall wire
  the compiler by default and may explicitly skip it for diagnostics.

## Non-functional, logging, and recovery contracts

- Invoke the compiler with an argument list and `shell=False`; never interpolate
  a user value into a shell command.
- Bound each compiler pass with a configurable positive timeout.
- Keep compiler output out of normal logs. On failure, include only a bounded
  diagnostic tail and never include source document contents.
- Emit one start and one success event for compilation, correlated with the
  pipeline `run_id`; the existing pipeline failure event owns error logging.
- A failed compilation may leave updated DuckDB and `.tex` sources. A rerun is
  the recovery path because compilation also occurs when loading is skipped.

## Security and privacy decision

Applicable OWASP risks are injection, software/data integrity, security
misconfiguration, logging failures, and mishandled exceptional conditions.
Controls are: no shell execution, a CLI allowlist of supported engine names,
explicit `.tex` input validation, bounded execution time, checked return codes,
bounded diagnostics, and existing HTTPS source-host allowlists. Authentication,
authorization, cryptography, and tenant isolation are not applicable to this local
single-user batch job.

LGPD does not apply to the changed flow: it processes public rules text and local
artifact paths, not personal or behavioral data. Logs continue to exclude rule
contents and secrets.

## Acceptance criteria and test mapping

| Rule | Acceptance criterion | Test | Code area | Documentation |
| --- | --- | --- | --- | --- |
| S-001 | Defaults and maintained `.tex` files resolve under `latex/` | `tests/test_cli.py` plus repository tree check | `mtg_rules_etl/cli.py` | README Data Flow / Run |
| S-002 | Compiler uses the main file's parent as `cwd` and emits the PDF there | `tests/test_compiler.py` | `mtg_rules_etl/compiler.py` | README Compile stage |
| S-003 | Default compilation performs two successful passes | `tests/test_compiler.py` | `mtg_rules_etl/compiler.py` | README How It Works |
| S-004 | A skipped load still invokes the compiler | `tests/test_pipeline.py` | `mtg_rules_etl/pipeline.py` | README recovery flow |
| S-005 | Missing engine and failed command raise actionable errors | `tests/test_compiler.py` | `mtg_rules_etl/compiler.py` | README troubleshooting |
| S-006 | CLI enables compilation by default and exposes an explicit opt-out | `tests/test_cli.py` | `mtg_rules_etl/cli.py` | README Run options |

