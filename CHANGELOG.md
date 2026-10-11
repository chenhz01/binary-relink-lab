# Changelog

## [0.1.1] - 2026-09-20

### Changed (round-2 iteration after 16-item self-audit)

- **Correctness (+~25% test rigor):** rebuilt ELF fixture builder after header pack/unpack field-count bugs (header was 14 fields, packer passed 20); suite grew 17→21 checks, all PASS. Repro: `python self_test.py`.
- **Correctness:** relocmap now attaches symbol names through the full pipeline in tests (previously fell back to address keys, masking name-matching logic).
- **Safety:** Ethics section expanded with explicit jurisdiction references (EU 2009/24/EC Art. 6) and a "no distribution of derived binaries" clause; fail-loud matching rationale documented in FAQ.

## [0.1.0] - 2026-09-20

### Added

- `abi_lab.py`: stdlib-only ELF64-LE parser (header/sections/dynsym+symtab), exported-ABI surface extraction, `abidiff` compatibility verdict, `relocmap` symbol re-pointing emission (map only, never writes binaries).
- `cli.py`: `elfinfo` / `abidiff` / `relocmap` subcommands.
- `self_test.py`: in-memory synthetic ELF64 fixture builder; functional / error-path / extreme-edge families.
- Ethics & Legal Boundaries section (interoperability research positioning, no-DRM, no-derived-binary distribution); MIT LICENSE (zhengming contributors).
