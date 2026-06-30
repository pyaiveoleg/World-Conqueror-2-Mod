#!/usr/bin/env python3
"""
build_android_apk.py — one-command, UI-free build of the modded WC2 APK.

Replaces the manual "open it in APK Editor Studio and click Save" step. It:

  1. unpacks the original APK with apktool          (decode)
  2. runs every patch in patches/ in the right order (mod)
  3. repacks with apktool                            (build)
  4. zipaligns + signs (v1+v2+v3)                    (sign)

and leaves you with an installable `wc2_mod_signed.apk`.

WHY A FIXED KEYSTORE MATTERS (this is half of the save fix)
-----------------------------------------------------------
Android keeps an app's data (your WC2 progress lives in the app's internal
dataDir) across updates ONLY when the new APK is signed with the SAME key as
the installed one. Re-sign with a different key and `adb install -r` refuses;
you then have to uninstall, which deletes the save. So this script signs with a
*stable* keystore (default: ./wc2.keystore) that it creates once and reuses for
every later build. Keep that file. Combined with `save_persistence_fix.py`
(which stops the engine wiping the save on a cold start) your progress survives
both reboots and mod updates — as long as you always `adb install -r`.

SIGNERS (best available is used; pick with --signer)
----------------------------------------------------
  * android-sdk   zipalign + apksigner from an Android SDK (ANDROID_HOME /
                  ANDROID_SDK_ROOT / PATH). Full v1+v2+v3. Best option.
  * uber          uber-apk-signer (one self-contained jar, no SDK needed,
                  does align + v1+v2+v3). Download it once from the official
                  releases page (printed below) and drop it at
                  ./tools/uber-apk-signer.jar, or pass --uber PATH.
  * jarsigner     JDK fallback. v1 ONLY — the result will NOT install on
                  Android 11+. Use only for old devices / a quick smoke test.

Examples
--------
  python build_android_apk.py
  python build_android_apk.py --signer android-sdk
  python build_android_apk.py --uber tools/uber-apk-signer.jar
  python build_android_apk.py --apk wc2.apk --out wc2_mod_signed.apk
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APKTOOL = ROOT / "apktool.jar"
PATCHES_DIR = ROOT / "patches"

# Patches applied to the unpacked tree, in order. add_battle goes last because
# it (re)seeds the lib/*.so.orig backups it keys off.
PATCH_ORDER = (
    "infinite_money.py",
    "unlock_all_battles.py",
    "commander_reset.py",
    "add_battle.py",
)

# Stable signing identity. Reused across builds so `adb install -r` keeps saves.
KS_ALIAS = "wc2mod"
KS_PASS = "wc2mod-keystore"
KS_DNAME = "CN=WC2 Mod, OU=modding, O=WC2, L=., ST=., C=US"

# Where to get the self-contained signer (download manually, verify, drop in tools/).
UBER_RELEASES = "https://github.com/patrickfav/uber-apk-signer/releases"


def die(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print("  $ " + " ".join(str(c) for c in cmd))
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def java() -> str:
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        cand = Path(java_home) / "bin" / ("java.exe" if os.name == "nt" else "java")
        if cand.exists():
            return str(cand)
    found = shutil.which("java")
    if not found:
        die("java not found. Install a JDK or set JAVA_HOME.")
    return found


def tool_for(name: str) -> str | None:
    """Find a JDK companion tool (keytool / jarsigner), next to java if needed."""
    found = shutil.which(name)
    if found:
        return found
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        exe = Path(java_home) / "bin" / (f"{name}.exe" if os.name == "nt" else name)
        if exe.exists():
            return str(exe)
    jp = Path(java()).parent / (f"{name}.exe" if os.name == "nt" else name)
    return str(jp) if jp.exists() else None


# --------------------------------------------------------------------------
# build steps
# --------------------------------------------------------------------------

def apktool(args: list[str]) -> None:
    if not APKTOOL.exists():
        die(f"{APKTOOL.name} not found next to this script.")
    run([
        java(), "-jar", "-Xmx1024M", "-Duser.language=en", "-Dfile.encoding=UTF8",
        "-Djdk.util.zip.disableZip64ExtraFieldValidation=true",
        str(APKTOOL), *args,
    ])


def unpack(apk: Path, work: Path) -> None:
    if not apk.exists():
        die(f"input APK not found: {apk}")
    print(f"[1/4] decode {apk.name} -> {work.name}/")
    apktool(["d", "-f", str(apk), "-o", str(work)])


def apply_patches(work: Path) -> None:
    print("[2/4] apply patches")
    staged = work / "patches"
    if staged.exists():
        shutil.rmtree(staged)
    shutil.copytree(PATCHES_DIR, staged)
    for name in PATCH_ORDER:
        script = staged / name
        if not script.exists():
            die(f"missing patch script: patches/{name}")
        print(f"  -- {name}")
        proc = subprocess.run([sys.executable, str(script)], cwd=str(work))
        if proc.returncode != 0:
            die(f"patch {name} failed (exit {proc.returncode}).")
    # Don't ship the .py files inside the APK.
    shutil.rmtree(staged)


def build(work: Path, unsigned: Path) -> None:
    print(f"[3/4] build -> {unsigned.name}")
    unsigned.parent.mkdir(parents=True, exist_ok=True)
    apktool(["b", str(work), "-o", str(unsigned)])


# --------------------------------------------------------------------------
# signing
# --------------------------------------------------------------------------

def ensure_keystore(keystore: Path) -> None:
    if keystore.exists():
        return
    keytool = tool_for("keytool") or die("keytool not found (needed once to create the keystore).")
    print(f"  creating stable keystore {keystore.name} (keep this file!)")
    run([
        keytool, "-genkeypair", "-v",
        "-keystore", str(keystore), "-storepass", KS_PASS, "-keypass", KS_PASS,
        "-alias", KS_ALIAS, "-keyalg", "RSA", "-keysize", "2048",
        "-validity", "10000", "-dname", KS_DNAME,
    ])


def find_sdk_buildtools() -> tuple[str, str] | None:
    roots = [os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT")]
    if os.name == "nt":
        roots.append(str(Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk"))
    else:
        roots.append(str(Path.home() / "Android" / "Sdk"))
    exe = ".exe" if os.name == "nt" else ""
    bat = ".bat" if os.name == "nt" else ""
    for root in filter(None, roots):
        bts = sorted(glob.glob(str(Path(root) / "build-tools" / "*")))
        for bt in reversed(bts):
            za = Path(bt) / f"zipalign{exe}"
            asg = Path(bt) / f"apksigner{bat}"
            if za.exists() and asg.exists():
                return str(za), str(asg)
    # zipalign/apksigner on PATH?
    za = shutil.which("zipalign")
    asg = shutil.which("apksigner")
    if za and asg:
        return za, asg
    return None


def sign_android_sdk(unsigned: Path, out: Path, keystore: Path) -> str:
    tools = find_sdk_buildtools()
    if not tools:
        die("Android SDK build-tools (zipalign+apksigner) not found.")
    zipalign, apksigner = tools
    aligned = unsigned.with_name("aligned.apk")
    run([zipalign, "-f", "-p", "4", str(unsigned), str(aligned)])
    run([
        apksigner, "sign", "--ks", str(keystore),
        "--ks-key-alias", KS_ALIAS, "--ks-pass", f"pass:{KS_PASS}",
        "--key-pass", f"pass:{KS_PASS}", "--out", str(out), str(aligned),
    ])
    aligned.unlink(missing_ok=True)
    return "android-sdk (zipalign + apksigner, v1+v2+v3)"


def uber_jar(explicit: str | None) -> Path | None:
    for cand in filter(None, [explicit, os.environ.get("UBER_APK_SIGNER"),
                              str(ROOT / "tools" / "uber-apk-signer.jar")]):
        if Path(cand).exists():
            return Path(cand)
    return None


def sign_uber(unsigned: Path, out: Path, keystore: Path, jar: Path) -> str:
    run([
        java(), "-jar", str(jar), "--apks", str(unsigned),
        "--ks", str(keystore), "--ksAlias", KS_ALIAS,
        "--ksPass", KS_PASS, "--ksKeyPass", KS_PASS,
        "--allowResign", "--overwrite",
    ])
    # uber overwrites in place (zipaligned + signed); move to the requested name.
    if unsigned.resolve() != out.resolve():
        shutil.move(str(unsigned), str(out))
    return "uber-apk-signer (zipalign + v1+v2+v3)"


def sign_jarsigner(unsigned: Path, out: Path, keystore: Path) -> str:
    js = tool_for("jarsigner") or die("jarsigner not found.")
    shutil.copyfile(unsigned, out)
    run([
        js, "-keystore", str(keystore), "-storepass", KS_PASS, "-keypass", KS_PASS,
        "-sigalg", "SHA256withRSA", "-digestalg", "SHA-256", str(out), KS_ALIAS,
    ])
    print("  !! WARNING: jarsigner produces a v1-only signature. This APK will\n"
          "     NOT install on Android 11+. Use --signer android-sdk, or drop\n"
          "     uber-apk-signer.jar in tools/ for a real v2/v3 signature.")
    return "jarsigner (v1 ONLY — not installable on Android 11+)"


def _uber_hint() -> None:
    print(f"  tip: for a real v2/v3 signature with no Android SDK, download "
          f"uber-apk-signer.jar\n       from {UBER_RELEASES} , put it at "
          f"tools/uber-apk-signer.jar, and re-run.")


def sign(unsigned: Path, out: Path, keystore: Path, choice: str, uber_path: str | None) -> str:
    ensure_keystore(keystore)
    jar = uber_jar(uber_path)

    if choice == "android-sdk":
        return sign_android_sdk(unsigned, out, keystore)
    if choice == "uber":
        if not jar:
            _uber_hint()
            die("uber selected but uber-apk-signer.jar not found (use --uber PATH).")
        return sign_uber(unsigned, out, keystore, jar)
    if choice == "jarsigner":
        return sign_jarsigner(unsigned, out, keystore)

    # auto: best available
    if find_sdk_buildtools():
        return sign_android_sdk(unsigned, out, keystore)
    if jar:
        return sign_uber(unsigned, out, keystore, jar)
    print("  no Android SDK and no uber-apk-signer found; falling back to jarsigner.")
    _uber_hint()
    return sign_jarsigner(unsigned, out, keystore)


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Build + sign the modded WC2 APK (no UI).")
    ap.add_argument("--apk", default="wc2.apk", help="input/original APK (default wc2.apk)")
    ap.add_argument("--out", default="wc2_mod_signed.apk", help="output signed APK")
    ap.add_argument("--work", default="wc2_unpacked", help="apktool work dir")
    ap.add_argument("--keystore", default="wc2.keystore", help="stable signing keystore")
    ap.add_argument("--signer", choices=["auto", "android-sdk", "uber", "jarsigner"],
                    default="auto")
    ap.add_argument("--uber", help="path to uber-apk-signer.jar")
    ap.add_argument("--skip-patches", action="store_true",
                    help="reuse the existing work dir as-is (don't decode/patch)")
    args = ap.parse_args()

    apk = (ROOT / args.apk) if not os.path.isabs(args.apk) else Path(args.apk)
    out = (ROOT / args.out) if not os.path.isabs(args.out) else Path(args.out)
    work = (ROOT / args.work) if not os.path.isabs(args.work) else Path(args.work)
    keystore = (ROOT / args.keystore) if not os.path.isabs(args.keystore) else Path(args.keystore)
    unsigned = ROOT / "build" / "wc2_mod_unsigned.apk"

    if not args.skip_patches:
        unpack(apk, work)
        apply_patches(work)
    elif not work.exists():
        die(f"--skip-patches given but work dir {work} doesn't exist.")

    build(work, unsigned)
    print("[4/4] zipalign + sign")
    scheme = sign(unsigned, out, keystore, args.signer, args.uber)

    digest = hashlib.sha256(out.read_bytes()).hexdigest()[:16]
    print(f"\nOK  {out.name}  ({out.stat().st_size:,} bytes, sha256:{digest})")
    print(f"    signed with: {scheme}")
    print(f"    install:     adb install -r {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
