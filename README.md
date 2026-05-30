# World-Conqueror-2-Mod
My custom World Conqueror 2 Mods. 

In current mod:
- Infinite money
- All missions unlocked (even NATO/WTO, it will appear locked, but just click and they are all open)
- Fixed progress clear after reboot on new Android versions
- Added progress reset on Commander and Medals (if you want to increase complexity level) - **only on arm64-v8a**
- You can add your own missions (see patches/add_battle.py)

See `patches` folder to understand how to do it.

There is an original APK which I have modified in this repo too.

1. Install:
    - Apk Editor Studio (https://qwertycube.com/apk-editor-studio/download/). It has built-in:
- apktool (compiler + decompiler)
- zipalign (alignment required for all android 11+)
- apksigner/jarsigner (signature, there are three versions V1, V2, V3 - all are needed, all are done by default)
2. Unpack the APK: `apktool d wc2.apk -o wc2_unpacked`
3. Make changes
- The code is in the .smali and .so files, the rest is as usual
- If you want use my patches: move `patches` folder inside `wc2_unpacked` and run python scripts
4. Pack the APK `apktool b wc2_unpacked -o wc2_mod_unsigned.apk`
5. zipalign + sign
- The easiest way is to just open the APK in Apk Editor Studio, do not make changes and click save, save with the name `wc_mod_signed.apk`
6. Install - the easiest way is using ADB: `adb install -r wc2_mod_signed.apk`
