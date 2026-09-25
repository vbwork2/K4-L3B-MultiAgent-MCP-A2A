from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

from .cases import CaseSet, load_case_set
from .config import Settings
from .contracts import Contracts
from .mcp_gateway import EvidenceGateway, connect_gateway
from .submission import package_submission, validate_artifacts
from .trace import TraceWriter
from .workflow import solve_case


def _root(value: str) -> Path:
    return Path(value).resolve()


async def _show_tools(root: Path, *, details: bool) -> None:
    settings = Settings.load(root)
    contracts = Contracts(root / "contracts" / "schemas")
    async with connect_gateway(settings.mcp_endpoint, settings.team_api_key, contracts) as gateway:
        if details:
            print(json.dumps(await gateway.describe_tools(), ensure_ascii=False, indent=2))
        else:
            for tool in await gateway.list_tools():
                print(tool)


async def _probe_tool(root: Path, case_id: str, tool_name: str, raw_args: list[str]) -> None:
    settings = Settings.load(root)
    contracts = Contracts(root / "contracts" / "schemas")
    arguments: dict[str, str] = {}
    for item in raw_args:
        key, separator, value = item.partition("=")
        if not separator or not key or key == "case_id":
            raise ValueError("each --arg must be KEY=VALUE and cannot override case_id")
        arguments[key] = value
    async with connect_gateway(settings.mcp_endpoint, settings.team_api_key, contracts) as gateway:
        if tool_name not in await gateway.list_tools():
            raise ValueError(f"MCP tool is not available: {tool_name}")
        evidence = await gateway.call(tool_name, case_id=case_id, **arguments)
        print(json.dumps(evidence, ensure_ascii=False, indent=2))


def _retain_trace(trace_path: Path, case_ids: set[str]) -> set[str]:
    if not trace_path.exists():
        return set()
    kept: list[str] = []
    finalized: set[str] = set()
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        case_id = event.get("case_id")
        if case_id in case_ids:
            kept.append(line)
            if event.get("event_type") == "case_finalized":
                finalized.add(case_id)
    trace_path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return finalized


def _run_context_digest(case_set: CaseSet, settings: Settings) -> str:
    payload = {
        "case_set_version": case_set.version,
        "variant_id": case_set.variant_id,
        "cases": case_set.cases,
        "mcp_endpoint": settings.mcp_endpoint,
        "team_api_key": settings.team_api_key,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


async def _run(
    root: Path, *, case_id: str | None = None, resume: bool = False, jobs: int = 4
) -> None:
    if jobs < 1 or jobs > 8:
        raise ValueError("jobs must be between 1 and 8")
    settings = Settings.load(root)
    case_set = load_case_set(root)
    contracts = Contracts(root / "contracts" / "schemas")
    output_root = root / "outputs"
    trace_path = root / "traces" / "trace.jsonl"
    context_path = output_root / ".run-context.sha256"
    output_root.mkdir(parents=True, exist_ok=True)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    if case_id is not None and case_id not in case_set.cases:
        raise ValueError(f"case is outside this case-set: {case_id}")
    selected = (case_id,) if case_id is not None else case_set.case_ids
    context_digest = _run_context_digest(case_set, settings)
    completed: set[str] = set()
    if resume:
        if (
            not context_path.exists()
            or context_path.read_text(encoding="ascii").strip() != context_digest
        ):
            raise ValueError("run context changed; start a fresh run without --resume")
        existing = {path.stem for path in output_root.glob("*.json") if path.is_file()}
        finalized = _retain_trace(trace_path, existing)
        for existing_id in existing & finalized:
            try:
                value = json.loads(
                    (output_root / f"{existing_id}.json").read_text(encoding="utf-8")
                )
                contracts.validate_output(value, f"outputs/{existing_id}.json")
                if value.get("case_id") == existing_id:
                    completed.add(existing_id)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        _retain_trace(trace_path, completed)
    elif case_id is None:
        for stale in output_root.glob("*.json"):
            stale.unlink()
        trace_path.unlink(missing_ok=True)
        context_path.write_text(context_digest + "\n", encoding="ascii")
    else:
        if context_path.exists():
            if context_path.read_text(encoding="ascii").strip() != context_digest:
                raise ValueError("run context changed; start a fresh run without --case-id")
        elif any(output_root.glob("*.json")) or trace_path.exists():
            raise ValueError("existing artifacts have no run context; start a fresh run")
        else:
            context_path.write_text(context_digest + "\n", encoding="ascii")
        (output_root / f"{case_id}.json").unlink(missing_ok=True)
        _retain_trace(trace_path, set(case_set.case_ids) - {case_id})
    remaining = [current_id for current_id in selected if current_id not in completed]
    if not remaining:
        print(f"OK: processed=0, skipped={len(selected)}")
        return
    semaphore = asyncio.Semaphore(jobs)
    trace_lock = asyncio.Lock()

    async def process(current_id: str, gateway: EvidenceGateway) -> tuple[str, str | None]:
        async with semaphore:
            target = output_root / f"{current_id}.json"
            temporary = target.with_suffix(".json.tmp")
            case_trace_path = trace_path.parent / f".{current_id}.trace.tmp"
            case_trace_path.unlink(missing_ok=True)
            case_trace = TraceWriter(case_trace_path, contracts)
            try:
                case_trace.emit(case_id=current_id, event_type="case_received", actor="coordinator")
                output = await solve_case(case_set.cases[current_id], gateway, case_trace)
                contracts.validate_output(output, f"outputs/{current_id}.json")
                if output.get("case_id") != current_id:
                    raise ValueError(f"solver returned a mismatched case_id for {current_id}")
                temporary.write_text(
                    json.dumps(output, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                case_trace.emit(
                    case_id=current_id, event_type="case_finalized", actor="coordinator"
                )
                trace_text = case_trace_path.read_text(encoding="utf-8")
                async with trace_lock:
                    with trace_path.open("a", encoding="utf-8") as handle:
                        handle.write(trace_text)
                    temporary.replace(target)
                print(f"OK: {current_id}", flush=True)
                return current_id, None
            except Exception as exc:
                target.unlink(missing_ok=True)
                temporary.unlink(missing_ok=True)
                print(f"ERROR: {current_id}: {exc}", file=sys.stderr, flush=True)
                return current_id, str(exc)
            finally:
                case_trace_path.unlink(missing_ok=True)

    outcomes: list[tuple[str, str | None]] = []
    for start in range(0, len(remaining), 16):
        batch = remaining[start : start + 16]
        async with connect_gateway(
            settings.mcp_endpoint, settings.team_api_key, contracts
        ) as gateway:
            discovered_tools = await gateway.list_tools()
            if not discovered_tools:
                raise RuntimeError("MCP Gateway returned no tools")
            outcomes.extend(
                await asyncio.gather(*(process(current_id, gateway) for current_id in batch))
            )
    failures = [f"{current_id}: {error}" for current_id, error in outcomes if error]
    if failures:
        raise RuntimeError(f"{len(failures)} case(s) failed; rerun with --resume")
    print(f"OK: processed={len(remaining)}, skipped={len(selected) - len(remaining)}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Day09 L3B student workflow")
    result.add_argument("--root", default=".", help="repository root (default: current directory)")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("validate-inputs", help="validate case-set.json and all 100 inputs")
    mcp_tools = commands.add_parser("mcp-tools", help="authenticate and list discovered MCP tools")
    mcp_tools.add_argument("--details", action="store_true", help="show tool input schemas")
    probe = commands.add_parser("mcp-probe", help="inspect one audited MCP evidence response")
    probe.add_argument("--case-id", required=True)
    probe.add_argument("--tool", required=True)
    probe.add_argument("--arg", action="append", default=[])
    run = commands.add_parser("run", help="run one case or the full case-set")
    run.add_argument("--case-id", help="run one case without removing other outputs")
    run.add_argument("--resume", action="store_true", help="skip valid completed outputs")
    run.add_argument("--jobs", type=int, default=4, help="parallel cases (1 to 8; default: 4)")
    commands.add_parser("validate", help="validate outputs and observable trace")
    package = commands.add_parser("package", help="validate and build the submission ZIP")
    package.add_argument("--output", default="dist/submission.zip")
    return result


def main() -> None:
    args = parser().parse_args()
    root = _root(args.root)
    try:
        if args.command == "validate-inputs":
            case_set = load_case_set(root)
            print(
                f"OK: {case_set.variant_id} / {case_set.version} / {len(case_set.case_ids)} cases"
            )
        elif args.command == "mcp-tools":
            asyncio.run(_show_tools(root, details=args.details))
        elif args.command == "mcp-probe":
            asyncio.run(_probe_tool(root, args.case_id, args.tool, args.arg))
        elif args.command == "run":
            asyncio.run(_run(root, case_id=args.case_id, resume=args.resume, jobs=args.jobs))
        elif args.command == "validate":
            case_set = load_case_set(root)
            contracts = Contracts(root / "contracts" / "schemas")
            _, trace = validate_artifacts(root, case_set, contracts)
            print(f"OK: {len(case_set.case_ids)} outputs / {len(trace)} trace events")
        elif args.command == "package":
            destination = package_submission(root, root / args.output)
            print(f"OK: {destination}")
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
