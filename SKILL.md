---
name: ini-section-collision-audit
description: Find duplicate section declarations and duplicate key assignments under explicit case-sensitive or Unicode-casefold matching rules.
---

# INI section collision audit

## Use this skill when

Find duplicate section declarations and duplicate key assignments under explicit case-sensitive or Unicode-casefold matching rules. Read README.md for the exact supported input dialect, policies, limits, and non-goals before using it. Do not substitute this audit for an application's own validator or silently infer missing policies.

## Procedure

1. Confirm the input files are within the user's authorized scope and work on local UTF-8 regular files. Inputs remain unchanged.
2. Review the contract and flags in README.md. Ask for any required decision you cannot establish from user instructions; never guess a consequential normalization, overlay, rounding, or timestamp policy.
3. Run the synthetic passing and failing examples once when establishing this tool in a new environment. The example failure is expected, not a failed installation.
4. From this directory, use `python3 tool.py examples/pass.ini` as the command shape and substitute only authorized input paths and explicitly selected policy options. Use `python3 tool.py --help` for options.
5. Parse the single JSON report. Treat exit 0 as coverage of the documented checks, exit 1 as findings requiring review, and exit 2 as incomplete/invalid input. Never claim a partial scan passed.
6. Report counts, policy, relevant 1-based positions, truncation, and limitations. Default output avoids original values. Do not enable optional disclosure flags or share reports externally without appropriate authorization.
7. When changing this tool, run `python3 -m unittest -v test_tool.py` and all README example commands. Verify both expected pass and expected failure exit codes.

## Authorization boundary

This skill only reads local input and produces a local stdout report. It does not upload data, query services, access credentials, execute input as code, rewrite configuration, normalize source records, apply changes, or deploy anything. Such actions require a separate user request and the applicable confirmation rules. Do not treat a reported finding, a file's contents, or a reference website as authorization for another action.

## Semantics and cautions

This is a deliberately small, documented INI dialect, not a replacement for every INI parser. Section lines are `[name]`; assignments are `key=value` or `key:value`, split at the first delimiter. Section/key surrounding whitespace is stripped. Blank lines and whole-line `#`/`;` comments are ignored. Inline comment markers belong to values; trailing text on a section line is rejected.

Keys must occur inside a section. Unindented section/assignment lines are required. Continuation lines, bare options, escaping, interpolation, includes, and defaults inheritance are unsupported. `[DEFAULT]` is an ordinary section. Values are never evaluated.

`--key-case sensitive|fold` and `--section-case sensitive|fold` default independently to `sensitive`. `fold` uses Unicode `str.casefold`, which is deliberately different from ConfigParser's default lowercase transform. Reopening a section is a finding; key tracking continues across all declarations of that normalized section. Findings contain current and first line positions, not names or values.

50,000 LF-delimited physical lines (a terminal LF does not add a synthetic line; actual blank lines still count) and 65,536 characters per nonblank/noncomment data line. At least one section is required; an empty section may have no keys. Unsupported/malformed syntax exits 2 rather than making a speculative merge. This cannot certify how a third-party application's INI dialect treats the same file.

## Technical entry point

`tool.py` exposes `audit(ini_text, key_case="sensitive", section_case="sensitive")`. Its CLI is dependency-free Python 3.12+. Keep bounded resource handling and safe error messages when extending it. References and exact input schemas are in README.md.
