# Get
import html, json, re, time, os
import requests as r
import xbmcgui, xbmcvfs, xbmcaddon
from xbmcswift2 import Plugin

import core.tools as ts
import core.secret as srt

ADDON=xbmcaddon.Addon()
addon_dir = xbmcvfs.translatePath(ADDON.getAddonInfo('path'))
temp_dir = xbmcvfs.translatePath('special://temp/plugin.video.bilikodiRe/')

heads = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.bilibili.com/'
}

bili = Plugin()

def init():
    os.makedirs(temp_dir, exist_ok=True)
    srt.update_buvid()

# 项目 icon/fanart/path 模板
def temp_item(a: dict):
    a["fanart"] = os.path.join(addon_dir, "fanart.png") 
    if not "path" in a:
        a["path"] = bili.url_for("passfunc")
    return a


def clean_text(value):
    """Remove Bilibili search highlight HTML from Kodi labels."""
    return html.unescape(re.sub(r"<[^>]+>", "", str(value or ""))).strip()

# 项目图库
def get_image(s):
    match s:
        case "bilikodi" | "logo" | "bilikodire" | "icon":
            return os.path.join(addon_dir, "icon.png")
        case "oldfanart" | "oldbg" | "old_bg" | "bsgm":
            return os.path.join(addon_dir, "old_fanart.png")
        case "fanart" | "bg" | "srow3" | "sr":
            return os.path.join(addon_dir, "fanart.png")
        case _:
            return ""

def getjson(urlpath, urlbase="https://api.bilibili.com", params="", cookies=None, headers=heads):
    if cookies is None:
        cookies = srt.get_cooks()
    try:
        res = r.get(
            f"{urlbase}{urlpath.rstrip('?')}",
            params=params or None,
            cookies=cookies,
            headers=headers,
            timeout=20
        )
        raw = res.json()
    except (r.exceptions.RequestException, ValueError) as exc:
        ts.err(f"GET {urlpath} failed: {exc}")
        xbmcgui.Dialog().ok("Error", "Json 解析失败，疑似返回的不是 Json")
        return
    ts.log(f"GET {urlpath}: HTTP {res.status_code}, code={raw.get('code')}")
    if raw.get("code") != 0:
        xbmcgui.Dialog().ok("请求失败", f"{raw.get('code')}: {raw.get('message', '未知错误')}")
        return 
    if isinstance(raw.get("data"), dict) and "v_voucher" in raw["data"]:
        xbmcgui.Dialog().ok("请求失败", f"接口返回了 v_voucher Captcha 验证")
        return
    return raw

def postjson(
    urlpath,
    data,
    urlbase="https://api.bilibili.com",
    params="",
    cookies=None,
    headers=heads,
    warmup_url=None,
):
    #if isinstance(params, dict): parmas = ts.dict2url(parmas)
    if cookies is None:
        cookies = srt.get_cooks()
    session = r.Session()
    session.cookies.update(cookies)
    try:
        if warmup_url:
            warmup = session.get(warmup_url, headers=headers, timeout=20)
            warmup.raise_for_status()
            # Bilibili's video page supplies the buvid3/b_nut web-session
            # cookies that its mutation endpoints expect. Persist them across
            # Kodi's short-lived plugin interpreter processes.
            srt.merge_cookies(session.cookies.get_dict())
        res = session.post(
            f"{urlbase}{urlpath}?{params}",
            headers=headers,
            data=data,
            timeout=20,
        )
        raw = res.json()
    except (r.exceptions.RequestException, ValueError) as exc:
        ts.err(f"POST {urlpath} failed: {exc}")
        xbmcgui.Dialog().ok("Error", "Json 解析失败，疑似返回的不是 Json")
        return
    srt.merge_cookies(session.cookies.get_dict())
    ts.log(
        f"POST {urlpath}: HTTP {res.status_code}, code={raw.get('code')}, "
        f"message={raw.get('message', '')}"
    )
    return raw


def interaction_headers(bvid):
    """Headers used by the official web-origin video interaction requests."""
    headers = dict(heads)
    headers["Origin"] = "https://www.bilibili.com"
    headers["Referer"] = "https://www.bilibili.com/video/{}/".format(bvid)
    return headers


def interaction_post(urlpath, data, bvid):
    """Warm the web session once, then perform exactly one mutation request."""
    payload = dict(data)
    csrf = payload.get("csrf")
    if csrf:
        payload.setdefault("csrf_token", csrf)
    return postjson(
        urlpath,
        payload,
        headers=interaction_headers(bvid),
        warmup_url="https://www.bilibili.com/video/{}/".format(bvid),
    )

# 记录历史
def rec_history(bv, cid):
    if ts.getSet("rec_history", bool) == False: return
    return postjson("/x/click-interface/web/heartbeat", {
       "bvid": bv,
       "cid": cid,
       "played_time": 0,
       "csrf": srt.get_cookie_value("bili_jct")
    })

###$$$$$$##########
# Default Video items back
def get_viditem(v, direct_play=None):
    i = {}
    context = []
    if v.get('attr', 0) != 0:
        return
    # Up
    uname = ''
    mid = 0
    if 'upper' in v:
        uname = v['upper']['name']
        mid = v['upper']['mid']
    elif 'owner' in v:
        uname = v['owner']['name']
        mid = v['owner']['mid']
    elif 'author' in v:
        uname = v['author']
    elif 'author_name' in v:
        uname = v['author_name']

    if not mid:
        if 'mid' in v:
            mid = v['mid']
        elif 'uid' in v:
            mid = v['uid']
        elif 'author_mid' in v:
            mid = v['author_mid']

    if 'pic' in v:
        pic = v['pic']
    elif 'cover' in v:
        pic = v['cover']
    else:
        pic = ''
    
    if pic.startswith('//'): # 缺 https
        pic = "https:" + pic

    if 'bvid' in v:
        bvid = v['bvid']
    elif 'history' in v and 'bvid' in v['history']:
        bvid = v['history']['bvid']

    if 'title' in v:
        title = clean_text(v['title'])

    if 'cid' in v:
        cid = v['cid']
    elif 'ugc' in v and 'first_cid' in v['ugc']:
        cid = v['ugc']['first_cid']
    elif 'history' in v and 'cid' in v['history']:
        cid = v['history']['cid']
    else:
        cid = 0

    if 'duration' in v:
        if isinstance(v['duration'], int):
            duration = v['duration']
        else:
            duration = parse_duration(v['duration'])
    elif 'length' in v:
        if isinstance(v['length'], int):
            duration = v['length']
        else:
            duration = parse_duration(v['length'])
    elif 'duration_text' in v:
        duration = parse_duration(v['duration_text'])
    else:
        duration = 0
    
    pubtime = ""
    year = 0
    if 'pubdate' in v:
        pubtime = ts.ts2date(v['pubdate'], ctype=2)
        year = int(ts.ts2date(v['pubdate'], custom="%Y"))
    
    plot = parse_plot(v)
    
    # Kodi Metadata
    info = {
         "mediatype": "movie",
         "duration": duration,
         "title": title,
         "plot": plot
    }
    if uname: info["director"] = uname
    if pubtime: info["date"] = pubtime
    if year: info["year"] = year
    if direct_play is None:
        direct_play = ts.getSet("video_click_action") == "play"

    play_url = bili.url_for("bvplay", bv=bvid, cid=cid)
    detail_url = bili.url_for("video_detail", bv=bvid)
    # Collection-like pages normally open details.  A favourites entry is an
    # explicit video choice, so its caller can opt into one-click playback and
    # keep details available from the context menu.
    if direct_play:
        context = [("视频详情", "Container.Update({})".format(detail_url))]
    else:
        context = [("立即播放", "PlayMedia({})".format(play_url))]
    if uname: context.append((f"跳转到 {uname}", f"Container.Update({bili.url_for('user_page', uid=mid)})"))
    i = {
       "label": title,
       "icon": pic,
       "fanart": pic,
       "path": play_url if direct_play else detail_url,
       "info": info,
       "context_menu": context,
       "is_playable": bool(direct_play)
    }
    
    return i

def parse_plot(item):
    plot = ""
    
    # Up主信息
    if 'upper' in item:
        plot += f"UP: {item['upper']['name']} ({item['upper']['mid']})\n"
    elif 'owner' in item:
        plot += f"UP: {item['owner']['name']} ({item['owner']['mid']})\n"
    elif 'author' in item:
        plot += f"UP: {item['author']}"
        if 'mid' in item:
            plot += f' ({item["mid"]})'
        plot += '\n'
    
    # default info
    if 'bvid' in item:
        plot += f"{item['bvid']}\n"
    if 'pubdate' in item:
        plot += f"{ts.ts2date(item['pubdate'])}\n"
    if 'copyright' in item and str(item['copyright']) == '1':
        plot += '未经作者授权禁止转载\n'
    
    state = ''
    if 'stat' in item:
        stat = item['stat']
        if 'view' in stat:
            state += f"{ts.n2num(stat['view'])}播放 | "
        elif  'play' in stat:
            state += f"{ts.n2num(stat['play'])}播放 | "
        if 'like' in stat:
            state += f"{ts.n2num(stat['like'])}点赞 | "
        if 'coin' in stat:
            state += f"{ts.n2num(stat['coin'])}投币 | "
        if 'favorite' in stat:
            state += f"{ts.n2num(stat['favorite'])}收藏 | "
        if 'reply' in stat:
            state += f"{ts.n2num(stat['reply'])}评论 | "
        if 'danmaku' in stat:
            state += f"{ts.n2num(stat['danmaku'])}弹幕 | "
        if 'share' in stat:
            state += f"{ts.n2num(stat['share'])}分享 | "
    elif 'cnt_info' in item:
        stat = item['cnt_info']
        if 'play' in item:
            state += f"{ts.n2num(stat['play'])}播放 | "
        if 'collect' in stat:
            state += f"{ts.n2num(stat['collect'])}收藏 | "
        if 'danmaku' in stat:
            state += f"{ts.n2num(stat['danmaku'])}弹幕 | "
    else:
        if 'play' in item and isinstance(item['play'], int):
            state += f"{ts.n2num(item['play'])}播放 | "
        if 'comment' in item and isinstance(item['comment'], int):
            state += f"{ts.n2num(item['comment'])}评论 | "
    
    if state:
        plot = plot+state+"\n"
    plot += "\n"
    
    # achievement
    if 'achievement' in item and item['achievement']:
        plot += f"{ts.ctxt(item['achievement'], 'orange')}\n"
    if 'rcmd_reason' in item and isinstance(item['rcmd_reason'], str) and item['rcmd_reason']:
        plot += f"{ts.ctxt(item['rcmd_reason'], 'orange')}\n"
    # Description
    if 'desc' in item and item['desc']:
        plot += f"{item['desc']}"
    elif 'description' in item and item['description']:
        plot += f"{item['description']}"
    
    return plot

def parse_duration(duration_text):
    parts = duration_text.split(':')
    duration = 0
    for part in parts:
        duration = duration * 60 + int(part)
    return duration


#############$#########
# 登录生成 qrcode
def login_genqr():
    try:
        res = r.get("https://passport.bilibili.com/x/passport-login/web/qrcode/generate", headers=heads)
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
        ts.err(f"GetJson Error: {resu['code']}: {resu['message']}")
        return False

def check_login():
    cooks = srt.get_cooks()
    try:
        re = r.get("https://api.bilibili.com/x/web-interface/nav", headers=heads, cookies=cooks, timeout=20)
        resu = re.json()
    except:
        ts.err("RequestsIsNotAvailable")
        xbmcgui.Dialog().ok("Error", "无法获取登录状态")
        return
    # check code
    logged_in = resu.get("code") == 0 and bool(resu.get("data", {}).get("isLogin"))
    ts.log("Login status: {}".format("logged-in" if logged_in else "anonymous"))
    return logged_in
