- unpack APK (see README.md)
- just add to `smali/com/easytech/Wc2Activity.smali` inside function `mainMenuLoaded()` the following code:
```
const v0, 0x3b9aca00

invoke-static {v0}, Lcom/easytech/wc2/Wc2Activity;->AddMedal(I)V

const/4 v0, 0x0

invoke-static {v0}, Lcom/easytech/wc2/Wc2Activity;->PurchaseSuccess(I)V

const/4 v0, 0x1

invoke-static {v0}, Lcom/easytech/wc2/Wc2Activity;->PurchaseSuccess(I)V

const/4 v0, 0x2

invoke-static {v0}, Lcom/easytech/wc2/Wc2Activity;->PurchaseSuccess(I)V

const/4 v0, 0x3

invoke-static {v0}, Lcom/easytech/wc2/Wc2Activity;->PurchaseSuccess(I)V
```