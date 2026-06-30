# World-Conqueror-2-Mod

My custom World Conqueror 2 mods (package `com.easytech.wc2`, game version
1.3.14). Every change is a small, idempotent Python patch under `patches/`, and
`build_android_apk.py` turns the stock APK into an installable modded one with a
single command — no clicking around in a UI.

## What the mod does

| Feature | Script | ABIs |
|---|---|---|
| Infinite money + all 4 IAP packs owned | `patches/infinite_money.py` | all (smali) |
| All campaign battles unlocked incl. NATO/WTO, no locked visuals | `patches/unlock_all_battles.py` | all |
| Roll back Commander rank & medals (to raise difficulty) | `patches/commander_reset.py` | arm64-v8a only |
| Add your own campaign missions | `patches/add_battle.py` | all |

`wc2.apk` is the unmodified original (stored via Git LFS). `wc2_mod_latest.apk`
is a published build.

> **Heads up:** to publish a new build, run `build_android_apk.py` and copy the
> resulting `wc2_mod_signed.apk` over `wc2_mod_latest.apk`.

## Saves (and the 1.3.14 vs 1.3.20 investigation)

Saves live in the app's internal `dataDir` (`game6.sav`, `conquest6.sav`,
`commander.sav`, `AutoSave`) — internal storage, which survives reboots.

**What's reproducible — rely on this.** The 1.3.14-based mod keeps progress
across a reboot, every time. Verified on-device: snapshot the saves →
`adb reboot` → relaunch → byte-compare. Campaign saves come back **identical**
(only `commander.sav` changes, by 6 bytes — a "last played" timestamp). Make
progress → reboot → it's still there.

**It's the install environment, not the game's code.** On the same phone
(Android 13, OnePlus CPH2493, same official EasyTech signature `f2c90fa9`), the
Play-Store **v1.3.20** resets progress on reboot while **v1.3.14** keeps it.
That looked like a version regression — but a deep binary comparison (capstone +
pyelftools) shows the two versions share the **same save/load logic**:

- arm64 `.text` of `libworld-conqueror-2.so` — **functionally identical**
  (relocation-aware instruction diff: **0** structural changes; the raw byte
  diffs are only address-shift noise from ~4 KB of appended data).
- assets — **byte-identical**; Java save path + `onCreate` order — identical;
  neither version has Play Games cloud saves; targetSdk 33 → 35 is moot on an
  Android-13 device (target-gated behavior needs the *device* at that level).

So the 1.3.20 reset isn't the game's own save code. The difference that remains
is the **install environment**: 1.3.20 came from the Play Store as a
split-bundle (`extractNativeLibs=false`) install, while 1.3.14 was a sideloaded
standalone APK. A code patch can't change that — the fix is simply to stay on
1.3.14 (which the mod does).

**Practical guidance**
- Keep the mod on **1.3.14**; it reliably keeps saves.
- The other, well-understood way to lose everything is a **data wipe from
  re-signing with a different key**: Android then refuses `adb install -r`, you
  uninstall, and `/data/data/com.easytech.wc2` (all saves) goes with it. So
  always build with the **same** keystore (`build_android_apk.py` creates
  `wc2.keystore` once and reuses it — keep that file) and install with
  **`adb install -r`**, never uninstall.

> An earlier attempt to "fix" saves *inside* the APK (rebinding the save path
> early in `onCreate`) was a misdiagnosis — it crashed on launch and was
> removed. On 1.3.14 there is no in-game save bug to patch.

## Build it (the easy way)

```sh
python build_android_apk.py
```

That unpacks `wc2.apk`, applies every patch in `patches/`, repacks, zipaligns and
signs (v1+v2+v3), and writes `wc2_mod_signed.apk`. Then:

```sh
adb install -r wc2_mod_signed.apk
```

### Prerequisites

- **Java (JDK)** — provides `keytool`/`jarsigner` and runs apktool.
- **`apktool.jar`** in the repo root. It is *not* committed (15 MB); grab it
  from <https://apktool.org/> or copy the one bundled with APK Editor Studio.
- **A signer that produces v2/v3 signatures** (required to install on Android
  11+). `build_android_apk.py` picks the best available, in order:
  1. **Android SDK** `zipalign` + `apksigner` (found via `ANDROID_HOME` /
     `ANDROID_SDK_ROOT` / `PATH`). Best option.
  2. **uber-apk-signer** — one self-contained jar, no SDK needed. Download it
     from <https://github.com/patrickfav/uber-apk-signer/releases>, verify it,
     and drop it at `tools/uber-apk-signer.jar` (or pass `--uber PATH`).
  3. **jarsigner** (JDK) — *fallback only*. Produces a v1-only signature that
     will **not** install on Android 11+. Useful for a quick smoke test.

Useful flags: `--signer {auto,android-sdk,uber,jarsigner}`, `--apk`, `--out`,
`--keystore`, `--uber PATH`, `--skip-patches` (reuse the existing work tree).

## Build it (the manual way)

If you'd rather drive it by hand (e.g. in APK Editor Studio):

1. Install **APK Editor Studio** (<https://qwertycube.com/apk-editor-studio/download/>).
   It bundles apktool, zipalign, and apksigner/jarsigner (V1/V2/V3, all on by default).
2. Unpack: `apktool d wc2.apk -o wc2_unpacked`
3. Make changes. Code lives in the `.smali` and `lib/**/*.so` files; everything
   else is normal APK content. To use these patches, copy the `patches/` folder
   into `wc2_unpacked/` and run the scripts (see order below).
4. Repack: `apktool b wc2_unpacked -o wc2_mod_unsigned.apk`
5. zipalign + sign: open the unsigned APK in APK Editor Studio and click Save
   (zipaligns and signs V1+V2+V3), saving as `wc2_mod_signed.apk`.
6. Install: `adb install -r wc2_mod_signed.apk`

### Patch order

`build_android_apk.py` runs them in this order; do the same if running by hand:

1. `infinite_money.py`
2. `unlock_all_battles.py`
3. `commander_reset.py`
4. `add_battle.py`

Each script is idempotent and refuses to write if the bytes/anchors it expects
aren't there, so re-running is safe. The native patches keep a `*.so.orig`
backup next to each library; `add_battle.py` keys off those backups so you can
change `MISSIONS_TO_ADD` and rebuild without manual cleanup.

### Are the patches independent?

Yes — all four are independent and can be applied in any order or subset. The
order above is just what `build_android_apk.py` happens to use. What each patch
writes to:

| Patch | Touches | Native byte offsets |
|---|---|---|
| `infinite_money.py` | `smali/com/easytech/wc2/Wc2Activity.smali` (Java/Dalvik) | none — no `.so` at all |
| `unlock_all_battles.py` | `lib/<abi>/libworld-conqueror-2.so` | `GUIBattleList::Init`, `GUIMainMenu::Init`, `CMenuState::OnEvent` |
| `commander_reset.py` | `lib/arm64-v8a/libworld-conqueror-2.so` (arm64 only) | `CCommander::*` (`0x5f79x–0x5f91x`) + `GUICommander::SetCommanderInfo` (`0xa58ac`) |
| `add_battle.py` | `assets/*` + `lib/<abi>/libworld-conqueror-2.so` | `GetNumBattles` count knob (`0x63340` on arm64) |

Why they don't collide:

- **`infinite_money.py`** edits a completely separate file tree (smali), so it
  can't interact with the other three.
- The three native patchers all open the same `libworld-conqueror-2.so`, but
  every byte range they write is **disjoint** — on arm64 the commander cluster
  (`0x5f790–0x5f918`, `0xa58ac`), unlock's three gates (`0x833d4`, `0xaa16c`,
  `0xb4e40`) and add_battle's `GetNumBattles` knob (`0x63340`) never overlap, and
  the same holds on every other ABI.
- They share one `*.so.orig` backup, but that's safe regardless of run order:
  `unlock_all_battles.py` / `commander_reset.py` validate against the **live**
  `.so` bytes at their own offsets (the backup is only a snapshot), and
  `add_battle.py` reads pristine bytes from the backup but only at the
  `GetNumBattles` offsets, which no other script ever touches. So the backup
  always holds the right pristine value at the offset each script cares about.

The one caveat: because the backup is shared, deleting `*.so.orig` to reset one
script also drops the safety net for the others. Only delete it when the `.so`
is back to a pristine state (e.g. re-extracted from `wc2.apk`).

See `patches/ADDING_MISSIONS.md` for the full story on adding campaign missions.

## Repo layout

```
wc2.apk                  original APK (Git LFS)
wc2_mod_latest.apk       published modded APK (Git LFS)
build_android_apk.py     one-command build + sign
patches/                 the individual mods (Python) + notes
.gitattributes           routes *.apk through Git LFS
```

Build artifacts (`wc2_unpacked/`, `build/`, `wc2_mod_signed.apk`), tooling
(`apktool.jar`, `tools/`) and your signing key (`wc2.keystore`) are git-ignored.
