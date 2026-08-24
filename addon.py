###############################
#     Bilikodi Reborn addon.py
#   插件入口
#   原来的写的太神作了我想，所以重构了qwq
###############################
import json, os, time
import urllib.parse
import requests as r
# Core
import core.tools as ts
import core.core as c
import core.secret as srt
from resources.lib.playback.dash import (
    DashPlaybackError,
    ManifestServerError,
    attach_subtitles,
    play_dash,
)
from resources.lib.playback.danmaku import DanmakuError, prepare_danmaku
from resources.lib.playback.subtitles import (
    BilibiliSubtitleError,
    prepare_bilibili_subtitles,
)
from resources.lib.playback.live import (
    LivePlaybackError,
    PI4_LIVE_MAX_QN,
    select_live_stream,
)
from resources.lib.playback.live_danmaku import write_live_context
from resources.lib.playback.progress import write_playback_context
from resources.lib.playback.settings import playback_settings
from resources.lib.dynamic_feed import normalize_dynamic
# xbmcswift (新的我们使用了这个78来构建我们的菜单）
from xbmcswift2 import ListItem, Plugin, xbmc, xbmcplugin, xbmcvfs, xbmcgui, xbmcaddon

try:
    xbmc.translatePath = xbmcvfs.translatePath
except AttributeError:
    pass

bili = c.bili

# version
version = "v1.5.4"
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
      {"label": "入站必刷", "path": bili.url_for("feed_popular")},
      {"label": "哔哩哔哩直播", "path": bili.url_for("live_index")},
      {"label": "观看历史", "path": bili.url_for("history", max_id=0, view_at=0)},
      {"label": "稍后再看", "path": bili.url_for("watch_later")},
      {"label": "视频动态", "path": bili.url_for("dynamic_feed", page=1, offset="0")},
      {"label": "我的账户", "path": bili.url_for("user_page", uid=srt.get_uid())},
      {"label": "我的投稿视频", "path": bili.url_for("user_upload", uid=srt.get_uid(), page=1)},
      {"label": "我的关注", "path": bili.url_for("user_sub", uid=srt.get_uid(), page=1)},
      {"label": "我的收藏夹", "path": bili.url_for("user_fav", uid=srt.get_uid())},
      {"label": "搜索", "path": bili.url_for("search_ready")},
      {"label": "二维码登录", "path": bili.url_for("login_qrcode")},
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
    params = {"fresh_type": ts.getSet("home_fresh"), "fresh_idx": int(page), "ps": ts.getSet("ps.home", int)}
    params = ts.dict2url(params)
    res = c.getjson("/x/web-interface/wbi/index/top/feed/rcmd", params=params)
    if not isinstance(res, dict): return
    
    for x in res["data"]["item"]:
        if not x["bvid"]:
            continue
        items.append(c.get_viditem(x))
    items.append({"label": ts.ctxt(f"下一页 (目前在第 {page} 页)", color="yellow"), "path": bili.url_for("feed_home", page=int(page)+1)})
    return items

# 入站必刷
@bili.route("/feed_popular/")
def feed_popular():
    res = c.getjson("/x/web-interface/popular/precious")
    if not isinstance(res, dict): return
    
    items = []
    for x in res["data"]["list"]:
        items.append(c.get_viditem(x))
    return items


LIVE_API = "https://api.live.bilibili.com"
LIVE_HEADERS = {
    "User-Agent": c.heads["User-Agent"],
    "Referer": "https://live.bilibili.com/",
    "Origin": "https://live.bilibili.com",
}


def _live_room_item(room):
    room_id = room.get("roomid") or room.get("room_id") or room.get("id")
    if not room_id:
        return None
    title = c.clean_text(room.get("title") or "直播间")
    uname = room.get("uname") or room.get("username") or ""
    area = room.get("area_name") or room.get("parent_name") or ""
    popularity = room.get("online") or room.get("watched_show", {}).get("num") or 0
    cover = (
        room.get("keyframe")
        or room.get("cover")
        or room.get("room_cover")
        or room.get("cover_from_user")
        or room.get("face")
        or ""
    )
    plot = []
    if uname:
        plot.append("主播：{}".format(uname))
    if area:
        plot.append("分区：{}".format(area))
    if popularity:
        plot.append("人气：{}".format(ts.n2num(popularity)))
    return {
        "label": title,
        "path": bili.url_for("live_play", room_id=room_id),
        "icon": cover,
        "fanart": cover,
        "is_playable": True,
        "info": {
            "mediatype": "video",
            "title": title,
            "plot": "\n".join(plot),
        },
    }


@bili.route("/live/")
def live_index():
    items = [
        {"label": "推荐直播", "path": bili.url_for("live_recommend", page=1)},
    ]
    if _logged_in():
        items.append({"label": "我关注的直播", "path": bili.url_for("live_following")})
    else:
        items.append({
            "label": ts.ctxt("登录后查看关注的直播", color="yellow"),
            "path": bili.url_for("login_qrcode"),
        })
    return [c.temp_item(item) for item in items]


@bili.route("/live/recommend/<page>")
def live_recommend(page):
    res = c.getjson(
        "/xlive/web-interface/v1/webMain/getMoreRecList",
        urlbase=LIVE_API,
        params={"platform": "web"},
        headers=LIVE_HEADERS,
    )
    if not isinstance(res, dict):
        return []
    data = res.get("data") or {}
    rooms = data.get("recommend_room_list") or data.get("room_list") or []
    items = []
    for room in rooms:
        item = _live_room_item(room)
        if item:
            items.append(item)
    items.append(c.temp_item({
        "label": ts.ctxt("换一批直播", color="yellow"),
        "path": bili.url_for("live_recommend", page=int(page) + 1),
    }))
    return items


def _following_live_rooms():
    res = c.getjson(
        "/xlive/web-ucenter/v1/xfetter/GetWebList",
        urlbase=LIVE_API,
        params={"hit_ab": "false", "page": 1, "page_size": 30},
        headers=LIVE_HEADERS,
    )
    if not isinstance(res, dict):
        return []
    return (res.get("data") or {}).get("rooms") or []


@bili.route("/live/following/")
def live_following():
    if not _logged_in():
        return _login_required_items()
    items = []
    for room in _following_live_rooms():
        item = _live_room_item(room)
        if item:
            items.append(item)
    if not items:
        items.append(c.temp_item({"label": "当前没有关注的主播开播"}))
    return items


@bili.route("/live/play/<room_id>")
def live_play(room_id):
    playback = playback_settings(xbmcaddon.Addon())
    res = c.getjson(
        "/xlive/web-room/v2/index/getRoomPlayInfo",
        urlbase=LIVE_API,
        params={
            "room_id": room_id,
            "protocol": "0,1",
            "format": "0,1,2",
            "codec": "0,1,2",
            "qn": PI4_LIVE_MAX_QN,
            "platform": "web",
            "ptype": 8,
        },
        headers=LIVE_HEADERS,
    )
    if not isinstance(res, dict):
        return
    try:
        selected = select_live_stream(
            res.get("data") or {}, playback["codec_preference"]
        )
    except LivePlaybackError as exc:
        xbmcgui.Dialog().ok("直播播放失败", str(exc))
        return
    ts.log(
        "Live selected: room={} codec={} protocol={} format={} qn={} quality={}".format(
            room_id,
            selected["codec"],
            selected["protocol"],
            selected["format"],
            selected["qn"],
            selected.get("quality_desc") or "未知",
        )
    )
    http_headers = urllib.parse.urlencode({
        "User-Agent": LIVE_HEADERS["User-Agent"],
        "Referer": LIVE_HEADERS["Referer"],
    })
    write_live_context(c.temp_dir, room_id, selected["url"])
    bili.set_resolved_url("{}|{}".format(selected["url"], http_headers))


def _append_video(items, video):
    item = c.get_viditem(video)
    if item:
        items.append(item)


def _login_required_items():
    return [{
        "label": ts.ctxt("此页面需要登录，打开二维码登录", color="yellow"),
        "path": bili.url_for("login_qrcode"),
    }]


@bili.route("/history/<max_id>/<view_at>")
def history(max_id, view_at):
    if srt.get_uid() == "0":
        return _login_required_items()
    params = {"ps": 20, "type": "archive"}
    if str(max_id) != "0":
        params["max"] = max_id
        params["view_at"] = view_at
        params["business"] = "archive"
    res = c.getjson("/x/web-interface/history/cursor", params=ts.dict2url(params))
    if not isinstance(res, dict):
        return []
    data = res.get("data") or {}
    items = []
    for video in data.get("list") or []:
        if (video.get("history") or {}).get("business") == "archive":
            _append_video(items, video)
    cursor = data.get("cursor") or {}
    next_max = cursor.get("max")
    next_view = cursor.get("view_at")
    if next_max and data.get("list"):
        items.append(c.temp_item({
            "label": ts.ctxt("下一页", color="yellow"),
            "path": bili.url_for("history", max_id=next_max, view_at=next_view or 0),
        }))
    return items


@bili.route("/watch_later/")
def watch_later():
    if srt.get_uid() == "0":
        return _login_required_items()
    res = c.getjson("/x/v2/history/toview/web")
    if not isinstance(res, dict):
        return []
    items = []
    for video in (res.get("data") or {}).get("list") or []:
        _append_video(items, video)
    return items


@bili.route("/dynamic/<page>/<offset>")
def dynamic_feed(page, offset):
    if srt.get_uid() == "0":
        return _login_required_items()
    params = {"type": "video"}
    if offset != "0":
        params["offset"] = offset
    res = c.getjson(
        "/x/polymer/web-dynamic/v1/feed/all", params=ts.dict2url(params)
    )
    if not isinstance(res, dict):
        return []
    data = res.get("data") or {}
    items = []
    # The official dynamic experience exposes followed creators who are live
    # at the top of the feed. Keep these as native Kodi-playable items rather
    # than making the user leave dynamics and find the live section.
    if str(page) == "1" and str(offset) == "0":
        for room in _following_live_rooms():
            item = _live_room_item(room)
            if item:
                item["label"] = ts.ctxt("直播中", color="red") + " · " + item["label"]
                items.append(item)
    for dynamic in data.get("items") or []:
        normalized = normalize_dynamic(dynamic)
        if not normalized:
            continue
        item = c.get_viditem(normalized["video"])
        if item:
            item["label"] = normalized["label"]
            items.append(item)
    next_offset = data.get("offset")
    if data.get("has_more") and next_offset:
        items.append(c.temp_item({
            "label": ts.ctxt("下一页 · 当前第 {} 页".format(page), color="yellow"),
            "path": bili.url_for(
                "dynamic_feed", page=int(page) + 1, offset=next_offset
            ),
        }))
    return items

########################
#  User/用户/Up主 路由
@bili.route("/user/<uid>/")
def user_page(uid):
    params = srt.getwbikey({
        "mid": uid
    })
    params = ts.dict2url(params)
    
    # 添加两项空值以过鉴权
    cooks = srt.get_cooks()
    cooks["a"] = ""
    cooks["bing"] = ""
    res = c.getjson("/x/space/wbi/acc/info", params=params, cookies=cooks)
    if not isinstance(res, dict): return
    
    # Metadata
    i = res["data"]
    label = ts.ctxt("[Metadata] ", color="yellow")
    plot = ""
    ufi = ts.getSet("other.userfanart", int) # 0 = default 1 = userHeadimage 2 = userAvatar
    ufiurl = c.get_image("bg")
    
    # Card requests 获取粉丝等数据
    card = c.getjson("/x/web-interface/card", params=ts.dict2url({"mid": uid, "photo": True}))
    
    plot += f"UID: {i['mid']}\n"
    if i["sex"] != "保密":
        plot += f"{i['sex']}性 | "
    plot += f"Lv{i['level']}"
    if i["is_senior_member"] == 1:
        plot += " (硬核)"
    plot += " | "
    if isinstance(card, dict):
        cd = card["data"]
        card = card["data"]["card"]
        plot += f"{cd['archive_count']} 稿件 | "
        plot += f"{card['fans']} 粉丝 | "
        plot += f"{card['attention']} 关注 | "
        plot += f"{cd['like_num']} 点赞"
        if ufi == 1:
            ufiurl = cd["space"]["l_img"]
    plot += "\n"
    
    if ufi == 2:
        ufiurl = i["face"]
    
    # 主播被封了。
    if i["silence"] == 1:
        plot += ts.ctxt("主播老实了被封了。", color="red") + "\n"
    if i["is_followed"] == True:
        label += ts.ctxt("[已关注] ", color="red")
    if i["official"]["role"] != 0:
        plot += f"{i['official']['title']}\n"
    plot += f"\n{i['sign']}"
    
    label += f"{i['name']}"
    items = []
    # Metadata
    items.append({
       "label": label,
       "icon": i["face"],
       "fanart": ufiurl,
       "path": bili.url_for("passfunc"),
       "info": {
           "plot": plot
       }
    })
    # OtherPath
    items.append({"label": "用户投稿", "fanart": ufiurl, "path": bili.url_for("user_upload", uid=i["mid"], page=1)})
    items.append({"label": "用户收藏夹", "fanart": ufiurl, "path": bili.url_for("user_fav", uid=i["mid"])})
    items.append({"label": "用户关注列表", "fanart": ufiurl, "path": bili.url_for("user_sub", uid=i["mid"], page=1)})
    
    return items
    

# 关注列表
@bili.route("/user_sub/<uid>/<page>/")
def user_sub(uid, page):
    ps = ts.getSet("ps.subs", int)
    params = ts.dict2url({
        "vmid": uid,
        "pn": int(page),
        "ps": ts.getSet("ps.subs", int)
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
            "path": bili.url_for("user_page", uid=x["mid"]),
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
        "pn": page,
        "ps": ts.getSet("ps.upvideos", int)
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
    if not isinstance(res, dict): return
    if res["data"] == None:
        xbmcgui.Dialog().ok("ee", "此用户不公开/没有收藏夹")
        return
    
    items = []
    for x in res["data"]["list"]:
        # No Details
        if ts.getSet("detail.fav", bool) != True:
            items.append({
               "label": x["title"],
               "path": bili.url_for("fav_con", mlid=x["id"], page=1),
               "info": {
                 "plot": f"已收藏 {x['media_count']} 个视频"
               }
            })
            continue
        
        # Details More
        idx = x["id"]
        params=ts.dict2url({"media_id": int(idx)})
        info = c.getjson("/x/v3/fav/folder/info", params=params)
        if not isinstance(info, dict): return
        
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
@bili.route("/fav_content/<mlid>/<page>/")
def fav_con(mlid, page):
    page = int(page)
    params = ts.dict2url({
        "media_id": int(mlid),
        "order": "mtime",
        "ps": 15,
        "pn": page
    })
    res = c.getjson("/x/v3/fav/resource/list", params=params)
    if not isinstance(res, dict):
        return []
    
    items = []
    res = res.get("data") or {}
    next_page = bool(res.get("has_more"))
    
    for x in res.get("medias") or []:
        if not isinstance(x, dict) or x.get("type") != 2:
            continue
        # Deleted/private favourites carry a non-zero attr. get_viditem()
        # deliberately returns None for those entries, so use the guarded
        # append helper instead of handing None to xbmcswift2 and aborting the
        # whole directory page.
        _append_video(items, x)
    
    # 下一页逻辑
    if next_page:
        items.append(c.temp_item({
            "label": ts.ctxt("下一页", color="yellow"),
            "path": bili.url_for("fav_con", mlid=int(mlid), page=page+1)
        }))
    
    return items

########################
# 搜索 Search

def search_type(d, kw, typ):
    items = []
    resu = d.get("result") or []
    # video
    if typ == "video":
        for x in resu:
            _append_video(items, x)
    
    if typ == "media_bangumi":
        for nb in resu:
            label = ""
            
            plot = nb.get("desc") or ""
            if nb.get("type") == "media_bangumi":
                label = ts.ctxt("[番剧] ", color="pink")

            label += c.clean_text(nb.get("title") or "番剧")
            items.append({
                "label": label,
                "icon": nb.get("cover") or "",
                "path": bili.url_for("season_detail", season_id=nb.get("season_id") or 0),
                "info": {"plot": plot},
            })
    
    if typ == "bili_user":
        for nu in resu:
            plot = ""
            plot += f"uid: {nu['mid']}\n"
            plot += f"{nu['fans']} 粉丝 | {nu['videos']} 投稿 | Lv{nu['level']}\n"
            plot += f"\n{nu['usign']}"
            
            label = ts.ctxt("[用户] ", color="yellow") + nu["uname"]
            items.append({"label": label, "icon": "https:"+nu["upic"], "path": bili.url_for("user_page", uid=nu["mid"]), "info": {"plot": plot}})
    
    return items

def search_global(d, kw, typ):
    items = []
    
    if d["page"] == 1 and typ == "all":
        items.append({"label": ts.ctxt("搜视频", color="pink"), "path": bili.url_for("search", keyword=kw, typ="video", page=1)})
        items.append({"label": ts.ctxt("搜用户", color="pink"), "path": bili.url_for("search", keyword=kw, typ="bili_user", page=1)})
        items.append({"label": ts.ctxt("搜番剧", color="pink"), "path": bili.url_for("search", keyword=kw, typ="media_bangumi", page=1)})
    
    result_groups = {
        group.get("result_type"): group.get("data") or []
        for group in (d.get("result") or [])
        if isinstance(group, dict)
    }
    bangumi = result_groups.get("media_bangumi", [])
    films = result_groups.get("media_ft", [])
    users = result_groups.get("bili_user", [])
    videos = result_groups.get("video", [])
    
    # bangumi
    if bangumi:
        for nb in bangumi:
            label = ""
            
            plot = nb.get("desc") or ""
            if nb.get("type") == "media_bangumi":
                label = ts.ctxt("[番剧] ", color="pink")

            label += c.clean_text(nb.get("title") or "番剧")
            items.append({"label": label, "icon": nb.get("cover") or "", "path": bili.url_for("season_detail", season_id=nb.get("season_id") or 0), "info": {"plot": plot}})
    
    # media_ft /Movies
    if films:
        for nft in films:
            label = ""
            label += ts.ctxt("[" + (nft.get("season_type_name") or "影视") + "] ", color="yellow")
            label += c.clean_text(nft.get("title") or "影视")
            
            plot = ""
            plot += nft.get("desc") or ""
            items.append({"label": label, "icon": nft.get("cover") or "", "path": bili.url_for("season_detail", season_id=nft.get("season_id") or 0), "info": {"plot": plot}})
    
    # Users
    if users:
        nu = users[0]
        
        plot = ""
        plot += f"uid: {nu['mid']}\n"
        plot += f"{nu['fans']} 粉丝 | {nu['videos']} 投稿 | Lv{nu['level']}\n"
        plot += f"\n{nu['usign']}"
        
        label = ts.ctxt("[用户] ", color="yellow") + nu["uname"]
        items.append({"label": label, "icon": "https:"+nu["upic"], "path": bili.url_for("user_page", uid=nu["mid"]), "info": {"plot": plot}})
    
    # Videos
    for x in videos:
        if "live_status" in x and x["live_status"] == 1:
            continue
        _append_video(items, x)
    return items
    

@bili.route("/search/<keyword>/<typ>/<page>")
def search(keyword, typ, page):
    items = []
    
    # urlpath/params
    urlpath = "/x/web-interface/wbi/search/all/v2"
    params = {
        "keyword": keyword,
    }
    if typ != "all":
        params["search_type"] = typ
        params["page"] = page
        urlpath = "/x/web-interface/wbi/search/type"
    
    # Get
    header = {
       "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
       "Referer": "https://search.bilibili.com/all", # 搜索接口极其看重这个
       "Origin": "https://search.bilibili.com"
    }
    params = ts.dict2url(srt.getwbikey(params))
    res = c.getjson(urlpath, params=params, headers=header)
    if not isinstance(res, dict): return
    
    # 综合搜索
    if typ == "all":
        return search_global(res["data"], keyword, typ)
    else:
        return search_type(res["data"], keyword, typ)

@bili.route("/search_input/")
def search_input():
    # autoinput
    typ = "all"
    keyboard = xbmc.Keyboard('', '请输入搜索内容')
    keyboard.doModal()
    if (keyboard.isConfirmed()):
        keyword = keyboard.getText()
    else:
        return []
    
    if not keyword.strip():
        return []
    
    return search(keyword, "all", 1)

@bili.route("/search_ready/")
def search_ready():
    items = [
      {"label": ts.ctxt("新搜索", color="yellow"), "path": bili.url_for("search_input")},
      {"label": ts.ctxt("test_search", color="red"), "path": bili.url_for("search", keyword="籽岷", typ="all", page=1)},
      {"label": ts.ctxt("test_search", color="red"), "path": bili.url_for("search", keyword="少女终末旅行", typ="all", page=1)}
    ]
    return items


def _logged_in():
    return str(srt.get_uid()) != "0"


def _interaction_csrf():
    return srt.get_cookie_value("bili_jct")


def _favorite_folders(aid):
    if not _logged_in() or not aid:
        return []
    res = c.getjson(
        "/x/v3/fav/folder/created/list-all",
        params=ts.dict2url({
            "up_mid": srt.get_uid(),
            "type": 2,
            "rid": aid,
        }),
    )
    if not isinstance(res, dict):
        return []
    return (res.get("data") or {}).get("list") or []


def _interaction_items(bv, data, cover):
    """Build remote-friendly interaction entries for the video detail page."""
    if not _logged_in():
        return [{
            "label": ts.ctxt("互动功能需要登录", color="yellow"),
            "path": bili.url_for("login_qrcode"),
            "icon": c.get_image("icon"),
            "fanart": cover,
        }]

    aid = int(data.get("aid") or 0)
    liked = False
    coins = 0

    like_res = c.getjson(
        "/x/web-interface/archive/has/like",
        params=ts.dict2url({"bvid": bv}),
    )
    if isinstance(like_res, dict):
        liked = int(like_res.get("data") or 0) == 1

    coin_res = c.getjson(
        "/x/web-interface/archive/coins",
        params=ts.dict2url({"bvid": bv}),
    )
    if isinstance(coin_res, dict):
        coins = int((coin_res.get("data") or {}).get("multiply") or 0)

    folders = _favorite_folders(aid)
    favourite_count = sum(
        1 for folder in folders if int(folder.get("fav_state") or 0) == 1
    )

    like_label = "已点赞 · 点击取消" if liked else "点赞"
    favourite_label = (
        "收藏 · 已加入 {} 个收藏夹".format(favourite_count)
        if favourite_count
        else "收藏 · 选择收藏夹"
    )
    icon = c.get_image("icon")
    return [
        {
            "label": ts.ctxt(like_label, color="pink" if liked else "yellow"),
            "path": bili.url_for(
                "video_like", bv=bv, operation=2 if liked else 1
            ),
            "icon": icon,
            "fanart": cover,
            "info": {"plot": "点赞或取消点赞；操作完成后返回视频详情页。"},
        },
        {
            "label": ts.ctxt(
                "投币 · 已投 {}/2".format(coins), color="yellow"
            ),
            "path": bili.url_for("video_coin", bv=bv),
            "icon": icon,
            "fanart": cover,
            "info": {"plot": "选择投 1 枚或 2 枚硬币，提交前会再次确认。"},
        },
        {
            "label": ts.ctxt(favourite_label, color="yellow"),
            "path": bili.url_for("video_favorite", bv=bv),
            "icon": icon,
            "fanart": cover,
            "info": {"plot": "选择该视频需要加入或移出的收藏夹。"},
        },
        {
            "label": ts.ctxt("一键三连 · 点赞 + 投币 + 默认收藏", color="pink"),
            "path": bili.url_for("video_triple", bv=bv),
            "icon": icon,
            "fanart": cover,
            "info": {"plot": "通常会投入 2 枚硬币；提交前会再次确认。"},
        },
    ]


def _interaction_redirect(bv):
    return bili.redirect(bili.url_for("video_detail", bv=bv))


def _interaction_ready():
    if not _logged_in():
        xbmcgui.Dialog().ok("需要登录", "请先使用二维码登录 Bilibili 账号")
        return False
    if not _interaction_csrf():
        xbmcgui.Dialog().ok("操作失败", "登录 Cookie 缺少 bili_jct，请重新登录")
        return False
    return True


def _show_interaction_result(raw, success_message):
    if isinstance(raw, dict) and raw.get("code") == 0:
        xbmcgui.Dialog().notification(
            "Bilibili", success_message, c.get_image("icon"), 3000
        )
        return True
    if isinstance(raw, dict):
        code = raw.get("code", "未知错误")
        detail = raw.get("message") or "操作失败"
        if code in (-403, -352, -412):
            message = (
                "{}: {}\n\nB站拒绝了本次写操作。插件已刷新并保存网页会话 Cookie；"
                "请勿连续重试，稍后再试。若持续出现，请重新扫码登录。"
            ).format(code, detail)
        elif code == -101:
            message = "登录已失效，请重新扫码登录。"
        else:
            message = "{}: {}".format(code, detail)
    else:
        message = "请求未返回有效结果"
    xbmcgui.Dialog().ok("操作失败", message)
    return False


@bili.route("/video_action/like/<bv>/<operation>")
def video_like(bv, operation):
    if _interaction_ready():
        operation = 2 if str(operation) == "2" else 1
        raw = c.interaction_post("/x/web-interface/archive/like", {
            "bvid": bv,
            "like": operation,
            "csrf": _interaction_csrf(),
        }, bv)
        _show_interaction_result(raw, "已取消点赞" if operation == 2 else "点赞成功")
    return _interaction_redirect(bv)


@bili.route("/video_action/coin/<bv>")
def video_coin(bv):
    if not _interaction_ready():
        return _interaction_redirect(bv)
    selection = xbmcgui.Dialog().select("投币数量", ["投 1 枚", "投 2 枚"])
    if selection < 0:
        return _interaction_redirect(bv)
    multiply = selection + 1
    if not xbmcgui.Dialog().yesno(
        "确认投币", "确定为该视频投入 {} 枚硬币？投币不可撤销。".format(multiply)
    ):
        return _interaction_redirect(bv)
    raw = c.interaction_post("/x/web-interface/coin/add", {
        "bvid": bv,
        "multiply": multiply,
        "select_like": 0,
        "csrf": _interaction_csrf(),
    }, bv)
    _show_interaction_result(raw, "成功投入 {} 枚硬币".format(multiply))
    return _interaction_redirect(bv)


@bili.route("/video_action/favorite/<bv>")
def video_favorite(bv):
    if not _interaction_ready():
        return _interaction_redirect(bv)
    view = c.getjson("/x/web-interface/view", params=ts.dict2url({"bvid": bv}))
    aid = int(((view or {}).get("data") or {}).get("aid") or 0)
    folders = _favorite_folders(aid)
    if not aid or not folders:
        xbmcgui.Dialog().ok("收藏失败", "没有获取到可用收藏夹")
        return _interaction_redirect(bv)

    labels = [
        "{}（{}项）".format(
            folder.get("title") or "未命名收藏夹", folder.get("media_count") or 0
        )
        for folder in folders
    ]
    current = {
        index for index, folder in enumerate(folders)
        if int(folder.get("fav_state") or 0) == 1
    }
    selected = xbmcgui.Dialog().multiselect(
        "选择收藏夹", labels, preselect=sorted(current)
    )
    if selected is None:
        return _interaction_redirect(bv)
    selected = set(selected)
    add_ids = [str(folders[index]["id"]) for index in sorted(selected - current)]
    del_ids = [str(folders[index]["id"]) for index in sorted(current - selected)]
    if not add_ids and not del_ids:
        xbmcgui.Dialog().notification(
            "Bilibili", "收藏夹没有变化", c.get_image("icon"), 2500
        )
        return _interaction_redirect(bv)

    raw = c.interaction_post("/x/v3/fav/resource/deal", {
        "rid": aid,
        "type": 2,
        "add_media_ids": ",".join(add_ids),
        "del_media_ids": ",".join(del_ids),
        "platform": "web",
        "csrf": _interaction_csrf(),
    }, bv)
    _show_interaction_result(raw, "收藏夹已更新")
    return _interaction_redirect(bv)


@bili.route("/video_action/triple/<bv>")
def video_triple(bv):
    if not _interaction_ready():
        return _interaction_redirect(bv)
    if not xbmcgui.Dialog().yesno(
        "确认一键三连",
        "将点赞、投币并收藏到默认收藏夹。通常会投入 2 枚硬币，且投币不可撤销。是否继续？",
    ):
        return _interaction_redirect(bv)
    raw = c.interaction_post("/x/web-interface/archive/like/triple", {
        "bvid": bv,
        "csrf": _interaction_csrf(),
    }, bv)
    if isinstance(raw, dict) and raw.get("code") == 0:
        result = raw.get("data") or {}
        message = "三连完成：点赞{}，投币{}，收藏{}".format(
            "成功" if result.get("like") else "未变化",
            result.get("multiply") or ("成功" if result.get("coin") else "未变化"),
            "成功" if result.get("fav") else "未变化",
        )
        _show_interaction_result(raw, message)
    else:
        _show_interaction_result(raw, "一键三连完成")
    return _interaction_redirect(bv)


@bili.route("/video/<bv>")
def video_detail(bv):
    res = c.getjson("/x/web-interface/view", params=ts.dict2url({"bvid": bv}))
    if not isinstance(res, dict):
        return []
    data = res.get("data") or {}
    pages = data.get("pages") or []
    cover = data.get("pic") or ""
    items = []
    for page_index, page in enumerate(pages):
        part = page.get("part") or data.get("title") or "播放"
        if len(pages) > 1:
            part = "P{} · {}".format(page.get("page") or len(items) + 1, part)
        items.append({
            "label": ts.ctxt("▶ 立即播放 · ", color="yellow") + part,
            "path": bili.url_for("bvplay", bv=bv, cid=page.get("cid") or 0),
            "icon": page.get("first_frame") or cover,
            "fanart": cover,
            "is_playable": True,
            "info": {
                "mediatype": "video",
                "title": part,
                "plot": c.parse_plot(data),
                "duration": page.get("duration") or data.get("duration") or 0,
            },
        })
        if page_index == 0:
            items.extend(_interaction_items(bv, data, cover))

    if not pages:
        items.extend(_interaction_items(bv, data, cover))

    season = data.get("ugc_season") or {}
    seen = {(str(bv), str(page.get("cid"))) for page in pages}
    for section in season.get("sections") or []:
        for episode in section.get("episodes") or []:
            key = (str(episode.get("bvid")), str(episode.get("cid")))
            if not episode.get("bvid") or key in seen:
                continue
            seen.add(key)
            items.append({
                "label": ts.ctxt("合集 · ", color="pink") + (episode.get("title") or "视频"),
                "path": bili.url_for(
                    "bvplay", bv=episode.get("bvid"), cid=episode.get("cid") or 0
                ),
                "icon": (episode.get("arc") or {}).get("pic") or cover,
                "is_playable": True,
            })

    owner = data.get("owner") or {}
    if owner.get("mid"):
        items.append({
            "label": "UP主页 · {}".format(owner.get("name") or owner["mid"]),
            "path": bili.url_for("user_page", uid=owner["mid"]),
            "icon": owner.get("face") or "",
        })
    items.append({
        "label": "相关推荐",
        "path": bili.url_for("related_videos", bv=bv),
        "fanart": cover,
    })
    return items


@bili.route("/related/<bv>")
def related_videos(bv):
    res = c.getjson(
        "/x/web-interface/archive/related", params=ts.dict2url({"bvid": bv})
    )
    if not isinstance(res, dict):
        return []
    items = []
    for video in res.get("data") or []:
        _append_video(items, video)
    return items


@bili.route("/season/<season_id>")
def season_detail(season_id):
    res = c.getjson(
        "/pgc/view/web/season", params=ts.dict2url({"season_id": season_id})
    )
    if not isinstance(res, dict):
        return []
    data = res.get("result") or res.get("data") or {}
    items = []
    for episode in data.get("episodes") or []:
        title = episode.get("long_title") or episode.get("title") or "剧集"
        badge = episode.get("badge")
        if badge:
            title = "[{}] {}".format(badge, title)
        items.append({
            "label": title,
            "path": bili.url_for(
                "epplay",
                ep_id=episode.get("id") or episode.get("ep_id") or 0,
                bv=episode.get("bvid") or "0",
                cid=episode.get("cid") or 0,
            ),
            "icon": episode.get("cover") or data.get("cover") or "",
            "fanart": data.get("cover") or "",
            "is_playable": True,
            "info": {
                "mediatype": "episode",
                "title": title,
                "duration": int(episode.get("duration") or 0) // 1000,
            },
        })
    return items


########################
# PlayVideo 路由
@bili.route("/bvplay/<bv>/<cid>")
def bvplay(bv, cid):
    return _resolve_playback(bv, cid)


@bili.route("/epplay/<ep_id>/<bv>/<cid>")
def epplay(ep_id, bv, cid):
    return _resolve_playback(bv, cid, ep_id=ep_id)


def _resolve_playback(bv, cid, ep_id=None):
    if cid == 0 or cid == "0":
        res = c.getjson("/x/web-interface/view", params=ts.dict2url({"bvid": bv}))
        if not isinstance(res, dict) or not res.get("data", {}).get("pages"):
            xbmcgui.Dialog().ok("Error", "无法获取视频 cid")
            return
        cid = res["data"]['pages'][0]['cid']

    playback = playback_settings(xbmcaddon.Addon())
    params = {
        'bvid': bv,
        'cid': cid,
        'qn': playback["request_qn"],
        'fnver': 0,
        'fnval': 4048,
        'fourk': 1,
    }
    endpoint = "/x/player/playurl"
    if ep_id is not None:
        endpoint = "/pgc/player/web/playurl"
        params["ep_id"] = ep_id
    res = c.getjson(endpoint, params=ts.dict2url(params))
    if not isinstance(res, dict):
        return

    resu = res.get("result") if ep_id is not None else res.get("data")
    if not isinstance(resu, dict):
        xbmcgui.Dialog().ok("播放失败", "playurl 未返回播放信息")
        return
    ts.log(
        "playurl quality={} accept_quality={} dash_video={} dash_audio={}".format(
            resu.get("quality"),
            resu.get("accept_quality"),
            len((resu.get("dash") or {}).get("video") or []),
            len((resu.get("dash") or {}).get("audio") or []),
        )
    )

    cookies = srt.get_cooks()
    danmaku_subtitle = None
    try:
        danmaku_subtitle = prepare_danmaku(
            cid, c.temp_dir, xbmcaddon.Addon(), cookies=cookies
        )
    except (DanmakuError, OSError, ValueError) as exc:
        ts.err("Danmaku disabled for this playback: {}".format(exc))

    official_subtitles = []
    try:
        official_subtitles = prepare_bilibili_subtitles(
            bv,
            cid,
            c.temp_dir,
            xbmcaddon.Addon(),
            cookies=cookies,
            danmaku_path=danmaku_subtitle,
            wbi_signer=srt.getwbikey,
        )
    except (BilibiliSubtitleError, OSError, ValueError) as exc:
        ts.err("Bilibili official subtitles unavailable: {}".format(exc))
    ts.log(
        "Subtitle tracks prepared: official={} danmaku={}".format(
            len(official_subtitles), bool(danmaku_subtitle)
        )
    )
    subtitles = ([danmaku_subtitle] if danmaku_subtitle else []) + official_subtitles
    subtitles = subtitles or None

    write_playback_context(c.temp_dir, bv, cid)

    if isinstance(resu.get("dash"), dict):
        try:
            c.rec_history(bv, cid)
            selected = play_dash(
                resu["dash"],
                temp_dir=c.temp_dir,
                cid=cid,
                quality=playback["quality"],
                codec_preference=playback["codec_preference"],
                allow_av1=playback["allow_av1"],
                quality_fallback=playback["quality_fallback"],
                auto_compatible=playback["auto_compatible"],
                cookies=cookies,
                plugin=bili,
                subtitles=subtitles,
            )
            video = selected["video"]
            ts.log(
                "DASH selected: qn={} range={} codec={} {}x{} fps={} bandwidth={}".format(
                    selected["quality"],
                    selected["dynamic_range"],
                    selected["codec"],
                    video.get("width"),
                    video.get("height"),
                    selected["fps"],
                    video.get("bandwidth"),
                )
            )
        except (DashPlaybackError, ManifestServerError, ValueError, OSError) as exc:
            ts.err("DASH playback failed: {}".format(exc))
            xbmcgui.Dialog().ok("DASH 播放失败", str(exc))
        return

    # Keep the original progressive URL as a compatibility fallback for old
    # or unusual videos that do not expose DASH at all.
    if resu.get("durl"):
        c.rec_history(bv, cid)
        item = ListItem(path=resu["durl"][0]["url"], offscreen=True)
        attach_subtitles(item.as_xbmc_listitem(), subtitles)
        bili.set_resolved_url(item)
        return

    xbmcgui.Dialog().ok("播放失败", "playurl 未返回 DASH 或 MP4 播放地址")
    
########################
# Login
@bili.route("/login_qrcode/")
def login_qrcode():
    return _login_qrcode_page()


@bili.route("/login_qrcode_refresh/<nonce>")
def login_qrcode_refresh(nonce):
    return _login_qrcode_page()


def _login_qrcode_page():
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
         "label": ts.ctxt("刷新二维码", color="yellow"),
         "path": bili.url_for("login_qrcode_refresh", nonce=int(time.time() * 1000)),
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
    if cooks == False:
        return []
    # 保存内容
    user = bili.get_storage("user")
    user["cookies"] = r.utils.dict_from_cookiejar(cooks)
    user["refkey"] = refkey
    user.sync() # Sync storage immediately
    # 弹弹窗显示
    xbmcgui.Dialog().ok("Good Work!", "登录成功, you did very well")
    ts.back()
    return []

@bili.route("/login_local/")
def login_local():
    sel = xbmcgui.Dialog().yesno("确定？", "将从 插件根目录/cookies.json 中获取cookies/refresh_key参数并尝试登录\n同时也可能会覆盖你原有的登录信息")
    if sel == True:
        resu = c.login_local()
        if resu == False:
            xbmcgui.Dialog().ok("Error", "此 Cookie 可能无效")
            return
        user = bili.get_storage("user")
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
    a = f"无人问津的客户端 ~ Bilikodi Reborn {version}\n"
    a += "重构的 Bilikodi 打赢复活赛，基于bilibili-api实现\n"
    a += "应该适用于 Kodi 19~22 所有版本\n"
    a += "搜索中文关键词请使用中文输入法或者自动补全插件"
    xbmcgui.Dialog().ok("帮助/说明", a)

if __name__ == "__main__":
    bili.run()
