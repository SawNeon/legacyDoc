"""End-to-end smoke test against a real provider API.

The test suite uses provider doubles, which validates orchestration but never
exercises the adapters themselves. This command does, without touching the
database, so it can run before any infrastructure exists.

    python -m legacydoc_cli.smoke
    python -m legacydoc_cli.smoke path/to/file.py --plan pro --format markdown
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

from legacydoc_agents import DocumentationPipeline, PipelineOptions
from legacydoc_core.errors import LegacyDocError
from legacydoc_core.plans import PlanTier, get_plan
from legacydoc_core.settings import Settings
from legacydoc_exporters import ExporterFactory
from legacydoc_parsing import build_chunks, detect_language, parse_file
from legacydoc_parsing.languages import LanguageInfo
from legacydoc_providers.catalog import get_model_spec
from legacydoc_providers.router import AgentRole, CallRecord, ProviderRouter

from legacydoc_cli.console import Style, section

SAMPLE_SOURCE = '''\
"""Shopping cart module."""


class Cart:
    def __init__(self, customer_id):
        self.customer_id = customer_id
        self.items = []

    def add(self, item, quantity):
        if quantity <= 0:
            raise ValueError("quantity must be positive")

        for _ in range(quantity):
            self.items.append(item)

        return len(self.items)

    def remove(self, item):
        if item not in self.items:
            return False
        self.items.remove(item)
        return True


def calculate_total(items, discount=0.0):
    if discount < 0 or discount > 1:
        raise ValueError("invalid discount")

    total = sum(item.price for item in items)
    return total * (1 - discount)
'''

SAMPLE_PATH = "example/cart.py"
READER_SAMPLE_LIMIT = 12000


def load_settings() -> Settings:
    """Fill in the database and JWT values this command never uses."""
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    os.environ.setdefault("JWT_SECRET_KEY", "smoke-test-unused-" + "x" * 24)

    return Settings()  # type: ignore[call-arg]


def report_providers(settings: Settings) -> bool:
    section("1. Configured providers")
    configured = settings.configured_providers()

    if not configured:
        print(Style.failure("  No provider key found."))
        print("  Set OPENAI_API_KEY in .env and run again.")
        return False

    for name in sorted(configured):
        print(f"  {Style.success('OK')}  {name}")

    if len(configured) == 1:
        print(
            Style.warning(
                "  Warning: a single provider means no fallback chain. If it fails, the job fails."
            )
        )

    return True


def report_routes(router: ProviderRouter) -> None:
    section("2. Effective route per agent")

    for role in AgentRole:
        chain = router.resolve_chain(role)
        primary = chain[0]
        fallbacks = f" (fallbacks: {len(chain) - 1})" if len(chain) > 1 else ""
        print(f"  {str(role):11} -> {primary.provider}/{primary.model}{fallbacks}")


def load_source(file_argument: str | None) -> tuple[str, str] | None:
    section("3. Parsing")

    if not file_argument:
        print(Style.dim("  (built-in sample; pass a path to use your own code)"))
        return SAMPLE_SOURCE, SAMPLE_PATH

    path = Path(file_argument)

    if not path.is_file():
        print(Style.failure(f"  File not found: {path}"))
        return None

    return path.read_text(encoding="utf-8", errors="replace"), path.as_posix()


def report_parsing(path: str, source: str, chunk_tokens: int) -> LanguageInfo | None:
    language = detect_language(path)

    if language is None:
        print(Style.failure(f"  Unsupported extension: {path}"))
        return None

    parsed = parse_file(path, source, language)
    chunks = build_chunks(parsed, max_tokens_per_chunk=chunk_tokens)

    print(f"  file     : {path}")
    print(f"  language : {language.display_name}")
    print(f"  symbols  : {len(parsed.symbols)}")
    print(f"  chunks   : {len(chunks)}")

    if parsed.parse_failed:
        print(Style.warning("  Warning: grammar unavailable; fell back to line chunking."))
    elif not parsed.symbols:
        print(Style.warning("  Warning: no symbols recognised; fell back to line chunking."))

    for symbol in parsed.symbols[:12]:
        owner = f" in {symbol.parent}" if symbol.parent else ""
        print(
            Style.dim(
                f"     {symbol.kind:9} {symbol.name}{owner} "
                f"(lines {symbol.line_start}-{symbol.line_end}, complexity {symbol.complexity})"
            )
        )

    return language


def report_documentation(documentation) -> None:
    section("5. Generated documentation")

    if documentation.summary:
        print(f"  summary: {documentation.summary}\n")

    for symbol in documentation.symbols:
        print(f"  {Style.bold(symbol.name)}  {Style.dim(symbol.signature[:70])}")
        print(f"    {symbol.summary}")

        if symbol.parameters:
            rendered = ", ".join(f"{p.name}: {p.type or '?'}" for p in symbol.parameters)
            print(Style.dim(f"    parameters: {rendered}"))

        if symbol.raises:
            print(Style.dim(f"    raises: {', '.join(symbol.raises)}"))

        print()


def report_findings(documentation, plan_name: str) -> None:
    if not documentation.findings:
        if plan_name == "free":
            print(Style.dim("\n  (the Free plan produces no findings - try --plan pro)"))
        return

    section("6. Improvement findings")

    for finding in documentation.findings:
        print(f"  [{finding.severity}] {Style.bold(finding.title)}")
        print(f"    {finding.detail}")

        if finding.suggestion:
            print(Style.dim(f"    suggestion: {finding.suggestion}"))

        print()


def report_cost(records: list[CallRecord], elapsed_seconds: float) -> int:
    section("7. Cost and performance")

    total_cost = sum(record.cost_usd for record in records)
    input_tokens = sum(record.input_tokens for record in records)
    output_tokens = sum(record.output_tokens for record in records)
    failures = sum(1 for record in records if not record.succeeded)

    print(f"  calls    : {len(records)}" + (f" ({failures} failed)" if failures else ""))
    print(f"  tokens   : {input_tokens} in, {output_tokens} out")
    print(f"  duration : {elapsed_seconds:.1f}s")
    print(f"  cost     : {Style.bold(f'US$ {total_cost:.6f}')}")

    unverified = {
        record.model
        for record in records
        if (spec := get_model_spec(record.model)) and not spec.verified
    }
    if unverified:
        print(
            Style.warning(
                f"  Warning: unverified pricing for {', '.join(sorted(unverified))}. "
                "Check the provider's official table before billing."
            )
        )

    unknown = {record.model for record in records if get_model_spec(record.model) is None}
    if unknown:
        print(
            Style.warning(
                f"  Warning: model outside the catalog ({', '.join(sorted(unknown))}); "
                "cost counted as zero."
            )
        )

    return failures


def export_result(documentation, export_format: str, output_path: str | None) -> None:
    exporter = ExporterFactory.get(export_format)
    exported = exporter.export(documentation)
    destination = Path(output_path or exported.suggested_filename)
    destination.write_bytes(exported.content)

    section("8. Export")
    print(f"  {Style.success('written')} {destination.resolve()} ({len(exported.content)} bytes)")


async def run(args: argparse.Namespace) -> int:
    settings = load_settings()

    if not report_providers(settings):
        return 1

    call_records: list[CallRecord] = []

    async def record_usage(record: CallRecord) -> None:
        call_records.append(record)
        status = Style.success("ok") if record.succeeded else Style.failure("failed")
        print(
            f"     {record.agent:11} {record.provider}/{record.model:16} "
            f"{record.input_tokens:>6}in {record.output_tokens:>5}out "
            f"{record.latency_ms:>6}ms  {status}"
        )

    router = ProviderRouter.from_settings(settings, usage_sink=record_usage)
    report_routes(router)

    loaded = load_source(args.file)

    if loaded is None:
        return 1

    source, path = loaded

    language = report_parsing(path, source, args.chunk_tokens)

    if language is None:
        return 1

    plan = get_plan(PlanTier(args.plan))

    section(f"4. Pipeline (plan {plan.display_name})")
    print(Style.dim("  real LLM calls start here - this spends money\n"))

    pipeline = DocumentationPipeline(
        router,
        plan,
        PipelineOptions(
            output_language=args.language,
            max_tokens_per_chunk=args.chunk_tokens,
            chunk_concurrency=args.concurrency,
            generate_summary=True,
        ),
    )

    async def report_progress(percent: int, message: str) -> None:
        print(Style.dim(f"  [{percent:>3}%] {message}"))

    started_at = time.perf_counter()

    try:
        result = await pipeline.run(
            path=path,
            source=source,
            language=language,
            progress=report_progress,
        )
    except LegacyDocError as error:
        print(f"\n  {Style.failure('FAILED')}  {error.code}: {error.message}")

        if error.details:
            print(Style.dim(f"  details: {error.details}"))

        await router.aclose()
        return 1
    finally:
        elapsed_seconds = time.perf_counter() - started_at

    await router.aclose()

    report_documentation(result.documentation)
    report_findings(result.documentation, args.plan)

    if result.warnings:
        section("Warnings")
        for warning in result.warnings:
            print(Style.warning(f"  - {warning}"))

    failures = report_cost(call_records, elapsed_seconds)

    if args.format:
        export_result(result.documentation, args.format, args.out)

    return report_verdict(result.documentation, failures)


def report_verdict(documentation, failures: int) -> int:
    print()

    if not documentation.symbols:
        print(Style.failure("VERDICT: no symbols documented. Something is wrong."))
        return 1

    if failures:
        print(Style.warning(f"VERDICT: worked, but {failures} call(s) fell back after failing."))
        return 0

    print(Style.success("VERDICT: pipeline works end to end against the real API."))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m legacydoc_cli.smoke",
        description="Validate the pipeline against a real provider API. Uses no database.",
    )
    parser.add_argument("file", nargs="?", help="File to document (default: built-in sample)")
    parser.add_argument(
        "--plan",
        default="free",
        choices=[str(tier) for tier in PlanTier],
        help="Plan to simulate. 'pro' enables Improver and Verifier.",
    )
    parser.add_argument("--language", default="pt-BR", help="Documentation output language")
    parser.add_argument("--chunk-tokens", type=int, default=6000, help="Budget per chunk")
    parser.add_argument("--concurrency", type=int, default=4, help="Chunks processed in parallel")
    parser.add_argument("--format", choices=["markdown", "pdf", "json"], help="Export the result")
    parser.add_argument("--out", help="Export destination path")

    return parser


def main() -> None:
    args = build_parser().parse_args()

    try:
        exit_code = asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\ninterrupted")
        exit_code = 130

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
