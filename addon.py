# Bilikodi Reborn Entry
import json, os, time
import requests as r
# Core
import core.tools as ts
import core.core as c
import core.secret as srt
# xbmcswift (新的我们使用了这个78来构建我们的菜单）
from xbmcswift2 import Plugin, xbmc, xbmcplugin, xbmcvfs, xbmcgui, xbmcaddon

try:
    xbmc.translatePath = xbmcvfs.translatePath
except AttributeError:
    pass

bili = c.bili

# version
version = "v1.0.16"
debug = True


# passfunc
@bili.route("/pass/")
def passfunc():
    pass

###############
# 主页功能
###############
@bili.route("/")
def index():
    c.init()
    items = [
      {"label": "首页推荐", "path": bili.url_for("feed_home", page=1)},
      # {"label": "我的账号", "path": bili.url_for("user")},
      {"label": "插件设置", "path": bili.url_for("open_set")},
      {"label": "登录帐号", "path": bili.url_for("login_qrcode")},
      {"label": "Bilikodi Reborn 帮助", "path": bili.url_for('help')},
    ]
    return items

@bili.route("/feed_home/<page>")
def feed_home(page):
    items = []
    params = {"fresh_idx": int(page), "ps": 20}
    params = ts.dict2url(params)
    res = c.getjson("/x/web-interface/wbi/index/top/feed/rcmd?", params=params)
    for x in res["data"]["item"]:
        if not x["bvid"]:
            continue
        items.append(c.get_viditem(x))
    items.append({"label": ts.ctxt(f"下一页 (目前在第 {page} 页)", color="yellow"), "path": bili.url_for("feed_home", page=int(page)+1)})
    return items

########################
# PlayVideo
@bili.route("/bvplay/<bv>/<cid>")
def bvplay(bv, cid):
    legacy_mode = True
    if cid == 0:
        res = c.getjson("/x/web-interface/view", params=ts.dict2url({"bvid": bv}))
        if res["data"]["code"] == 0:
            xbmcgui.Dialog().ok("Error", "无法获取视频 cid")
            return
        cid = res["data"]['pages'][0]['cid']
    
    url = "/x/player/playurl"
    qn = 64
    params = {
        'bvid': bv,
        'cid': cid,
        'qn': qn,
        'fnval': 4048,
        'fourk': 1,
        # "platform": "html5"
    }
    if legacy_mode:
        params = {
            'bvid': bv,
            'cid': cid,
            'qn': qn,
            'fnval': 1,
            'platform': 'html5'
        }
    # if legacy_mode: params["platform"] = "html5"
    params = srt.getwbikey(params)
    res = c.getjson(url, params=ts.dict2url(params))
    
    # code
    if res["code"] != 0:
        xbmcgui.Dialog().ok("Error", f"{res['code']}: {res['message']}")
        return
    
    resu = res["data"]
    
    # Dash format
    if "dash" in resu:
        mpd = ts.genmpd(resu["dash"])
        mpdpath = os.path.join(c.temp_dir, f"{cid}.mpd")
        resu2 = False
        with open(mpdpath, "w") as f:
            resu2 = f.write(mpd)
        if resu2 == False:
            xbmcgui.Dialog().ok("Error", "写入mpd文件失败")
            return
        
        video_url = {
            'path': 'file://{}'.format(mpdpath),
            'properties': {
                'inputstream': 'inputstream.adaptive',
                'inputstream.adaptive.manifest_type': 'mpd',
                'inputstream.adaptive.manifest_headers': 'Referer=https://www.bilibili.com',
                'inputstream.adaptive.stream_headers': 'Referer=https://www.bilibili.com'
            }
        }
    
    # mp4 h264 format
    if 'durl' in resu:
        video_url = resu["durl"][0]["url"]
        
    bili.set_resolved_url(video_url)
    
########################
# Login
@bili.route("/login_qrcode/")
def login_qrcode():
    url, key = c.login_genqr()
    if url == False:
        xbmcgui.Dialog().ok("Error", "无法获取 qrcode url")
        ts.err("Failed to Create a Qrcode")
        return
    path = os.path.join(c.temp_dir, "qrcode.png")
    qrimg = ts.qrgen(url, path)
    # Menu
    i = [
       {
         "label": "二维码登录",
         "icon": qrimg,
         "path": bili.url_for("passfunc"),
         "info": { "plot": "使用官方客户端噼里啪啦扫码。。限时 180s 内扫码，过期就失效\n扫描完成后选择 “检查二维码状态” " }
       },
       {
         "label": "检查二维码状态",
         "path": bili.url_for("login_checkqr", key=key)
       },
       {
         "label": "通过 Json 格式的 cookies.txt 导入 cookies",
         "path": bili.url_for("login_local"),
       }
    ]
    return i

@bili.route("/login_checkqr/<key>")
def login_checkqr(key):
    cooks, refkey = c.login_checkqr(key)
    if cooks == False: return
    # 保存内容
    user = bili.get_storage("user")
    user["cookies"] = str(r.utils.dict_from_cookiejar(cooks))
    user["refkey"] = refkey
    user.sync() # Sync storage immediately
    # 弹弹窗显示
    xbmcgui.Dialog().ok("Good Work!", "登录成功, you did very well")
    ts.back()

@bili.route("/login_local/")
def login_local():
    sel = xbmcgui.Dialog().yesno("确定？", "将从 插件根目录/cookies.json 中获取cookies/refresh_key参数并尝试登录\n同时也可能会覆盖你原有的登录信息")
    if sel == True:
        resu = c.login_local()
        if resu == False:
            xbmcgui.Dialog().ok("Error", "此 Cookie 可能无效")
            return
        user = bili.get_storage("user")
        ts.log(str(resu))
        user["cookies"] = resu["cookies"]
        user["refkey"] = resu["refkey"]
        user.sync()
        # refkey
        xbmcgui.Dialog().ok("Good Work!", "此 Cookie 可用! you did very well\n为保证账户安全，请及时删除 插件根目录的cookies.json 防止盗号")


@bili.route('/open_set/')
def open_set():
    bili.open_settings()

# help
@bili.route("/help/")
def help():
    a = f"到达流媒体飞沫天 ~ Bilikodi Reborn {version}\n"
    a += "重构的 Bilikodi 打赢复活赛，基于bilibili-api实现\n"
    a += "应该适用于 Kodi 19~22 所有版本\n"
    a += "搜索中文关键词请使用中文输入法或者其他辅助插件"
    xbmcgui.Dialog().ok("帮助/说明", a)

if __name__ == "__main__":
    bili.run()