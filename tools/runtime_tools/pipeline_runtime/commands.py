"""An allowlisted shell command language. Never evaluate model text in Bash."""
from __future__ import annotations

import argparse
import json
import shlex


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def parse_command(command: str) -> argparse.Namespace:
    if len(command) > 32000 or any(c in command for c in "\n\r\x00"):
        raise ValueError("Expected one bounded bioagent-pipeline command.")
    tokens = shlex.split(command)
    if not tokens or tokens[0] != "bioagent-pipeline":
        raise ValueError("Only bioagent-pipeline commands are supported.")
    parser = Parser(prog="bioagent-pipeline", add_help=False, allow_abbrev=False)
    subs = parser.add_subparsers(dest="operation", required=True, parser_class=Parser)
    for name in ("catalog", "files", "jobs"):
        subs.add_parser(name, add_help=False, allow_abbrev=False)
    example = subs.add_parser("example", add_help=False, allow_abbrev=False)
    example.add_argument("--pipeline", default="example_sequence_qc")
    plan = subs.add_parser("plan", add_help=False, allow_abbrev=False)
    plan.add_argument("--pipeline", required=True)
    plan.add_argument("--input", action="append", default=[])
    plan.add_argument("--param", action="append", default=[])
    plan.add_argument("--cores", type=int, default=1)
    plan.add_argument("--timeout", type=int)
    plan.add_argument("--dry-run", action="store_true")
    run = subs.add_parser("run", add_help=False, allow_abbrev=False)
    run.add_argument("--plan-id", required=True)
    for name in ("status", "wait", "results", "cancel"):
        sub = subs.add_parser(name, add_help=False, allow_abbrev=False)
        sub.add_argument("--job-id", required=True)
        if name == "wait":
            sub.add_argument("--seconds", type=float, default=5)
        if name == "results":
            sub.add_argument("--max-table-rows", type=int, default=10)
    return parser.parse_args(tokens[1:])


def mapping(items: list[str], *, decode: bool = False) -> dict:
    result = {}
    for item in items:
        key, separator, value = item.partition("=")
        if not separator or not key or not value or key in result:
            raise ValueError("Use each input/parameter once as NAME=VALUE.")
        if decode:
            try:
                value = json.loads(value)
            except ValueError:
                pass
        result[key] = value
    return result


def dispatch(root, command: str) -> dict:
    from . import service
    args = parse_command(command)
    if args.operation == "catalog":
        return {"pipelines": service.catalog()}
    if args.operation == "files":
        return {"files": service.files(root)}
    if args.operation == "example":
        return service.stage_example(root, args.pipeline)
    if args.operation == "plan":
        return service.plan(root, args.pipeline, mapping(args.input, decode=True), mapping(args.param, decode=True), args.cores, args.timeout, args.dry_run)
    if args.operation == "run":
        return service.start(root, args.plan_id)
    if args.operation == "jobs":
        return {"jobs": [service.status(root, job["job_id"]) for job in service.JobStore(root).list()]}
    if args.operation == "status":
        return service.status(root, args.job_id)
    if args.operation == "wait":
        return service.wait(root, args.job_id, args.seconds)
    if args.operation == "cancel":
        return service.cancel(root, args.job_id)
    return service.results(root, args.job_id, args.max_table_rows)
