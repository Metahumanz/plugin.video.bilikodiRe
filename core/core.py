# Get
import json, time, os
import requests as r
import xbmcgui, xbmcvfs, xbmcaddon

import core.tools as ts

ADDON=xbmcaddon.Addon()
addon_dir = xbmcvfs.translatePath(ADDON.getAddonInfo('path'))
temp_dir = os.path.join(addon_dir, "tmp")

heads = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.115 Safari/537.36',
}

# 登录生成 qrcode
def login_genqr():
    try:
        res = r.get("https://passport.bilibili.com/x/passport-login/web/qrcode/generate", headers=heads)
        ts.log(res.text)
        res = res.json()
        ts.log(f"CreateQrcodeRequest: {res['code']}, {res['message']}")
    except:
        return False, False
    else:
        return res["data"]["url"], res["data"]["qrcode_key"]

# 验证
def login_checkqr(qrkey):
    res = r.get(f"https://passport.bilibili.com/x/passport-login/web/qrcode/poll?qrcode_key={qrkey}", headers=heads)
    resj = res.json()
    if resj["data"]["code"] != 0:
        xbmcgui.Dialog().ok("Error", f"二维码未正常扫码: \n{resj['data']['code']}: {resj['data']['message']}")
        return False, False
    else:
        return res.cookies, resj["data"]["refresh_token"]

# 本地 cookies.txt 登录
def login_local():
    path = os.path.join(addon_dir, "cookies.json")
    if not os.path.exists(path):
        xbmcgui.Dialog().ok("消失的cookies.json", f"没有 {path} 文件，此文件目前是一个滚木。")
        return
    with open(path, "r") as f:
        res = json.loads(f.read())
        cooks = r.utils.cookiejar_from_dict(res["cookies"])
    # 验证 cookies
    try:
        re = r.get("https://api.bilibili.com/x/web-interface/nav/stat", headers=heads, cookies=cooks)
        resu = re.json()
    except:
        ts.err("RequestsIsNotAvailable")
        xbmcgui.Dialog().ok("Error", "无法获取登录状态")
        return
    # check code
    if resu["code"] == 0:
        ts.log("Cookies Available!")
        return res
    elif resu["code"] == -101:
        ts.err("Cookies Unavailable.")
        return False
    else:
        ts.err(f"GetJson Error: {res['code']}: {res['message']}")
        return False
    
    