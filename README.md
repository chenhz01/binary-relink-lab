# binary-relink-lab

Generic, format-level ELF64 ABI tooling implementing the *relink, don't emulate* idea: parse exported symbol surfaces, diff them across binary versions, and emit symbol re-pointing maps a relinker could consume — no emulation overhead, no proprietary content. If you port software across ABI/memory-layout changes and want the static-analysis half as a reusable library, start here.

**Confidence: High (80%)** that symbol-level abidiff + relocmap covers the first decision layer of any relink project; the execution layer (actually rewriting relocations) is out of scope.

## Problem

Emulation is the default answer to "run this binary elsewhere," but it burns 3-10x runtime overhead for a problem that is often static: references just need re-pointing.

- **Why novel:** relink-based ports convert a compatibility problem into a static transformation — zero emulation cost at runtime. The published proofs of this route focus on one target; the *generalizable* primitives (ABI surface diff, relocation mapping) have not been extracted as reusable tools.
- **Overlooked angle:** ABI relinking generalizes far beyond its famous use case: reviving old software whose source is lost, porting firmware images across SoC revisions, forensics on relocated binaries — anywhere two ABI layouts need a symbol-level bridge.

## How it works

Three primitives on ELF64 little-endian binaries you legitimately possess (`abi_lab.py`, pure stdlib):

| Primitive | Input | Output |
|---|---|---|
| `parse_elf64` | binary blob | header/section/symbol structure (ELF64 headers unpacked with `struct`) |
| `abidiff` | two parsed ELFs | removed/added/stable exported symbols + compatibility verdict |
| `relocmap` | two parsed ELFs + base shift | `{symbol, old, new, delta}` JSON + match rate + unmatched list |

Names are resolved through string tables; undefined and local symbols are excluded so the "ABI surface" is exactly what external callers can depend on.

## Quickstart (~3 min)

```bash
# 1. Run the self-test — fixtures are synthetic ELFs built in-memory (~3 s)
python self_test.py

# 2. Inspect any ELF64 you own (~1 s)
python cli.py elfinfo /path/to/your_elf64_binary

# 3. Diff two builds of your own project (~2 s)
python cli.py abidiff build_v1/app.so build_v2/app.so
python cli.py relocmap build_v1/app.so build_v2/app.so --shift 0x40 > reloc.json
```

Step 1 requires nothing but Python 3.10+; steps 2-3 need an ELF64 file you have the right to analyze.

## Why not X

| Alternative | Why not |
|---|---|
| Full emulation (qemu/interpreters) | Correct for foreign ISAs, but 3-10x overhead and no static artifact; when only layout shifted, relinking wins decisively |
| objdump/readelf + shell scripts | Read-only inspection; no machine-readable abidiff verdict, no relocmap emission, awkward to integrate into CI |
| libabigail / ABI compliance checker | Excellent C/C++ ABI tooling, but source-oriented (needs debug info/DWARF) and heavyweight; this lab works on naked stripped binaries, stdlib-only |
| Recompiling from scratch | Requires source and toolchain; relinking is precisely for when you don't have them |

## Minimal Fallback (PLAN B)

No Python? The logic is documented struct: header layout `<16sHHIQQQIHHHHHH>`, symbol entry `<IBBHQQ>`, and the decision rule "removed symbol = incompatible; matched symbol gets re-pointed by delta". You can implement the same three primitives in any language in an afternoon — the README is the spec.

## Design Trade-offs

Priority: **format correctness > legality discipline > portability > feature breadth.** Name-based symbol matching (not fuzzy heuristics) because a wrong re-point is worse than an honest unmatched list; fail-closed parsing (anything non-ELF64-LE raises); relocation *emission only* — the lab never writes binaries, keeping the blast radius of bugs at zero.

## Ethics & Legal Boundaries

- **Interoperability research only.** This repository provides generic ABI analysis primitives. It contains, links, or targets **no game executables, no proprietary firmware, no DRM-protected content** — all fixtures are synthetic ELFs generated in-memory by the test suite.
- **You analyze only what you have the right to analyze.** Reverse engineering and relinking are lawful in many jurisdictions for interoperability purposes (e.g., EU Software Directive 2009/24/EC Art. 6, US copyright office exemptions) but restricted in others and under many EULAs. Jurisdiction and contract check are *your* responsibility; this tool does not and cannot decide for you.
- **No circumvention.** The lab does not decrypt, unpack, or defeat technical protection measures. If a binary requires breaking a protection to analyze, this lab is out of scope, full stop.
- **No distribution of derived binaries.** Relinked outputs typically derive from copyrighted works; redistribution is a separate legal act this repo deliberately does not facilitate.
- Contact: hcac4735@agent.qq.com

## Limits & Second-order Effects

- **Limits:** ELF64 little-endian only; name-based matching misses same-content-different-name symbols; no relocation-type awareness (entries are address deltas, not typed relocations); static symbol tables other than dynsym/symtab are ignored.
- **Second-order effects:** relink tooling lowers the cost of keeping abandoned software alive — culturally good, but it also lowers the cost of maintaining unauthorized forks of abandonware whose rights holders still exist. Wide adoption may push vendors toward harder anti-relink protections, an arms race this project does not intend to accelerate (hence no writing capability).

## FAQ

**Q: Can this port [famous game console title] to PC?**
Out of scope by design. The lab ships generic primitives and synthetic fixtures; applying them to any specific commercial binary is your legal decision, made elsewhere.

**Q: Why name-based matching instead of smarter matching?**
A wrong re-point silently corrupts a running program; an unmatched symbol fails loudly. Fail-loud beats fail-weird. [High confidence]

**Q: When you should NOT use this tool**
- The target binary is packed, encrypted, or DRM-wrapped — nothing here applies.
- You need runtime behavior guarantees — abidiff is a static first filter, not a proof of behavioral equivalence.
- Your two binaries differ by more than layout (different compilers + inlining + renamed internals) — the match rate will be too low to be useful; source-level porting wins.

**Q: Why no binary-writing step?**
Deliberate trade-off: emitting patched binaries is where legal risk concentrates. This lab stops at the map; executors stay yours.

## Core Assumptions

1. Exported dynamic-symbol surface (defined, global/weak) is a meaningful approximation of "ABI" for compatibility triage.
2. Symbol-level address deltas are the dominant relocation work in layout-shift relink scenarios.
3. Users can legitimately possess the binaries they analyze; the tool's job is format analysis, not rights verification.
4. ELF64 LE remains the dominant target format for interoperability research through at least the near term (as of 2026-09-20).

*All fixtures synthetic; no third-party binaries analyzed in this repo. Contact: hcac4735@agent.qq.com*
