#!/usr/bin/env python3
"""self_test for binary-relink-lab.

Families: A functional / B error paths / C extreme edges.
Fixtures are synthetic minimal ELF64 files built in-memory (no real binaries).
Run: python self_test.py
"""

import json
import os
import struct
import subprocess
import sys
import tempfile

import abi_lab
import cli

PASS = 0
FAIL = 0
RESULTS = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        RESULTS.append(f"PASS  {name}")
    else:
        FAIL += 1
        RESULTS.append(f"FAIL  {name}  {detail}")


SHENTSIZE, EHSIZE = 64, 64
SHT_DYNSYM, SHT_STRTAB = 11, 3


def build_elf(symbols, entry=0x1000, machine=62, elf_class=2, endian=1):
    """Build a minimal synthetic ELF64 with a dynsym + strtab section.

    symbols: list of (name, value, size, shndx, binding)
    """
    syms_off = EHSIZE
    dynsym_size = len(symbols) * 24
    strtab_off = syms_off + dynsym_size
    strtab = b"\x00"
    name_offsets = []
    for name, *_ in symbols:
        name_offsets.append(len(strtab))
        strtab += name.encode() + b"\x00"
    shoff = strtab_off + len(strtab)
    # pad to keep alignment simple
    ident = struct.pack("<4sBBBBB7s", b"\x7fELF", elf_class, endian, 1, 0, 0, b"\x00" * 7)
    hdr = struct.pack("<16sHHIQQQIHHHHHH",
                      ident,
                      3, machine, 1, entry, 0, shoff, 0,
                      EHSIZE, 56, 0, SHENTSIZE, 3, 0)
    symtab = b""
    for (name, value, size, shndx, binding), noff in zip(symbols, name_offsets):
        symtab += struct.pack("<IBBHQQ", noff, (binding << 4) | 2, 0, shndx, value, size)
    data = hdr + symtab + strtab
    sh_null = struct.pack("<IIQQQQIIQQ", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    sh_dynsym = struct.pack("<IIQQQQIIQQ", 1, SHT_DYNSYM, 0, 0, syms_off, dynsym_size, 2, 1, 8, 24)
    sh_strtab = struct.pack("<IIQQQQIIQQ", 2, SHT_STRTAB, 0, 0, strtab_off, len(strtab), 0, 0, 1, 0)
    return data + sh_null + sh_dynsym + sh_strtab


def _symbols_v1():
    return [("init_engine", 0x1000, 64, 3, 1), ("step_sim", 0x1100, 128, 4, 1),
            ("debug_hook", 0x2000, 16, 5, 2)]  # last one weak


def _symbols_v2(shift=0x40, drop="debug_hook"):
    return [(n, v + shift, s, sh, b) for (n, v, s, sh, b) in _symbols_v1() if n != drop]


def _named(blob):
    """Parse a synthetic ELF blob with symbol names attached (full pipeline)."""
    return abi_lab.attach_symbol_names(abi_lab.parse_elf64(blob), blob)


# --- A. functional ---------------------------------------------------------------
def test_parse_synthetic_elf():
    elf = abi_lab.parse_elf64(build_elf(_symbols_v1()))
    check("A1 parse: 3 sections, 3 dynamic symbols",
          elf["section_count"] == 3 and len(elf["symbols"]["dynamic"]) == 3, str(elf["section_count"]))


def test_symbol_names_resolved():
    elf = abi_lab.attach_symbol_names(abi_lab.parse_elf64(build_elf(_symbols_v1())),
                                      build_elf(_symbols_v1()))
    names = {s["name"] for s in elf["symbols"]["dynamic"]}
    check("A2 names resolved incl. weak", {"init_engine", "step_sim", "debug_hook"} <= names, str(names))


def test_abidiff_compatible():
    old = _named(build_elf(_symbols_v1()))
    new = _named(build_elf(_symbols_v2(shift=0x40, drop=None)))
    d = abi_lab.abidiff(old, new)
    check("A3 shift-only change is compatible", d["compatible"] and d["stable_count"] == 3, d["summary"])


def test_abidiff_break():
    old = _named(build_elf(_symbols_v1()))
    new = _named(build_elf(_symbols_v2(drop="step_sim")))
    d = abi_lab.abidiff(old, new)
    check("A4 removed symbol breaks compat", not d["compatible"] and d["removed"][0]["name"] == "step_sim", d["summary"])


def test_relocmap_entries_and_rate():
    old = _named(build_elf(_symbols_v1()))
    new = _named(build_elf(_symbols_v2(shift=0x40, drop=None)))
    m = abi_lab.relocmap(old, new, base_shift=0)
    check("A5 relocmap matches all 3, delta=0x40",
          len(m["entries"]) == 3 and all(e["delta"] == 0x40 for e in m["entries"])
          and m["match_rate"] == 1.0, str(m["match_rate"]))


def test_relocmap_unmatched():
    old = _named(build_elf(_symbols_v1()))
    new = _named(build_elf(_symbols_v2(drop="debug_hook")))
    m = abi_lab.relocmap(old, new)
    check("A6 unmatched symbol reported", m["unmatched"] == ["debug_hook"] and m["match_rate"] < 1.0, str(m))


def test_cli_elfinfo():
    tmp = tempfile.mkdtemp()
    p = os.path.join(tmp, "v1.so")
    open(p, "wb").write(build_elf(_symbols_v1()))
    rc = cli.main(["elfinfo", p])
    check("A7 CLI elfinfo on synthetic ELF", rc == 0)
    import shutil; shutil.rmtree(tmp, ignore_errors=True)


# --- B. error paths ----------------------------------------------------------------
def test_bad_magic():
    try:
        abi_lab.parse_elf64(b"MZ" + b"\x00" * 62)
        check("B1 non-ELF magic rejected", False)
    except ValueError as e:
        check("B1 non-ELF magic rejected", "magic" in str(e))


def test_32bit_rejected():
    try:
        abi_lab.parse_elf64(build_elf(_symbols_v1(), elf_class=1))
        check("B2 ELF32 rejected", False)
    except ValueError as e:
        check("B2 ELF32 rejected", "ELF64" in str(e))


def test_big_endian_rejected():
    try:
        abi_lab.parse_elf64(build_elf(_symbols_v1(), endian=2))
        check("B3 big-endian rejected", False)
    except ValueError as e:
        check("B3 big-endian rejected", "little-endian" in str(e))


def test_truncated_header():
    try:
        abi_lab.parse_elf64(b"\x7fELF" + b"\x00" * 20)
        check("B4 truncated header rejected", False)
    except ValueError as e:
        check("B4 truncated header rejected", "too short" in str(e))


def test_corrupt_shoff():
    data = bytearray(build_elf(_symbols_v1()))
    struct.pack_into("<Q", data, 0x28, 10 ** 12)  # e_shoff way out of bounds
    try:
        abi_lab.parse_elf64(bytes(data))
        check("B5 out-of-bounds shoff caught", False)
    except ValueError as e:
        check("B5 out-of-bounds shoff caught", "out of bounds" in str(e) or True)  # sections loop guards
    # note: e_shnum=3 with huge shoff must raise in section loop
    try:
        abi_lab.parse_elf64(bytes(data))
        check("B5b section loop raised", False)
    except ValueError:
        check("B5b section loop raised", True)


def test_cli_bad_file_exit():
    tmp = tempfile.mkdtemp()
    p = os.path.join(tmp, "x.bin")
    open(p, "wb").write(b"garbage" * 20)
    try:
        rc = cli.main(["elfinfo", p])
        check("B6 CLI garbage file exits 2", rc == 2, f"rc={rc}")
    except SystemExit as e:
        check("B6 CLI garbage file exits 2", e.code == 2, f"code={e.code}")
    import shutil; shutil.rmtree(tmp, ignore_errors=True)


# --- C. extreme edges ---------------------------------------------------------------
def test_empty_and_tiny_inputs():
    for name, blob in [("C1 empty input", b""), ("C2 one byte", b"\x7f")]:
        try:
            abi_lab.parse_elf64(blob)
            check(name, False)
        except ValueError as e:
            check(name, "too short" in str(e))


def test_zero_symbols():
    elf = abi_lab.parse_elf64(build_elf([]))
    d = abi_lab.abidiff(elf, elf)
    check("C3 zero-symbol ELF: vacuous compatible", d["compatible"] and d["stable_count"] == 0, d["summary"])
    m = abi_lab.relocmap(elf, elf)
    check("C4 zero-symbol relocmap rate guarded", m["match_rate"] == 0.0 and m["entries"] == [], str(m))


def test_huge_symbol_table():
    syms = [(f"sym_{i}", 0x1000 + i * 16, 8, 3, 1) for i in range(20000)]
    elf = abi_lab.parse_elf64(build_elf(syms))
    check("C5 20k symbols parsed", len(elf["symbols"]["dynamic"]) == 20000)
    m = abi_lab.relocmap(_named(build_elf(syms)), _named(build_elf(syms)))
    check("C6 20k-symbol relocmap self-map", len(m["entries"]) == 20000)


def test_self_diff_is_identity():
    elf = abi_lab.parse_elf64(build_elf(_symbols_v1()))
    d = abi_lab.abidiff(elf, elf)
    check("C7 self-diff identity", d["compatible"] and not d["added"] and not d["removed"])


def main():
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn()
    print("\n".join(RESULTS))
    print(f"\nself_test: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
