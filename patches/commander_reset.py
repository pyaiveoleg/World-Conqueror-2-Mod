#!/usr/bin/env python3
"""
World Conqueror 2 — let the player roll back commander progress.

In the "Commander" panel the upgrade arrow on each medal (infantry, air force,
artillery, armour, navy, honour) and on the general's rank disappears once the
medal reaches the maximum tier. With this patch the button stays clickable at
the top tier; tapping it resets that medal / rank back to zero so the player
can start grinding it again.

How it works (per ABI):

  1. `CCommander::IsMaxLevel` → always returns 0 so the rank-upgrade button is
     never hidden, neither from `GUICommander::SetCommanderInfo` (initial draw)
     nor from `GUICommander::OnEvent` (post-upgrade refresh).
  2. `GUICommander::SetCommanderInfo` — the inline `if (warMedalLevel > 2) Hide()`
     branch for the six medals is forced to fall through to the Show + SetNeedMedal
     path, so each medal's arrow stays visible at Gold.
  3. `CCommander::CheckUpgarde` and `CCommander::CheckUpgradeWarMedal` — the
     "at max → return false" early exit is changed to return true, so clicks
     at max no longer no-op.
  4. `CCommander::Upgrade` and `CCommander::UpgradeWarMedal` — when the
     current rank/level is past the cap, the increment is replaced by a reset
     to 0 (via `csinc Wd, wzr, Wd, gt` after `cmp`). Below the cap the
     behaviour is unchanged.

Carrying value (medals owned, lifetime medals) is preserved on reset; only
the consumable rank / war-medal tier is rolled back.

Idempotent: re-running on a patched library is a no-op. Refuses to write if
the bytes at any patch site don't match what we expect.

Currently only arm64-v8a is patched; other ABIs are listed below as TODO.
"""
from __future__ import annotations

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


def _hx(words):
    """Pack a sequence of 32-bit little-endian words into bytes."""
    import struct
    return b"".join(struct.pack("<I", w) for w in words)


# ---------------- arm64-v8a ----------------
#
# All five touch points live in libworld-conqueror-2.so. Offsets are file
# offsets — for this build they equal the in-memory VA, because the .text
# section starts at 0x50890 with no shift.
#
# Symbols (mangled → demangled):
#   CCommander::IsMaxLevel              @ 0x5f818..0x5f828 (4 instrs)
#   CCommander::CheckUpgarde            @ 0x5f78c..0x5f7c8
#   CCommander::Upgrade                 @ 0x5f7c8..0x5f818 (20 instrs)
#   CCommander::CheckUpgradeWarMedal    @ 0x5f88c..0x5f8cc
#   CCommander::UpgradeWarMedal         @ 0x5f8cc..0x5f930 (25 instrs)
#   GUICommander::SetCommanderInfo war-medal hide branch @ 0xa58ac
#
# The two big rewrites (Upgrade / UpgradeWarMedal) reuse the existing stack
# frames and call site offsets; only the body that increments rank/level is
# swapped for a `cmp + csinc Wd, wzr, Wd, gt` pair that returns 0 when above
# the cap and `Wd + 1` otherwise. To make room for those two extra
# instructions, the redundant `uxtb w0, w0` after the CheckUpgrade* call is
# dropped (CheckUpgrade* already returns a clean 0/1 in w0).

ARM64_PATCHES: tuple[Patch, ...] = (
    # 1) IsMaxLevel — `cset w0, gt` → `mov w0, #0`
    Patch(
        abi="arm64-v8a",
        offset=0x5F820,
        original=bytes.fromhex("e0d79f1a"),  # cset w0, gt
        patched=bytes.fromhex("00008052"),   # mov  w0, #0
        note="CCommander::IsMaxLevel always returns 0",
    ),
    # 2) SetCommanderInfo war-medal hide — `b.le 0xa5994` → `b 0xa5994`
    Patch(
        abi="arm64-v8a",
        offset=0xA58AC,
        original=bytes.fromhex("4d070054"),  # b.le 0xa5994
        patched=bytes.fromhex("3a000014"),   # b    0xa5994
        note="GUICommander::SetCommanderInfo war-medal show button at max",
    ),
    # 3) CheckUpgarde — `mov w2, #0` → `mov w2, #1`
    Patch(
        abi="arm64-v8a",
        offset=0x5F790,
        original=bytes.fromhex("02008052"),  # mov w2, #0
        patched=bytes.fromhex("22008052"),   # mov w2, #1
        note="CCommander::CheckUpgarde returns true at max",
    ),
    # 4) CheckUpgradeWarMedal — `mov w3, #0` → `mov w3, #1`
    Patch(
        abi="arm64-v8a",
        offset=0x5F89C,
        original=bytes.fromhex("03008052"),  # mov w3, #0
        patched=bytes.fromhex("23008052"),   # mov w3, #1
        note="CCommander::CheckUpgradeWarMedal returns true at max",
    ),
    # 5) Upgrade — rewrite the post-CheckUpgarde body so that when
    #    rank > 13 the new rank becomes 0 instead of rank + 1.
    Patch(
        abi="arm64-v8a",
        offset=0x5F7DC,
        original=_hx([
            0x53001C00,  # uxtb w0, w0
            0x2A0003F3,  # mov  w19, w0
            0x34000120,  # cbz  w0, 0x5F808
            0xAA1403E0,  # mov  x0, x20
            0x97FFAD11,  # bl   GetUpgradeMedal
            0xB9400A82,  # ldr  w2, [x20, #0x8]
            0xB9400681,  # ldr  w1, [x20, #0x4]
            0x4B000040,  # sub  w0, w2, w0
            0xB9000A80,  # str  w0, [x20, #0x8]
            0x11000421,  # add  w1, w1, #0x1
        ]),
        patched=_hx([
            0x2A0003F3,  # mov  w19, w0                (drops uxtb)
            0x34000140,  # cbz  w0, 0x5F808            (target moves down 1 slot)
            0xAA1403E0,  # mov  x0, x20
            0x97FFAD12,  # bl   GetUpgradeMedal        (offset +1 because of shift)
            0xB9400A82,  # ldr  w2, [x20, #0x8]
            0xB9400681,  # ldr  w1, [x20, #0x4]
            0x4B000040,  # sub  w0, w2, w0
            0xB9000A80,  # str  w0, [x20, #0x8]
            0x7100343F,  # cmp  w1, #0xd               (NEW)
            0x1A81C7E1,  # csinc w1, wzr, w1, gt       (NEW; replaces add w1, w1, #1)
        ]),
        note="CCommander::Upgrade resets rank to 0 when at max",
    ),
    # 6) UpgradeWarMedal — analogous: when medal level > 2 the new level
    #    becomes 0 instead of level + 1.
    Patch(
        abi="arm64-v8a",
        offset=0x5F8E8,
        original=_hx([
            0x53001C00,  # uxtb w0, w0
            0x2A0003F3,  # mov  w19, w0
            0x34000160,  # cbz  w0, 0x5F91C
            0x2A1403E1,  # mov  w1, w20
            0xAA1503E0,  # mov  x0, x21
            0x8B34CAB4,  # add  x20, x21, w20, sxtw #2
            0x97FFC24C,  # bl   GetNeedUpgradeMedal
            0xB9400AA1,  # ldr  w1, [x21, #0x8]
            0x4B000020,  # sub  w0, w1, w0
            0xB9000AA0,  # str  w0, [x21, #0x8]
            0xB9401280,  # ldr  w0, [x20, #0x10]
            0x11000400,  # add  w0, w0, #0x1
        ]),
        patched=_hx([
            0x2A0003F3,  # mov  w19, w0                (drops uxtb)
            0x34000180,  # cbz  w0, 0x5F91C            (target moves down 1 slot)
            0x2A1403E1,  # mov  w1, w20
            0xAA1503E0,  # mov  x0, x21
            0x8B34CAB4,  # add  x20, x21, w20, sxtw #2
            0x97FFC24D,  # bl   GetNeedUpgradeMedal    (offset +1 because of shift)
            0xB9400AA1,  # ldr  w1, [x21, #0x8]
            0x4B000020,  # sub  w0, w1, w0
            0xB9000AA0,  # str  w0, [x21, #0x8]
            0xB9401280,  # ldr  w0, [x20, #0x10]
            0x7100081F,  # cmp  w0, #0x2               (NEW)
            0x1A80C7E0,  # csinc w0, wzr, w0, gt       (NEW; replaces add w0, w0, #1)
        ]),
        note="CCommander::UpgradeWarMedal resets level to 0 when at max",
    ),
)


# ---------------- armeabi-v7a / armeabi / x86 / x86_64 ----------------
#
# Same idea but with a different instruction set per ABI. Not yet ported —
# leave the libraries on these ABIs untouched. arm64-v8a covers the vast
# majority of modern Android devices.
OTHER_ABI_PATCHES: tuple[Patch, ...] = ()


PATCHES = ARM64_PATCHES + OTHER_ABI_PATCHES


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
            f"{here.hex()} (expected {p.original.hex()}). "
            "Library may have been modified."
        )

    if not backup.exists():
        backup.write_bytes(bytes(data))

    data[p.offset:p.offset + n] = p.patched
    so.write_bytes(bytes(data))
    return (
        f"[{p.abi}] patched 0x{p.offset:x} ({len(p.patched)} bytes): "
        f"{p.note}"
    )


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
