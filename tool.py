#!/usr/bin/env python3
"""Offline, read-only audit. Python 3.12+, standard library only."""
import argparse
import json
import math
import re
import stat
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024
MAX_RECORDS = 50000
MAX_FINDINGS = 100

class InputError(ValueError):
    """A safe, non-payload-bearing input error code."""

class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise InputError("invalid_arguments")

def read_text(path):
    p = Path(path)
    if not stat.S_ISREG(p.stat().st_mode):
        raise InputError("regular_file_required")
    with p.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise InputError("file_size_limit")
    return data.decode("utf-8")

def reject_constant(value):
    raise InputError("non_finite_json_number")

def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError("duplicate_json_member")
        result[key] = value
    return result

def parse_json(text):
    try:
        result = json.loads(text, object_pairs_hook=unique_pairs,
                            parse_float=Decimal, parse_constant=reject_constant)
    except InputError:
        raise
    except (ValueError, RecursionError, InvalidOperation):
        raise InputError("invalid_json") from None
    stack, nodes = [(result, 0)], 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if depth > 128 or nodes > 200000:
            raise InputError("json_structure_limit")
        if isinstance(value, dict):
            stack.extend((v, depth + 1) for v in value.values())
        elif isinstance(value, list):
            stack.extend((v, depth + 1) for v in value)
    return result

class Report:
    def __init__(self, tool):
        self.tool, self.findings, self.count = tool, [], 0
    def add(self, code, **location):
        self.count += 1
        if len(self.findings) < MAX_FINDINGS:
            self.findings.append(dict(code=code, **location))
    def finish(self, **summary):
        return {"tool": self.tool, "status": "fail" if self.count else "pass",
                "summary": dict(summary, finding_count=self.count),
                "findings": self.findings,
                "findings_truncated": self.count > len(self.findings)}

def emit_main(run):
    try:
        result = run()
        code = 1 if result["status"] == "fail" else 0
    except InputError as exc:
        result, code = {"tool": TOOL, "status": "error", "error": str(exc)}, 2
    except (OSError, UnicodeError):
        result, code = {"tool": TOOL, "status": "error", "error": "unreadable_utf8_input"}, 2
    except (ValueError, RecursionError, InvalidOperation):
        result, code = {"tool": TOOL, "status": "error", "error": "invalid_input"}, 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False))
    return code

TOOL = "ini-section-collision-audit"

def audit(text, *, key_case="sensitive", section_case="sensitive"):
    if key_case not in ("sensitive", "fold") or section_case not in ("sensitive", "fold"):
        raise InputError("invalid_case_policy")
    report = Report(TOOL)
    sections, keys, current = {}, {}, None
    records = 0
    lines = text.split("\n")
    # A terminal LF terminates the last physical line; it is not another line.
    # Remove only its synthetic split element, preserving real blank lines.
    if lines[-1] == "":
        lines.pop()
    if len(lines) > MAX_RECORDS:
        raise InputError("line_count_limit")
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if len(raw) > 65536:
            raise InputError("line_size_limit")
        if raw[:1].isspace():
            raise InputError("indented_or_multiline_syntax_unsupported")
        if line.startswith("["):
            if not re.fullmatch(r"\[[^\[\]\r\n]+\]", line):
                raise InputError("malformed_section")
            name = line[1:-1].strip()
            if not name:
                raise InputError("empty_section")
            current = name.casefold() if section_case == "fold" else name
            if current in sections:
                report.add("duplicate_section", line=number, first_line=sections[current])
            else:
                sections[current] = number
                keys[current] = {}
            continue
        if current is None:
            raise InputError("key_outside_section")
        match = re.match(r"([^=:]+)[=:](.*)$", line)
        if not match or not match.group(1).strip():
            raise InputError("malformed_key_value")
        key = match.group(1).strip()
        key = key.casefold() if key_case == "fold" else key
        records += 1
        if key in keys[current]:
            report.add("duplicate_key", line=number, first_line=keys[current][key],
                       section_line=sections[current])
        else:
            keys[current][key] = number
    if not sections:
        raise InputError("section_required")
    return report.finish(sections=len(sections), key_assignments=records,
                         key_case=key_case, section_case=section_case)

def run():
    parser = Parser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("--key-case", choices=("sensitive", "fold"), default="sensitive")
    parser.add_argument("--section-case", choices=("sensitive", "fold"), default="sensitive")
    args = parser.parse_args()
    return audit(read_text(args.input), key_case=args.key_case, section_case=args.section_case)

if __name__ == "__main__":
    sys.exit(emit_main(run))
