- unpack APK (see README.md)
- just add to `smali/com/easytech/Wc2Activity.smali` inside function `mainMenuLoaded()` the following code:
```
const v0, 0x3b9aca00
invoke-static {v0}, Lcom/easytech/wc2/Wc2Activity;->AddMedal(I)V
```