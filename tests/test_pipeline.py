from datetime import date

from mtg_rules_etl.pipeline import FetchedRules, RulesEtlPipeline
from mtg_rules_etl.repository import DuckDBRulesRepository


LEGACY_TEX = r"""	\chapter*{Introduction}
\addcontentsline{toc}{chapter}{Introduction}
\lettrine[lines=3, depth=0]{T}{ } his document is the ultimate authority. These rules are effective as of February 27, 2026.

Changes may have been made.

\chapter{Game Concepts}
\setcounter{section}{99}
\section{General}
\subsection*{100.1.}
These Magic rules apply.
"""


REMOTE_SAME_DATE = """Magic: The Gathering Comprehensive Rules

These rules are effective as of February 27, 2026.

Introduction

This document is the ultimate authority.

Changes may have been made.

Contents

1. Game Concepts
100. General
Glossary
Credits

1. Game Concepts
100. General
100.1.
These Magic rules apply.

Glossary
"""


REMOTE_NEW_DATE = REMOTE_SAME_DATE.replace("February 27, 2026", "June 19, 2026").replace(
    "These Magic rules apply.", "These Magic rules apply to any Magic game."
)


class FakeSource:
    def __init__(self, text: str):
        self.text = text

    def fetch_latest_rules_txt(self) -> FetchedRules:
        return FetchedRules(text=self.text, url="https://media.wizards.com/rules.txt")


class FakeCompiler:
    def __init__(self):
        self.compiled_paths = []
        self.cover_snapshots = []
        self.rules_snapshots = []

    def compile(self, main_tex_path):
        self.compiled_paths.append(main_tex_path)
        self.cover_snapshots.append(main_tex_path.read_text(encoding="utf-8"))
        self.rules_snapshots.append((main_tex_path.parent / "rules.tex").read_text(encoding="utf-8"))
        pdf_path = main_tex_path.with_suffix(".pdf")
        pdf_path.write_bytes(b"%PDF-1.4")
        return pdf_path


def test_pipeline_seeds_missing_database_then_skips_same_date(tmp_path):
    latex_path = tmp_path / "rules.tex"
    latex_path.write_text(LEGACY_TEX, encoding="utf-8")
    db_path = tmp_path / "rules.duckdb"

    result = RulesEtlPipeline(
        repository=DuckDBRulesRepository(db_path),
        source=FakeSource(REMOTE_SAME_DATE),
        latex_path=latex_path,
    ).run()

    assert result.status == "skipped"
    assert result.previous_effective_date == date(2026, 2, 27)
    assert result.current_effective_date == date(2026, 2, 27)
    assert latex_path.read_text(encoding="utf-8") == LEGACY_TEX
    assert result.cover_updated is False


def test_pipeline_updates_database_and_latex_when_date_changes(tmp_path, caplog):
    caplog.set_level("INFO")
    latex_path = tmp_path / "rules.tex"
    latex_path.write_text(LEGACY_TEX, encoding="utf-8")
    db_path = tmp_path / "rules.duckdb"

    result = RulesEtlPipeline(
        repository=DuckDBRulesRepository(db_path),
        source=FakeSource(REMOTE_NEW_DATE),
        latex_path=latex_path,
    ).run()

    assert result.status == "updated"
    assert result.previous_effective_date == date(2026, 2, 27)
    assert result.current_effective_date == date(2026, 6, 19)
    assert "These rules are effective as of June 19, 2026." in latex_path.read_text(encoding="utf-8")
    assert DuckDBRulesRepository(db_path).latest_effective_date() == date(2026, 6, 19)
    assert result.cover_updated is False
    assert any("pipeline_finished" in record.message for record in caplog.records)


def test_pipeline_updates_stale_cover_when_rules_date_is_already_current(tmp_path):
    latex_path = tmp_path / "rules.tex"
    latex_path.write_text(LEGACY_TEX, encoding="utf-8")
    cover_path = tmp_path / "mtg_rules.tex"
    cover_path.write_text(
        "Effective as of February 27, 2026\n"
        r"{\large\textsc{Effective as of February 27, 2026}}\par"
        "\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "rules.duckdb"
    repository = DuckDBRulesRepository(db_path)
    RulesEtlPipeline(
        repository=repository,
        source=FakeSource(REMOTE_NEW_DATE),
        latex_path=latex_path,
    ).run()

    result = RulesEtlPipeline(
        repository=repository,
        source=FakeSource(REMOTE_NEW_DATE),
        latex_path=latex_path,
        cover_path=cover_path,
    ).run()

    assert result.status == "skipped"
    assert result.latex_updated is False
    assert result.cover_updated is True
    cover = cover_path.read_text(encoding="utf-8")
    assert "Effective as of February 27, 2026" not in cover
    assert cover.count("Effective as of June 19, 2026") == 2


def test_pipeline_compiles_main_tex_even_when_data_load_is_skipped(tmp_path, caplog):
    caplog.set_level("INFO")
    latex_dir = tmp_path / "latex"
    latex_dir.mkdir()
    latex_path = latex_dir / "rules.tex"
    latex_path.write_text(LEGACY_TEX, encoding="utf-8")
    cover_path = latex_dir / "mtg_rules.tex"
    cover_path.write_text("Effective as of February 27, 2026\n", encoding="utf-8")
    compiler = FakeCompiler()

    result = RulesEtlPipeline(
        repository=DuckDBRulesRepository(tmp_path / "rules.duckdb"),
        source=FakeSource(REMOTE_SAME_DATE),
        latex_path=latex_path,
        cover_path=cover_path,
        compiler=compiler,
    ).run()

    assert result.status == "skipped"
    assert result.pdf_compiled is True
    assert result.pdf_path == latex_dir / "mtg_rules.pdf"
    assert compiler.compiled_paths == [cover_path]
    assert any("latex_compile_started" in record.message for record in caplog.records)
    assert any("latex_compile_finished" in record.message for record in caplog.records)


def test_pipeline_compiles_after_updated_latex_sources_are_published(tmp_path):
    latex_dir = tmp_path / "latex"
    latex_dir.mkdir()
    latex_path = latex_dir / "rules.tex"
    latex_path.write_text(LEGACY_TEX, encoding="utf-8")
    cover_path = latex_dir / "mtg_rules.tex"
    cover_path.write_text("Effective as of February 27, 2026\n", encoding="utf-8")
    compiler = FakeCompiler()

    result = RulesEtlPipeline(
        repository=DuckDBRulesRepository(tmp_path / "rules.duckdb"),
        source=FakeSource(REMOTE_NEW_DATE),
        latex_path=latex_path,
        cover_path=cover_path,
        compiler=compiler,
    ).run()

    assert result.status == "updated"
    assert result.pdf_compiled is True
    assert "Effective as of June 19, 2026" in compiler.cover_snapshots[0]
    assert "These Magic rules apply to any Magic game." in compiler.rules_snapshots[0]
