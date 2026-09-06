from pathlib import Path
import subprocess

import pytest

from mtg_rules_etl.compiler import LatexCompilationError, SubprocessLatexCompiler


def test_compiler_rejects_an_unsupported_engine():
    with pytest.raises(ValueError, match="Unsupported LaTeX engine"):
        SubprocessLatexCompiler(executable="powershell")


def test_compiler_runs_two_passes_inside_latex_directory(tmp_path, monkeypatch):
    latex_dir = tmp_path / "latex"
    latex_dir.mkdir()
    main_tex = latex_dir / "mtg_rules.tex"
    main_tex.write_text(r"\documentclass{book}\begin{document}\end{document}", encoding="utf-8")
    calls: list[tuple[list[str], dict]] = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        (latex_dir / "mtg_rules.pdf").write_bytes(b"%PDF-1.4")
        return subprocess.CompletedProcess(command, 0, stdout="compiled", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    pdf_path = SubprocessLatexCompiler().compile(main_tex)

    assert pdf_path == latex_dir / "mtg_rules.pdf"
    assert len(calls) == 2
    for command, kwargs in calls:
        assert command == [
            "pdflatex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-file-line-error",
            "mtg_rules.tex",
        ]
        assert kwargs["cwd"] == latex_dir
        assert kwargs["shell"] is False
        assert kwargs["timeout"] == 300


def test_compiler_rejects_a_non_tex_main_file(tmp_path):
    main_file = tmp_path / "mtg_rules.txt"
    main_file.write_text("not latex", encoding="utf-8")

    with pytest.raises(ValueError, match=r"\.tex"):
        SubprocessLatexCompiler().compile(main_file)


def test_compiler_reports_a_missing_main_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="main LaTeX source"):
        SubprocessLatexCompiler().compile(tmp_path / "missing.tex")


def test_compiler_reports_a_missing_engine(tmp_path, monkeypatch):
    main_tex = tmp_path / "mtg_rules.tex"
    main_tex.write_text("latex", encoding="utf-8")

    def missing_engine(*args, **kwargs):
        raise FileNotFoundError("pdflatex")

    monkeypatch.setattr(subprocess, "run", missing_engine)

    with pytest.raises(LatexCompilationError, match="pdflatex.*not found"):
        SubprocessLatexCompiler().compile(main_tex)


def test_compiler_reports_nonzero_exit_with_bounded_diagnostics(tmp_path, monkeypatch):
    main_tex = tmp_path / "mtg_rules.tex"
    main_tex.write_text("latex", encoding="utf-8")

    def failed_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="x" * 10_000, stderr="LaTeX error")

    monkeypatch.setattr(subprocess, "run", failed_run)

    with pytest.raises(LatexCompilationError) as error:
        SubprocessLatexCompiler().compile(main_tex)

    assert "LaTeX error" in str(error.value)
    assert len(str(error.value)) < 5_000


def test_compiler_reports_timeout(tmp_path, monkeypatch):
    main_tex = tmp_path / "mtg_rules.tex"
    main_tex.write_text("latex", encoding="utf-8")

    def timed_out(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timed_out)

    with pytest.raises(LatexCompilationError, match="timed out after 300 seconds"):
        SubprocessLatexCompiler().compile(main_tex)


def test_compiler_requires_the_pdf_artifact(tmp_path, monkeypatch):
    main_tex = tmp_path / "mtg_rules.tex"
    main_tex.write_text("latex", encoding="utf-8")

    def successful_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="compiled", stderr="")

    monkeypatch.setattr(subprocess, "run", successful_run)

    with pytest.raises(LatexCompilationError, match="did not produce"):
        SubprocessLatexCompiler().compile(main_tex)
