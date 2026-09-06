from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


SUPPORTED_LATEX_ENGINES = ("pdflatex", "xelatex", "lualatex")
DIAGNOSTIC_CHARACTER_LIMIT = 4_000


class LatexCompilationError(RuntimeError):
    """Raised when a LaTeX engine cannot produce the expected PDF artifact."""


class LatexCompiler(Protocol):
    def compile(self, main_tex_path: str | Path) -> Path:
        raise NotImplementedError


@dataclass(frozen=True)
class SubprocessLatexCompiler:
    executable: str = "pdflatex"
    passes: int = 2
    timeout_seconds: int = 300

    def __post_init__(self) -> None:
        if self.executable not in SUPPORTED_LATEX_ENGINES:
            raise ValueError(f"Unsupported LaTeX engine: {self.executable}")
        if self.passes < 1:
            raise ValueError("LaTeX compilation passes must be at least 1.")
        if self.timeout_seconds < 1:
            raise ValueError("LaTeX compilation timeout must be at least 1 second.")

    def compile(self, main_tex_path: str | Path) -> Path:
        main_tex = Path(main_tex_path)
        if main_tex.suffix.lower() != ".tex":
            raise ValueError("The main LaTeX source must use the .tex extension.")
        if not main_tex.is_file():
            raise FileNotFoundError(f"The main LaTeX source does not exist: {main_tex}")

        command = [
            self.executable,
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-file-line-error",
            main_tex.name,
        ]
        for pass_number in range(1, self.passes + 1):
            completed = self._run_pass(command, main_tex.parent, pass_number)
            if completed.returncode != 0:
                diagnostics = _diagnostic_tail(completed.stdout, completed.stderr)
                raise LatexCompilationError(
                    f"{self.executable} failed on pass {pass_number} "
                    f"with exit code {completed.returncode}. Diagnostics: {diagnostics}"
                )

        pdf_path = main_tex.with_suffix(".pdf")
        if not pdf_path.is_file():
            raise LatexCompilationError(
                f"{self.executable} completed but did not produce the expected PDF: {pdf_path}"
            )
        return pdf_path

    def _run_pass(
        self,
        command: list[str],
        working_directory: Path,
        pass_number: int,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                command,
                cwd=working_directory,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
                shell=False,
            )
        except FileNotFoundError as exc:
            raise LatexCompilationError(
                f"LaTeX engine '{self.executable}' was not found. Install it or select another engine."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise LatexCompilationError(
                f"{self.executable} timed out after {self.timeout_seconds} seconds "
                f"on pass {pass_number}."
            ) from exc


def _diagnostic_tail(stdout: str | None, stderr: str | None) -> str:
    diagnostics = "\n".join(part for part in (stdout, stderr) if part).strip()
    if not diagnostics:
        return "No diagnostic output was produced."
    return diagnostics[-DIAGNOSTIC_CHARACTER_LIMIT:]
