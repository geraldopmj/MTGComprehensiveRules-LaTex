from __future__ import annotations

import argparse
from pathlib import Path

from .compiler import SUPPORTED_LATEX_ENGINES, SubprocessLatexCompiler
from .logging_config import configure_logging
from .pipeline import RulesEtlPipeline
from .repository import DuckDBRulesRepository
from .source import DEFAULT_RULES_PAGE_URL, OfficialRulesSource


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Update MTG Comprehensive Rules in DuckDB and LaTeX.")
    parser.add_argument("--db", default="data/mtg_rules.duckdb", help="DuckDB database path.")
    parser.add_argument("--rules-tex", default="latex/rules.tex", help="Path to the LaTeX rules body.")
    parser.add_argument("--cover-tex", default="latex/mtg_rules.tex", help="Path to the LaTeX main/cover file.")
    parser.add_argument("--rules-page", default=DEFAULT_RULES_PAGE_URL, help="Official rules page URL.")
    parser.add_argument(
        "--latex-engine",
        choices=SUPPORTED_LATEX_ENGINES,
        default="pdflatex",
        help="LaTeX engine used to compile the PDF.",
    )
    parser.add_argument(
        "--compile-timeout",
        type=_positive_integer,
        default=300,
        help="Maximum seconds allowed for each LaTeX compilation pass.",
    )
    parser.add_argument(
        "--skip-compile",
        action="store_true",
        help="Publish the data and LaTeX sources without compiling the PDF.",
    )
    return parser


def main() -> int:
    args = create_parser().parse_args()

    configure_logging()
    compiler = None
    if not args.skip_compile:
        compiler = SubprocessLatexCompiler(
            executable=args.latex_engine,
            timeout_seconds=args.compile_timeout,
        )
    pipeline = RulesEtlPipeline(
        repository=DuckDBRulesRepository(Path(args.db)),
        source=OfficialRulesSource(args.rules_page),
        latex_path=Path(args.rules_tex),
        cover_path=Path(args.cover_tex),
        compiler=compiler,
    )
    result = pipeline.run()
    print(
        f"{result.status}: previous={result.previous_effective_date} "
        f"current={result.current_effective_date} latex_updated={result.latex_updated} "
        f"cover_updated={result.cover_updated} pdf_compiled={result.pdf_compiled} "
        f"pdf_path={result.pdf_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
