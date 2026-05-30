#!/usr/bin/env python3
"""
add_battle.py — add N campaign missions by cloning battle 1 (Blitzkrieg).

==============================================================
   WHAT THIS SCRIPT TOUCHES
==============================================================

A working campaign mission lives in SIX data anchors plus ONE binary
count knob inside libworld-conqueror-2.so. If you tried to add a mission
by hand, you'd have to edit all of them — skip any one and the mission
silently fails (see "failure modes" below).

DATA ANCHORS (created/edited for each new mission K, in each faction F)

  1. assets/battle_F<K>.xml
     country list / area state / dialogue. Internal `areasenable=` is
     rewritten to point at the new .bin. CRLF line endings preserved.

  2. assets/battle_F<K>.bin
     binary area mask. Byte-for-byte copy of battle 1's .bin.

  3. assets/battlelist.xml
     New <battle name="F K" ...> entry inserted right after the highest
     existing entry for that faction. Copied from "F 1" (same map
     coordinates, flags, arrows, victory thresholds, open="1").

  4. assets/stringtable_*.xml   (×12 — 6 languages × phone+iPad)
     `F battle name K`   (button label, per language)
     `F battle intro K`  (mission description, per language)

  5. assets/selbattle_hd.xml
     <Image name="button_F_<KK>.png" .../>  alias pointing at the same
     atlas rectangle as button_F_01.png — so the new button looks
     identical to mission 1's button.

  6. assets/battlename_<lang>_hd.xml   (×6 — one per language)
     <Image name="text_F_<KK>.png" .../>  alias for the per-language
     button label graphic.

BINARY COUNT KNOB

  libworld-conqueror-2.so contains GetNumBattles(faction) which returns
  the per-faction battle count from a hardcoded 5-int table
  {axis=10, allies=10, wto=7, nato=7, multiplay=12}. GUIBattleList::Init
  loops 0..count-1 — so we have to raise the axis slot to 10+N in every
  shipped ABI (arm64-v8a, armeabi-v7a, armeabi, x86, x86_64).

FAILURE MODES (which anchor produces which symptom)

  missing (1)/(2) — crash on tap
  missing (3)     — battle isn't in the lookup, click does nothing
  missing (4)     — button shows the raw key string ("axis battle name 11")
  missing (5)/(6) — invisible button (widget renders nothing)
  binary knob not raised — extra buttons just don't appear

ARM64-V8A QUIRK

  On arm64 the compiler emitted ONE `mov w3, #10` reused by both the
  axis store and the allies store inside GetNumBattles, and there's no
  slack for an instruction insert. So bumping the axis count on arm64
  inevitably bumps the allies count too. This script handles that by
  also cloning allies 1 -> allies N. On the other 4 ABIs the allies
  count slot is patched independently, so the allies clones are just
  unused data there (harmless).

WHAT THIS SCRIPT DOES *NOT* CUSTOMIZE

  All N missions are byte-for-byte clones of battle 1. After running, if
  you want each mission to play differently, you'd need to manually
  edit:

  - battle_F<K>.xml country/area/dialogue
  - battlelist.xml centerx/centery (otherwise all map pins overlap)
  - stringtable entries (otherwise every button reads "Blitzkrieg")
  - atlas aliases (otherwise every button looks identical)

  Real new artwork additionally requires re-baking selbattle_hd.webp /
  battlename_<lang>_hd.png with new regions — out of scope.

  Independent: patches/unlock_all_battles.py neutralises the "must beat
  previous mission first" gate. Run it once if you want all N buttons
  tappable without grinding.

==============================================================
   WORKFLOW
==============================================================

  1. Set MISSIONS_TO_ADD below.
  2. python3 patches/add_battle.py
  3. Repack APK and reinstall.

  Re-running with a different MISSIONS_TO_ADD is safe — data inserts are
  idempotent (skip if already present), and the binary patch is keyed
  off the .so.orig backup so it always patches relative to the pristine
  library.
"""

from __future__ import annotations

import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# =================================================================
#                          CONFIG
# =================================================================

# Number of new clones of battle 1 to create per faction.
# Creates indices 11 .. 10+MISSIONS_TO_ADD.
MISSIONS_TO_ADD = 1

# =================================================================

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
LIB = ROOT / "lib"

# Tunables that almost never change — kept out of the config block so
# the workflow above stays a single dial.
SRC_INDEX = 1
FACTIONS = ("axis", "allies")  # see ARM64-V8A QUIRK in the docstring
ORIGINAL_COUNT = 10  # axis and allies both ship with 10 missions


# -----------------------------------------------------------------
# helpers
# -----------------------------------------------------------------

def _read_preserving_newlines(path: Path) -> tuple[str, str]:
    """Return (text, newline_marker). Text uses '\\n' internally."""
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8").replace("\r\n", "\n")
    return text, newline


def _write_preserving_newlines(path: Path, text: str, newline: str) -> None:
    out = text.replace("\n", newline) if newline != "\n" else text
    path.write_bytes(out.encode("utf-8"))


# -----------------------------------------------------------------
# data anchors (1..6)
# -----------------------------------------------------------------

def patch_battle_xml(faction: str, k: int) -> str:
    """(1) Clone battle_F1.xml -> battle_F<k>.xml, retargeting areasenable=."""
    src = ASSETS / f"battle_{faction}{SRC_INDEX}.xml"
    dst = ASSETS / f"battle_{faction}{k}.xml"
    if dst.exists():
        return f"[battle_{faction}{k}.xml] already exists — skipped"
    if not src.exists():
        return f"[battle_{faction}{k}.xml] REFUSING — source {src.name} missing"

    # battle_*.xml uses CRLF in this build — preserve byte-for-byte.
    data = src.read_bytes()
    needle = f'areasenable="battle_{faction}{SRC_INDEX}.bin"'.encode("utf-8")
    replacement = f'areasenable="battle_{faction}{k}.bin"'.encode("utf-8")
    if needle not in data:
        return f"[battle_{faction}{k}.xml] REFUSING — areasenable anchor not found"
    dst.write_bytes(data.replace(needle, replacement, 1))
    return f"[battle_{faction}{k}.xml] created"


def patch_battle_bin(faction: str, k: int) -> str:
    """(2) Byte-for-byte copy battle_F1.bin -> battle_F<k>.bin."""
    src = ASSETS / f"battle_{faction}{SRC_INDEX}.bin"
    dst = ASSETS / f"battle_{faction}{k}.bin"
    if dst.exists():
        return f"[battle_{faction}{k}.bin] already exists — skipped"
    if not src.exists():
        return f"[battle_{faction}{k}.bin] REFUSING — source {src.name} missing"
    shutil.copyfile(src, dst)
    return f"[battle_{faction}{k}.bin] created"


def patch_battlelist(faction: str, k: int) -> str:
    """(3) Insert <battle name="F k"> into battlelist.xml after the highest
    existing entry for this faction (so consecutive runs build an ordered list)."""
    path = ASSETS / "battlelist.xml"
    text, newline = _read_preserving_newlines(path)

    if re.search(rf'<battle\s+name="{faction} {k}"', text):
        return f"[battlelist.xml] {faction} {k} already present — skipped"

    src_match = re.search(
        rf'(^[ \t]*)<battle\s+name="{faction} {SRC_INDEX}"[\s\S]*?</battle>\s*\n',
        text, re.MULTILINE,
    )
    if not src_match:
        return f"[battlelist.xml] REFUSING — could not locate {faction} {SRC_INDEX} block"

    new_block = src_match.group(0).replace(
        f'name="{faction} {SRC_INDEX}"', f'name="{faction} {k}"', 1
    )

    # Insert after the highest existing entry less than k.
    anchor_match = None
    for i in range(k - 1, 0, -1):
        m = re.search(
            rf'<battle\s+name="{faction} {i}"[\s\S]*?</battle>\s*\n', text
        )
        if m:
            anchor_match = m
            break
    if anchor_match is None:
        return f"[battlelist.xml] REFUSING — no {faction} anchor found"

    insert_at = anchor_match.end()
    new_text = text[:insert_at] + new_block + text[insert_at:]
    _write_preserving_newlines(path, new_text, newline)
    return f"[battlelist.xml] inserted {faction} {k}"


def patch_stringtable(path: Path, faction: str, k: int) -> str:
    """(4) Add `F battle name k` + `F battle intro k` entries cloned from entry 1."""
    text, newline = _read_preserving_newlines(path)
    name_key = f"{faction} battle name {k}"
    intro_key = f"{faction} battle intro {k}"
    src_name_key = f"{faction} battle name {SRC_INDEX}"
    src_intro_key = f"{faction} battle intro {SRC_INDEX}"

    if name_key in text and intro_key in text:
        return f"[{path.name}] {faction} {k} already present — skipped"

    def inject(after_key: str, body: str, source: str) -> str | None:
        pattern = re.compile(
            rf'([ \t]*)<key>{re.escape(after_key)}</key>\s*\n'
            rf'([ \t]*)<string>([\s\S]*?)</string>\s*\n'
        )
        m = pattern.search(source)
        if m is None:
            return None
        indent_key, indent_str, value = m.group(1), m.group(2), m.group(3)
        block = (
            f"{indent_key}<key>{body}</key>\n"
            f"{indent_str}<string>{value}</string>\n"
        )
        return source[: m.end()] + block + source[m.end() :]

    updated = text
    if name_key not in updated:
        nxt = inject(src_name_key, name_key, updated)
        if nxt is None:
            return f"[{path.name}] REFUSING — '{src_name_key}' not found"
        updated = nxt
    if intro_key not in updated:
        nxt = inject(src_intro_key, intro_key, updated)
        if nxt is None:
            return f"[{path.name}] REFUSING — '{src_intro_key}' not found"
        updated = nxt

    if updated == text:
        return f"[{path.name}] no changes for {faction} {k}"
    _write_preserving_newlines(path, updated, newline)
    return f"[{path.name}] added {faction} {k}"


def patch_atlas(path: Path, sprite_prefix: str, faction: str, k: int) -> str:
    """(5)/(6) Alias `<prefix>_F_<KK>.png` -> same atlas rect as `<prefix>_F_01.png`.

    Format string in the lib is `%02d` (min 2 digits), so for k in 1..99 we
    write 2-digit names; for k >= 100 the field naturally widens to 3 digits.
    """
    text, newline = _read_preserving_newlines(path)

    pad = max(2, len(str(k)))
    new_name = f"{sprite_prefix}_{faction}_{k:0{pad}d}.png"
    if f'name="{new_name}"' in text:
        return f"[{path.name}] {new_name} already aliased — skipped"

    src_name = f"{sprite_prefix}_{faction}_{SRC_INDEX:02d}.png"
    pattern = re.compile(
        rf'([ \t]*)<Image\s+name="{re.escape(src_name)}"([^/]*)/>\s*\n'
    )
    m = pattern.search(text)
    if m is None:
        return f"[{path.name}] REFUSING — anchor {src_name} not found"

    indent, attrs = m.group(1), m.group(2)
    alias_line = f'{indent}<Image name="{new_name}"{attrs}/>\n'
    new_text = text[: m.end()] + alias_line + text[m.end() :]
    _write_preserving_newlines(path, new_text, newline)
    return f"[{path.name}] aliased {new_name}"


# -----------------------------------------------------------------
# binary count knob (GetNumBattles)
# -----------------------------------------------------------------

def _encode_movz_w3(n: int) -> bytes:
    """Encode `MOVZ w3, #n` as 4 LE bytes. Single-instruction up to 0xFFFF."""
    if not 0 <= n <= 0xFFFF:
        raise ValueError(f"count {n} doesn't fit in a single MOVZ (max 65535)")
    return (0x52800003 | (n << 5)).to_bytes(4, "little")


def _encode_byte(n: int) -> bytes:
    if not 0 <= n <= 0xFF:
        raise ValueError(f"count {n} doesn't fit in 1 byte (arm32 rodata, max 255)")
    return bytes([n])


def _encode_imm32(n: int) -> bytes:
    if not 0 <= n < (1 << 32):
        raise ValueError(f"count {n} doesn't fit in 4 bytes")
    return n.to_bytes(4, "little")


@dataclass(frozen=True)
class BinPatch:
    abi: str
    offset: int
    original: bytes
    encode: Callable[[int], bytes]
    note: str

    @property
    def size(self) -> int:
        return len(self.original)


BIN_PATCHES: tuple[BinPatch, ...] = (
    BinPatch(
        abi="arm64-v8a",
        offset=0x63340,
        original=bytes.fromhex("43018052"),  # MOVZ w3, #10
        encode=_encode_movz_w3,
        note="MOVZ w3, #N (shared register also bumps allies)",
    ),
    BinPatch(
        abi="armeabi-v7a",
        offset=0x109774,
        original=b"\x0a",
        encode=_encode_byte,
        note="rodata axis slot",
    ),
    BinPatch(
        abi="armeabi",
        offset=0x10511C,
        original=b"\x0a",
        encode=_encode_byte,
        note="rodata axis slot",
    ),
    BinPatch(
        abi="x86",
        offset=0x4EF43,
        original=b"\x0a\x00\x00\x00",
        encode=_encode_imm32,
        note="movl imm32 axis slot",
    ),
    BinPatch(
        abi="x86_64",
        offset=0x66839,
        original=b"\x0a\x00\x00\x00",
        encode=_encode_imm32,
        note="movl imm32 axis slot",
    ),
)


def apply_binary(p: BinPatch, target_count: int) -> str:
    """Patch GetNumBattles axis slot to target_count. Idempotent + reconfigurable:
    .orig backup is the source of truth for pristine bytes, so MISSIONS_TO_ADD
    can be changed and re-run without manual cleanup."""
    so = LIB / p.abi / "libworld-conqueror-2.so"
    backup = so.with_suffix(so.suffix + ".orig")
    if not so.exists():
        return f"[{p.abi}] SKIP — {so} missing"

    current = so.read_bytes()
    if not backup.exists():
        # First run — assume current is pristine and seed the backup.
        backup.write_bytes(current)
    pristine = backup.read_bytes()

    here_pristine = pristine[p.offset : p.offset + p.size]
    if here_pristine != p.original:
        return (
            f"[{p.abi}] REFUSING — .orig bytes at 0x{p.offset:x} are "
            f"{here_pristine.hex()}, expected {p.original.hex()}. "
            f"Delete {backup.name} if the .so was previously modified."
        )

    target_bytes = p.encode(target_count)
    here_now = current[p.offset : p.offset + p.size]
    if here_now == target_bytes:
        return f"[{p.abi}] already at count {target_count} — skipped"

    data = bytearray(current)
    data[p.offset : p.offset + p.size] = target_bytes
    so.write_bytes(bytes(data))
    return (
        f"[{p.abi}] 0x{p.offset:x}: {here_now.hex()} -> {target_bytes.hex()}  "
        f"(count = {target_count}; {p.note})"
    )


# -----------------------------------------------------------------
# main
# -----------------------------------------------------------------

def main() -> int:
    if MISSIONS_TO_ADD < 0:
        print(f"MISSIONS_TO_ADD must be >= 0, got {MISSIONS_TO_ADD}")
        return 1

    new_indices = list(range(ORIGINAL_COUNT + 1, ORIGINAL_COUNT + 1 + MISSIONS_TO_ADD))
    target_count = ORIGINAL_COUNT + MISSIONS_TO_ADD
    selbattle = ASSETS / "selbattle_hd.xml"
    battlename_atlases = sorted(ASSETS.glob("battlename_*_hd.xml"))
    stringtables = sorted(ASSETS.glob("stringtable_*.xml"))

    span = f"{new_indices[0]}..{new_indices[-1]}" if new_indices else "(none)"
    print(
        f"# adding {len(new_indices)} clone(s) [{span}] for {FACTIONS}; "
        f"target count = {target_count}\n"
    )

    rc = 0
    def log(line: str) -> None:
        nonlocal rc
        print(line)
        if "REFUSING" in line:
            rc = 1

    print("== DATA ==")
    for faction in FACTIONS:
        for k in new_indices:
            log(patch_battle_xml(faction, k))
            log(patch_battle_bin(faction, k))
            log(patch_battlelist(faction, k))
            log(patch_atlas(selbattle, "button", faction, k))
            for atlas in battlename_atlases:
                log(patch_atlas(atlas, "text", faction, k))
            for stringtable in stringtables:
                log(patch_stringtable(stringtable, faction, k))

    print("\n== BINARY ==")
    for p in BIN_PATCHES:
        try:
            log(apply_binary(p, target_count))
        except ValueError as e:
            log(f"[{p.abi}] REFUSING — {e}")

    return rc


if __name__ == "__main__":
    sys.exit(main())
