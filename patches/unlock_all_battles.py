#!/usr/bin/env python3
"""
Open every campaign battle in World Conqueror 2 and remove the
WTO/NATO main-menu gate.

Two binary patches per ABI inside lib/<abi>/libworld-conqueror-2.so:

  1. GUIBattleList::Init — neuter the "this item index >= unlocked
     count → SetEnable(false); locked = 1" branch, so every campaign
     battle (axis / allies / wto / nato) shows up clickable. victory /
     greatvictory thresholds, star counts, and multiplay are untouched.

  2. CMenuState::OnEvent — the WTO/NATO main-menu button checks
     axis_played >= axis_total OR allies_played >= allies_total and
     pops up GUILockedWarning ("After axis or allies campaign…") when
     both checks fail. We force the first conditional branch (axis
     check) to take the "open" path unconditionally, so the warning is
     never constructed. armeabi-v7a in this build has no such gate
     (LockedWarning ctor is never called) — patch skipped there.

Idempotent: re-running on an already-patched library does nothing.
Refuses to write if the byte pattern at any patch site doesn't match.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "lib"


@dataclass(frozen=True)
class Patch:
    abi: str
    offset: int
    original: bytes
    patched: bytes
    note: str


PATCHES: tuple[Patch, ...] = (
    # ---- GUIBattleList::Init — unlock every battle icon ----
    Patch(
        abi="arm64-v8a",
        offset=0xB4E40,
        original=bytes.fromhex("ccfaff54"),  # b.gt 0xb4d98
        patched=bytes.fromhex("d6ffff17"),   # b    0xb4d98
        note="GUIBattleList::Init lock-branch @ b4e40",
    ),
    Patch(
        abi="armeabi-v7a",
        offset=0x740D8,
        original=bytes.fromhex("06db"),  # blt #0x740e8
        patched=bytes.fromhex("06e0"),   # b   #0x740e8
        note="GUIBattleList::Init lock-branch @ 740d8 (Thumb-2)",
    ),
    Patch(
        abi="armeabi",
        offset=0x739DC,
        original=bytes.fromhex("07db"),  # blt #0x739ee
        patched=bytes.fromhex("07e0"),   # b   #0x739ee
        note="GUIBattleList::Init lock-branch @ 739dc (Thumb)",
    ),
    Patch(
        abi="x86",
        offset=0xAFE26,
        original=bytes.fromhex("0f8f2cffffff"),  # jg  0xafd58
        patched=bytes.fromhex("e92dffffff90"),   # jmp 0xafd58 ; nop
        note="GUIBattleList::Init lock-branch @ afe26",
    ),
    Patch(
        abi="x86_64",
        offset=0xBF407,
        original=bytes.fromhex("0f8f4bffffff"),  # jg  0xbf358
        patched=bytes.fromhex("e94cffffff90"),   # jmp 0xbf358 ; nop
        note="GUIBattleList::Init lock-branch @ bf407",
    ),
    # ---- CMenuState::OnEvent — WTO/NATO main-menu gate ----
    Patch(
        abi="arm64-v8a",
        offset=0x833D4,
        original=bytes.fromhex("eaf7ff54"),  # b.ge 0x832d0
        patched=bytes.fromhex("bfffff17"),   # b    0x832d0
        note="CMenuState::OnEvent WTO/NATO gate @ 833d4",
    ),
    Patch(
        abi="armeabi",
        offset=0x58636,
        original=bytes.fromhex("61da"),  # bge #0x586fc
        patched=bytes.fromhex("61e0"),   # b   #0x586fc
        note="CMenuState::OnEvent WTO/NATO gate @ 58636 (Thumb)",
    ),
    Patch(
        abi="x86",
        offset=0x75D9E,
        original=bytes.fromhex("0f8d7cfeffff"),  # jge 0x75c20
        patched=bytes.fromhex("e97dfeffff90"),   # jmp 0x75c20 ; nop
        note="CMenuState::OnEvent WTO/NATO gate @ 75d9e",
    ),
    Patch(
        abi="x86_64",
        offset=0x89C2F,
        original=bytes.fromhex("0f8dcbfeffff"),  # jge 0x89b00
        patched=bytes.fromhex("e9ccfeffff90"),   # jmp 0x89b00 ; nop
        note="CMenuState::OnEvent WTO/NATO gate @ 89c2f",
    ),
    # armeabi-v7a: WTO/NATO gate absent in this build (no LockedWarning ctor
    # call anywhere in .text), so no patch is needed.
)


def apply(p: Patch) -> str:
    so = LIB / p.abi / "libworld-conqueror-2.so"
    backup = so.with_suffix(so.suffix + ".orig")
    if not so.exists():
        return f"[{p.abi}] SKIP — {so} missing"

    data = bytearray(so.read_bytes())
    n = len(p.original)
    here = bytes(data[p.offset:p.offset + n])

    if here == p.patched:
        return f"[{p.abi}] already patched ({p.note})"

    if here != p.original:
        return (
            f"[{p.abi}] REFUSING — bytes at 0x{p.offset:x} are "
            f"{here.hex()} (expected {p.original.hex()}). Library may have been modified."
        )

    if not backup.exists():
        backup.write_bytes(bytes(data))

    data[p.offset:p.offset + n] = p.patched
    so.write_bytes(bytes(data))
    return f"[{p.abi}] patched 0x{p.offset:x}: {p.original.hex()} -> {p.patched.hex()}  ({p.note})"


def main() -> int:
    rc = 0
    for p in PATCHES:
        result = apply(p)
        print(result)
        if "REFUSING" in result:
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
