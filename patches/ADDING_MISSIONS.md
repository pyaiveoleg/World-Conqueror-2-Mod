# Adding new campaign missions to WC2

How to register **N** new missions in a faction's campaign (e.g. 100 clones of
Blitzkrieg for axis). Distilled from the work that produced
`add_battle_axis11.py` + `patch_axis11_native.py`.

There are **two halves** to a working mission:

1. **Data** — XML/binary assets the engine reads at runtime. Roughly six
   distinct anchor points per mission.
2. **Binary** — a hardcoded per-faction count inside
   `libworld-conqueror-2.so` (`GetNumBattles`) that has to be raised so the
   UI loop runs `N` times.

If either half is incomplete, the new button silently fails to appear —
that's the whole "kнопка не появилась" lesson from the 11-th-mission test.

---

## The six anchor points (per mission `K`, faction `F`)

For each new mission `(F, K)` you must add:

| # | Anchor | Lives in | What it is |
|---|---|---|---|
| 1 | `assets/battle_F<K>.xml` | one file per mission | country list, area state, dialogue |
| 2 | `assets/battle_F<K>.bin` | one file per mission | binary area mask referenced from the xml's `areasenable=` attribute |
| 3 | `<battle name="F K">` inside `assets/battlelist.xml` | one entry | world-map pin: `centerx/centery`, flags, arrows, victory thresholds, `open="1"` |
| 4 | `F battle name K` + `F battle intro K` in **every** `assets/stringtable_*.xml` | 12 stringtables (6 languages × phone+iPad) | button label + intro text |
| 5 | `button_F_<KK>.png` alias in `assets/selbattle_hd.xml` | one atlas entry | sprite for the campaign button (KK is zero-padded: 01, 02, …, 11, …, 99) |
| 6 | `text_F_<KK>.png` alias in **every** `assets/battlename_<lang>_hd.xml` | 6 localised atlases | localised mission-name graphic (drawn into the texture, hence per-language) |

Skipping any one of these:

- Missing **(1) or (2)** → game crashes when the player taps the mission.
- Missing **(3)** → `LoadBattleList` can't find the battle by name, no map
  pin, click-through fails.
- Missing **(4)** → button shows the raw key string ("axis battle name 11").
- Missing **(5) or (6)** → `ecTextureRes::GetImage` returns NULL,
  `GUIBattleItem::Init` builds a widget that draws nothing → invisible
  button (this was the test-run failure).

Stringtable entries can be cloned trivially. Atlas sprites can either be
**aliased to an existing rectangle** (cheap, looks identical to the cloned
mission) or **packed as a new region** into the texture (real new art —
requires re-baking the `.webp` / `.png` and updating every reference).

### Heads-up about line endings

`battle_<faction><N>.xml` files in this build use **CRLF**, everything
else (battlelist, stringtables, atlases) uses **LF**. Preserve byte-for-byte
or the tinyxml loader can subtly misbehave on some entries.

---

## The binary count knob

`GetNumBattles(int faction)` returns a value from the per-ABI table
`{axis=10, allies=10, wto=7, nato=7, multiplay=12}`. Symbol:
`_Z13GetNumBattlesi`.

`GUIBattleList::Init` loops `0..GetNumBattles(faction)-1` and creates one
widget per iteration. To get **N** buttons you raise that slot to **N**.

### Per-ABI patch recipe (for new count `N`)

| ABI | File offset | What to write | Constraint |
|---|---|---|---|
| `arm64-v8a` | `0x63340` | 4 bytes: `MOVZ w3, #N` = `0x52800003 \| (N << 5)`, little-endian | `N ≤ 65535` (single MOVZ). Above that needs MOVZ+MOVK, no slack in the function — would require a code cave. |
| `armeabi-v7a` | `0x109774` | 1 byte: `N` | `N ≤ 255` |
| `armeabi` | `0x10511C` | 1 byte: `N` | `N ≤ 255` |
| `x86` | `0x4EF43..0x4EF46` | 4 bytes: `N` little-endian (`imm32`) | unlimited (4-byte imm) |
| `x86_64` | `0x66839..0x6683C` | 4 bytes: `N` little-endian (`imm32`) | unlimited (4-byte imm) |

#### MOVZ encoding cheat-sheet (Rd = w3)

```
N=10   -> 43 01 80 52    (original)
N=11   -> 63 01 80 52    (the test-run patch)
N=100  -> 83 0c 80 52
N=200  -> 03 19 80 52
N=255  -> e3 1f 80 52
N=1000 -> 03 7d 80 52
```

General formula: `bytes(0x52800003 | (N << 5), little-endian, 4)`.

### ⚠ arm64-v8a register-reuse caveat

The arm64 build emits **one** `mov w3, #10` and reuses `w3` to write both
`array[axis]` and `array[allies]` before reloading `w3` with 12 for
multiplay. There is no slack inside the function for an instruction
insert, so:

> **On arm64, raising the axis count to N inevitably raises the allies
> count to N too.**

`x86`, `x86_64`, `armeabi`, `armeabi-v7a` are each surgical — only the
faction you patch is affected on those ABIs.

You have three options on arm64:

1. **Mirror the data** (what `add_battle_axis11.py` does): also clone
   allies 1..N so the allies tab doesn't try to load missing assets and
   crash. Cheapest. Allies tab just gets `N` identical Blitzkrieg-style
   buttons.
2. **Code cave**: redirect 4 bytes inside `GetNumBattles` to a free spot
   in `.text` (e.g. zero-padding at the end of the section), write
   `mov w3, #N; str w3, [x29,#0x10]; mov w3, #10; b back`, return.
   Surgical, axis-only. More work, more risk.
3. **Ignore allies** — only safe if you never open the allies tab.
   Don't rely on this.

For "100 clones of Blitzkrieg for axis" the right answer is **(1)**: the
work to clone allies once is small compared to cloning axis 90 times.

### Other binary checks (mostly benign)

- `CheckMD5::INfile` (at `0x57d08` on arm64) hashes the hardcoded
  `battle_axis1.bin..battle_axis10.bin` and matching `.xml` paths against
  a manifest. The new `battle_axis11.bin..N.bin` are not in that list and
  therefore not checked. For offline play / a modded APK that's fine — the
  check only catches **tampering with the original 10**, not new files.
  If you also modify e.g. `battle_axis1.xml` you'd need the existing
  `unlock_all_battles.py`-style approach to bypass MD5.
- `GUIBattleList::Init`'s lock-branch (`b.gt 0xb4d98` at `0xb4e40`) hides
  battles above `played + 1`. `unlock_all_battles.py` already neuters it.
  Without that patch, only the first played-count+1 of your 100 new
  buttons would be tappable.

---

## Worked recipe: 90 new axis missions, indices 11..100

Goal: clones of Blitzkrieg occupying axis slots 11..100, all visually
identical to axis 1. We accept the arm64 side effect and mirror everything
to allies as well.

### 1. Generate data clones for axis 11..100 (and allies 11..100)

The existing `add_battle_axis11.py` was already extended to handle both
factions. To turn it into a batch tool, change the top of the file:

```python
SRC_INDEX = 1
NEW_INDICES = range(11, 101)   # was: NEW_INDEX = 11
FACTIONS = ("axis", "allies")
```

and wrap each `patch_*` helper in a loop over `NEW_INDICES`. The anchor
search logic inside the existing helpers stays unchanged — it always
anchors to entry `1` and inserts the new entry right after; multiple
inserts just stack up in reverse order, which doesn't matter for the
engine (battlelist + stringtables are keyed lookups, not positional).

If you want strict ascending order in the source files, anchor each new
entry `K` to entry `K-1` instead of always to entry `1`.

**Atlas entries** can all alias the same `_01.png` rectangle — every
button will look like Blitzkrieg. That's the whole point of "clones".

### 2. Patch `GetNumBattles` to 100 across all ABIs

Take `patch_axis11_native.py` and replace the hardcoded patched bytes
with the recipe table above for `N=100`:

```python
N = 100
PATCHES = (
    Patch("arm64-v8a",   0x63340,
          bytes.fromhex("43018052"),
          (0x52800003 | (N << 5)).to_bytes(4, "little"),
          "GetNumBattles axis 10 -> N (also bumps allies)"),
    Patch("armeabi-v7a", 0x109774, b"\x0a", bytes([N]), "rodata axis slot 10 -> N"),
    Patch("armeabi",     0x10511C, b"\x0a", bytes([N]), "rodata axis slot 10 -> N"),
    Patch("x86",         0x4EF43,  b"\x0a\x00\x00\x00", N.to_bytes(4, "little"),
          "movl imm32 axis slot 10 -> N"),
    Patch("x86_64",      0x66839,  b"\x0a\x00\x00\x00", N.to_bytes(4, "little"),
          "movl imm32 axis slot 10 -> N"),
)
```

Note the **width** change for x86 / x86_64: at `N=11` we got away with a
1-byte change (0x0a → 0x0b), but for `N ≥ 16` you should patch the full
4-byte imm32 to be encoding-safe. The script already refuses to write if
the original bytes don't match, so it's safe to widen the slice.

### 3. (If needed) Bypass the lock-branch

If you want all 100 missions playable without grinding through the
previous ones, run the existing `unlock_all_battles.py`. It neuters the
`SetEnable(false); locked=1` branch inside `GUIBattleList::Init` across
all ABIs.

### 4. Repack the APK and reinstall

Standard apktool flow:
```
apktool b wc2_unpacked -o wc2_modded.apk
# sign with your debug/release keystore, then install
```

---

## Caveats and edge cases

- **UI scroll**: `GUIBattleList` uses `CTouchInertia` and was designed
  with ~10 items in mind. 100 items render as a very long vertical list
  — scrollable on touch, but the inertia tuning was set for the short
  list. Acceptable for a test, may want tuning later.
- **World-map pin overlap**: all clones inherit axis 1's `centerx/centery`
  coordinates from `battlelist.xml`, so 100 pins stack on top of one
  another in central Europe. The campaign list shows them all in order,
  but only the topmost map pin is clickable. For real new missions, give
  each entry unique map coordinates.
- **Filename format**: the engine builds runtime paths via
  `sprintf("battle_F%d.xml", index+1)` (`GetBattleFileName` at `0x6343c`),
  so any positive `index+1` works — there is **no width or zero-padding**
  for the xml/bin filenames. The atlas sprite names, on the other hand,
  use `%02d` (`button_axis_01.png`), which works for indices 1..99. For
  100+ the engine would query `button_axis_100.png` — which is a
  valid 3-digit name and resolves fine in our atlas; just make sure the
  alias is written without zero-padding for 3-digit indices.

  → For mission 100: alias `button_axis_100.png` and `text_axis_100.png`,
    not `button_axis_100` with zero-padding past 2 digits.
- **Real new art**: aliases only work when art is reused. For unique
  per-mission artwork you must (a) repack `selbattle_hd.webp` /
  `battlename_<lang>_hd.png` with new regions and (b) update every
  `<Image x= y= w= h=>` rectangle to point at the new region. Atlas
  re-baking is out of scope here.
- **iPad assets**: `battlename_*_hd.{xml,png}` is shared between phone
  and iPad; only stringtables have explicit `_iPad` variants. No
  separate atlas changes needed for iPad.
- **Multiplay**: `multiplay` is faction id 4 and goes through a
  **different** branch in `GUIBattleItem::Init` (uses an indexed pointer
  array at `0x1e44b0` instead of sprintf). Adding multiplay missions
  beyond 12 requires extending that pointer array — strictly more
  invasive than axis/allies/wto/nato.
