#!/usr/bin/env python3
"""
Give the player a huge medal balance and mark all four IAP packs as owned.

This is the script form of the old infinite_money.md instructions. It patches
smali/com/easytech/wc2/Wc2Activity.smali inside an unpacked APK by inserting a
small block at the start of Wc2Activity.MainMenuLoaded().

Idempotent: re-running leaves an already-patched smali file untouched.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SMALI = ROOT / "smali" / "com" / "easytech" / "wc2" / "Wc2Activity.smali"

MARKER = "# infinite_money.py"
SNIPPET = f"""
    {MARKER}
    const v0, 0x3b9aca00

    invoke-static {{v0}}, Lcom/easytech/wc2/Wc2Activity;->AddMedal(I)V

    const/4 v0, 0x0

    invoke-static {{v0}}, Lcom/easytech/wc2/Wc2Activity;->PurchaseSuccess(I)V

    const/4 v0, 0x1

    invoke-static {{v0}}, Lcom/easytech/wc2/Wc2Activity;->PurchaseSuccess(I)V

    const/4 v0, 0x2

    invoke-static {{v0}}, Lcom/easytech/wc2/Wc2Activity;->PurchaseSuccess(I)V

    const/4 v0, 0x3

    invoke-static {{v0}}, Lcom/easytech/wc2/Wc2Activity;->PurchaseSuccess(I)V
"""


def _read_preserving_newlines(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    return raw.decode("utf-8").replace("\r\n", "\n"), newline


def _write_preserving_newlines(path: Path, text: str, newline: str) -> None:
    out = text.replace("\n", newline) if newline != "\n" else text
    path.write_bytes(out.encode("utf-8"))


def _is_already_patched(body: str) -> bool:
    if MARKER in body:
        return True
    required = [
        "const v0, 0x3b9aca00",
        "invoke-static {v0}, Lcom/easytech/wc2/Wc2Activity;->AddMedal(I)V",
        "invoke-static {v0}, Lcom/easytech/wc2/Wc2Activity;->PurchaseSuccess(I)V",
    ]
    return all(item in body for item in required) and body.count("PurchaseSuccess(I)V") >= 4


def patch_main_menu_loaded() -> str:
    if not SMALI.exists():
        return f"[{SMALI}] REFUSING - file missing"

    text, newline = _read_preserving_newlines(SMALI)
    method = re.search(
        r"(?ms)^\.method public static MainMenuLoaded\(\)V\n(?P<body>.*?)^\.end method\n",
        text,
    )
    if method is None:
        return "[Wc2Activity.smali] REFUSING - MainMenuLoaded() not found"

    body = method.group("body")
    if _is_already_patched(body):
        return "[Wc2Activity.smali] already patched (infinite money)"

    locals_match = re.search(r"(?m)^[ \t]*\.locals\s+(\d+)\s*$", body)
    if locals_match is None:
        return "[Wc2Activity.smali] REFUSING - .locals in MainMenuLoaded() not found"

    locals_count = int(locals_match.group(1))
    new_body = body
    if locals_count < 1:
        new_body = (
            body[: locals_match.start(1)]
            + "1"
            + body[locals_match.end(1) :]
        )
        locals_match = re.search(r"(?m)^[ \t]*\.locals\s+\d+\s*$", new_body)
        assert locals_match is not None

    insert_at = locals_match.end()
    new_body = new_body[:insert_at] + SNIPPET + new_body[insert_at:]
    new_text = text[: method.start("body")] + new_body + text[method.end("body") :]
    _write_preserving_newlines(SMALI, new_text, newline)
    return "[Wc2Activity.smali] patched MainMenuLoaded() with infinite money"


def main() -> int:
    result = patch_main_menu_loaded()
    print(result)
    return 1 if "REFUSING" in result else 0


if __name__ == "__main__":
    sys.exit(main())
