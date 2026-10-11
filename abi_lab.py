"""binary-relink-lab: generic ELF64 ABI tooling for relink-based interoperability research.

Implements the *relink, don't emulate* idea as reusable primitives on plain
ELF64 binaries you legitimately own:
  - elfinfo:  parse ELF64 headers, sections, dynamic symbols (stdlib only)
  - abidiff:  diff exported symbol sets between two ELF64 files
  - relocmap: emit a symbol-mapping JSON (old -> new address) that a relinker
              could consume to re-point references after a memory-layout change.

Scope & legality: this is format-level interoperability research. It handles
no proprietary game content, no DRM, no decryption. See README "Ethics &
Legal Boundaries".
"""

from __future__ import annotations

import json
import struct

ELF_MAGIC = b"\x7fELF"
ELFCLASS64 = 2
SHT_DYNSYM = 11
SHT_SYMTAB = 2
STB_GLOBAL, STB_WEAK = 1, 2
SHN_UNDEF = 0


def parse_elf64(data: bytes) -> dict:
    """Parse a 64-bit little-endian ELF into a structural summary.

    Raises ValueError on anything that is not an ELF64 LE binary.
    """
    if len(data) < 64:
        raise ValueError(f"too short for ELF header: {len(data)} bytes")
    if data[:4] != ELF_MAGIC:
        raise ValueError("not an ELF file (bad magic)")
    ei_class, ei_data = data[4], data[5]
    if ei_class != ELFCLASS64:
        raise ValueError(f"only ELF64 supported, got class={ei_class}")
    if ei_data != 1:
        raise ValueError("only little-endian supported")

    (e_ident, e_type, e_machine, _version, e_entry, e_phoff, e_shoff, _flags,
     _ehsize, _phentsize, e_phnum, shentsize, e_shnum, e_shstrndx) = struct.unpack_from("<16sHHIQQQIHHHHHH", data, 0)

    sections = []
    symtabs = {}
    for i in range(e_shnum):
        off = e_shoff + i * shentsize
        if off + shentsize > len(data):
            raise ValueError(f"section header {i} out of bounds")
        (sh_name, sh_type, _flags, _addr, sh_offset, sh_size,
         _link, _info, _align, sh_entsize) = struct.unpack_from("<IIQQQQIIQQ", data, off)
        sections.append({"index": i, "type": sh_type, "offset": sh_offset,
                         "size": sh_size, "entsize": sh_entsize})
        if sh_type in (SHT_DYNSYM, SHT_SYMTAB) and sh_entsize:
            syms = _parse_symbols(data, sh_offset, sh_size, sh_entsize)
            kind = "dynamic" if sh_type == SHT_DYNSYM else "static"
            symtabs.setdefault(kind, []).extend(syms)

    return {
        "type": e_type, "machine": e_machine, "entry": e_entry,
        "phnum": e_phnum, "section_count": e_shnum,
        "sections": sections,
        "symbols": symtabs,
    }


def _parse_symbols(data: bytes, offset: int, size: int, entsize: int) -> list:
    """Parse an ELF64 symbol table (24-byte entries)."""
    symbols = []
    count = size // entsize
    for i in range(count):
        off = offset + i * entsize
        if off + 24 > len(data):
            break
        st_name, st_info, _other, st_shndx, st_value, st_size = struct.unpack_from("<IBBHQQ", data, off)
        binding = st_info >> 4
        if st_shndx == SHN_UNDEF or binding not in (STB_GLOBAL, STB_WEAK):
            continue  # exported/defined ABI surface only
        symbols.append({"name_offset": st_name, "shndx": st_shndx,
                        "value": st_value, "size": st_size, "binding": binding})
    return symbols


def attach_symbol_names(elf: dict, data: bytes) -> dict:
    """Resolve symbol names via the linked string tables (best effort)."""
    # find .strtab / .dynstr-ish sections: we re-scan for SHT_STRTAB (type 3)
    strtabs = [s for s in elf["sections"] if s["type"] == 3]
    def read_cstr(buf: bytes, pos: int) -> str:
        end = buf.find(b"\x00", pos)
        if end == -1:
            end = len(buf)
        return buf[pos:end].decode("utf-8", "replace")
    for kind, tables in elf["symbols"].items():
        strtab_data = b""
        if strtabs:
            s = strtabs[-1]
            strtab_data = data[s["offset"]:s["offset"] + s["size"]]
        for sym in tables:
            sym["name"] = read_cstr(strtab_data, sym["name_offset"]) if sym["name_offset"] < len(strtab_data) else ""
    return elf


def exported_api(elf: dict, kind: str = "dynamic") -> set:
    """The exported ABI surface: set of (name, size) tuples."""
    out = set()
    for sym in elf["symbols"].get(kind, []):
        out.add((sym.get("name", f"@{sym['value']:#x}"), sym["size"]))
    return out


def abidiff(old: dict, new: dict) -> dict:
    """Diff two parsed ELF ABI surfaces."""
    old_api, new_api = exported_api(old), exported_api(new)
    removed = sorted(old_api - new_api)
    added = sorted(new_api - old_api)
    common = old_api & new_api
    return {
        "removed": [{"name": n, "size": s} for n, s in removed],
        "added": [{"name": n, "size": s} for n, s in added],
        "stable_count": len(common),
        "compatible": len(removed) == 0,
        "summary": (f"{len(removed)} removed, {len(added)} added, "
                    f"{len(common)} stable; compatibility={'yes' if not removed else 'NO'}"),
    }


def relocmap(old: dict, new: dict, base_shift: int = 0) -> dict:
    """Build a symbol re-pointing map old_address -> new_address.

    Symbols are matched by name (fallback: ordinal index within stable pairs).
    base_shift models a whole-image relocation delta.
    """
    old_by_name = {s.get("name", f"@{s['value']:#x}"): s for s in old["symbols"].get("dynamic", [])}
    new_by_name = {s.get("name", f"@{s['value']:#x}"): s for s in new["symbols"].get("dynamic", [])}
    entries, unmatched = [], []
    for name, osym in old_by_name.items():
        nsym = new_by_name.get(name)
        if nsym is None:
            unmatched.append(name)
            continue
        entries.append({"symbol": name,
                        "old": osym["value"], "new": nsym["value"],
                        "delta": nsym["value"] - osym["value"] + base_shift})
    return {"entries": entries, "unmatched": sorted(unmatched),
            "match_rate": round(len(entries) / max(1, len(old_by_name)), 3)}


def load_binary(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()
