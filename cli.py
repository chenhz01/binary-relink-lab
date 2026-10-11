#!/usr/bin/env python3
"""binary-relink-lab CLI.

Subcommands:
  elfinfo <file>                 structural summary of an ELF64 file
  abidiff <old> <new>            exported-ABI compatibility diff
  relocmap <old> <new> [--shift N]  emit symbol re-pointing map JSON
"""

import argparse
import json
import sys

import abi_lab


def _parse(path: str, named: bool = False) -> dict:
    try:
        data = abi_lab.load_binary(path)
    except OSError as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        raise SystemExit(2)
    try:
        elf = abi_lab.parse_elf64(data)
    except ValueError as exc:
        print(f"error: {path}: {exc}", file=sys.stderr)
        raise SystemExit(2)
    if named:
        elf = abi_lab.attach_symbol_names(elf, data)
    return elf


def cmd_elfinfo(args) -> int:
    elf = _parse(args.file)
    out = {k: v for k, v in elf.items() if k not in ("symbols", "sections")}
    out["sections"] = len(elf["sections"])
    out["dynamic_symbols"] = len(elf["symbols"].get("dynamic", []))
    print(json.dumps(out, indent=2))
    return 0


def cmd_abidiff(args) -> int:
    old, new = _parse(args.old, named=True), _parse(args.new, named=True)
    print(json.dumps(abi_lab.abidiff(old, new), indent=2))
    return 0


def cmd_relocmap(args) -> int:
    old, new = _parse(args.old, named=True), _parse(args.new, named=True)
    print(json.dumps(abi_lab.relocmap(old, new, args.shift), indent=2))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="abi-lab", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("elfinfo", help="ELF64 structural summary")
    e.add_argument("file")
    e.set_defaults(func=cmd_elfinfo)
    d = sub.add_parser("abidiff", help="exported ABI diff between two ELFs")
    d.add_argument("old")
    d.add_argument("new")
    d.set_defaults(func=cmd_abidiff)
    r = sub.add_parser("relocmap", help="symbol re-pointing map")
    r.add_argument("old")
    r.add_argument("new")
    r.add_argument("--shift", type=int, default=0, help="whole-image base shift delta")
    r.set_defaults(func=cmd_relocmap)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
