###############################
#     Bilikodi Reborn addon.py
#   插件入口
#   原来的写的太神作了我想，所以重构了qwq
###############################
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
version = "v1.0.21"
debug = True

# passfunc
@bili.route("/pass/")
def passfunc():
    pass

###############
# 主页路由
###############
@bili.route("/")
def index():
    c.init()
    i = [
      {"label": "首页推荐", "path": bili.url_for("feed_home", page=1)},
      {"label": "我的投稿视频", "path": bili.url_for("user_upload", uid=srt.get_uid(), page=1)},
      {"label": "我的关注", "path": bili.url_for("user_sub", uid=srt.get_uid(), page=1)},
      {"label": "我的收藏夹", "path": bili.url_for("user_fav", uid=srt.get_uid())},
      # {"label": "我的账号", "path": bili.url_for("user")},
      {"label": "插件设置", "path": bili.url_for("open_set")},
      # {"label": "登录帐号", "path": bili.url_for("login_qrcode")},
      {"label": "Bilikodi Reborn 帮助", "path": bili.url_for('help')},
    #  {"label": "大家好我是棍母"}
    ]
    items = []
    for x in i:
        items.append(c.temp_item(x))
    
    return items

@bili.route("/feed_home/<page>")
def feed_home(page):
    items = []
    params = {"fresh_type": ts.getSet("home_fresh"), "fresh_idx": int(page), "ps": 20}
    params = ts.dict2url(params)
    res = c.getjson("/x/web-interface/wbi/index/top/feed/rcmd?", params=params)
    if not isinstance(res, dict): return
    
    for x in res["data"]["item"]:
        if not x["bvid"]:
            continue
        items.append(c.get_viditem(x))
    items.append({"label": ts.ctxt(f"下一页 (目前在第 {page} 页)", color="yellow"), "path": bili.url_for("feed_home", page=int(page)+1)})
    return items

########################
#  User/用户/Up主 路由
@bili.route("/user/<uid>/")
def user_page(uid):
    pass

# 关注列表
@bili.route("/user_sub/<uid>/<page>/")
def user_sub(uid, page):
    ps = 50
    params = ts.dict2url({
        "vmid": uid,
        "pn": int(page),
        "ps": ps
    })
    res = c.getjson("/x/relation/followings", params=params)
    if not isinstance(res, dict): return
    
    items = []
    for x in res["data"]["list"]:
        plot = ""
        is_subto = False
        plot += x["sign"] + "\n\n"
        if x["attribute"] == 6:
            is_subto = True
            plot += ts.ctxt("我想你两可能是 Friend", color="pink")
        if x["official_verify"]["type"] != -1:
            plot += "\n" + ts.ctxt(x["official_verify"]["desc"], color="yellow")
        
        if is_subto:
            label = ts.ctxt(x["uname"], color="pink")
        else:
            label = x["uname"]
        
        items.append({
            "label": label,
            "path": bili.url_for("passfunc"),
            "icon": x["face"],
            "info": { "plot": plot }
        })
        
    maxpage = res["data"]["total"] // ps
    page = int(page)
    if res["data"]["total"] % ps != 0:
        maxpage += 1
    if maxpage > page:
        items.append(c.temp_item({
          "label": ts.ctxt(f"下一页 ({page}/{maxpage})", color="yellow"),
          "path": bili.url_for("user_sub", uid=uid, page=page+1)
        }))
    
    return items

# 投稿明细
@bili.route("/user_uploaded/<uid>/<page>")
def user_upload(uid, page):
    params = {
        "mid": uid,
        "pn": page
    }
    params = ts.dict2url(srt.getwbikey(params))
    res = c.getjson("/x/space/wbi/arc/search", params=params)
    if not isinstance(res, dict): return
    
    items = []
    for x in res["data"]["list"]["vlist"]:
        items.append(c.get_viditem(x))
    
    page = int(page)
    maxpage = res["data"]["page"]["count"] // res["data"]["page"]["ps"]
    if res["data"]["page"]["count"] % res["data"]["page"]["ps"] != 0:
        maxpage += 1
    if maxpage > page:
        items.append(c.temp_item({
            "label": ts.ctxt(f"下一页 ({page}/{maxpage})", color="yellow"),
            "path": bili.url_for("user_upload", uid=uid, page=page+1)
        }))
    return items

# 收藏
@bili.route("/fav_folder/<uid>")
def user_fav(uid):
    params = ts.dict2url({"up_mid": int(uid)})
    res = c.getjson("/x/v3/fav/folder/created/list-all", params=params)
    if not res: return
    if res["code"] != 0:
        xbmcgui.Dialog().ok("Error", f"{res['code']}: {res['message']}")
        return
    
    items = []
    for x in res["data"]["list"]:
        idx = x["id"]
        params=ts.dict2url({"media_id": int(idx)})
        info = c.getjson("/x/v3/fav/folder/info", params=params)
        if not res: continue
        if res["code"] != 0: continue
        
        plot = ""
        i = info["data"]
        up = i["upper"]
        plot += f"By {up['name']} ({up['mid']})\n"
        plot += f"创建时间: {ts.ts2date(i['ctime'])}\n"
        plot += f"已收藏 {i['media_count']} 个视频\n"
        plot += "\n\n"
        plot += i["intro"]
        
        items.append({
           "label": i["title"],
           "icon": i["cover"],
           "fanart": i["cover"],
           "path": bili.url_for("fav_con", mlid=idx, page=1),
           "info": {
              "plot": plot
           }
        })
    return items

# 收藏夹内容
@bili.route("/fav_content/<mlid>/<page>")
def fav_con(mlid, page):
    page = int(page)
    params = ts.dict2url({
        "media_id": int(mlid),
        "order": "mtime",
        "ps": 15,
        "pn": page
    })
    res = c.getjson("/x/v3/fav/resource/list", params=params)
    if not res: return
    if res["code"] != 0:
        xbmcgui.Dialog().ok("Error", f"{res['code']}: {res['message']}")
        return
    
    items = []
    res = res["data"]
    next_page = res["has_more"]
    
    for x in res["medias"]:
        if x["type"] != 2: continue
        items.append(c.get_viditem(x))
    
    # 下一页逻辑
    if next_page:
        items.append(c.temp_item({
            "label": ts.ctxt("下一页", color="yellow"),
            "path": bili.url_for("fav_con", mlid=int(mlid), page=page+1)
        }))
    
    return items


########################
# PlayVideo 路由
@bili.route("/bvplay/<bv>/<cid>")
def bvplay(bv, cid):
    legacy_mode = True
    if cid == 0 or cid == "0":
        res = c.getjson("/x/web-interface/view", params=ts.dict2url({"bvid": bv}))
        if res["code"] != 0:
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
    
    c.rec_history(bv, cid)  
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

@bili.route("/check_login/")
def check_login():
    if c.check_login():
        xbmcgui.Dialog().ok("Good", "您已登录")
    else:
        xbmcgui.Dialog().ok("Bad", "您还没登录")


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