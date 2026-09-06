from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from mtg_rules_etl import cli
from mtg_rules_etl.cli import create_parser
from mtg_rules_etl.compiler import SubprocessLatexCompiler


def test_cli_defaults_use_latex_directory():
    args = create_parser().parse_args([])

    assert args.rules_tex == "latex/rules.tex"
    assert args.cover_tex == "latex/mtg_rules.tex"
    assert args.latex_engine == "pdflatex"
    assert args.compile_timeout == 300
    assert args.skip_compile is False


def test_cli_can_explicitly_skip_pdf_compilation():
    args = create_parser().parse_args(["--skip-compile"])

    assert args.skip_compile is True


@pytest.mark.parametrize(
    ("arguments", "expects_compiler"),
    [([], True), (["--skip-compile"], False)],
)
def test_cli_wires_pdf_compilation_by_default(monkeypatch, arguments, expects_compiler):
    captured = {}

    class FakePipeline:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def run(self):
            return SimpleNamespace(
                status="skipped",
                previous_effective_date=date(2026, 8, 7),
                current_effective_date=date(2026, 8, 7),
                latex_updated=False,
                cover_updated=False,
                pdf_compiled=expects_compiler,
                pdf_path=Path("latex/mtg_rules.pdf") if expects_compiler else None,
            )

    monkeypatch.setattr(cli, "RulesEtlPipeline", FakePipeline)
    monkeypatch.setattr("sys.argv", ["mtg-rules-etl", *arguments])

    assert cli.main() == 0
    if expects_compiler:
        assert isinstance(captured["compiler"], SubprocessLatexCompiler)
    else:
        assert captured["compiler"] is None
