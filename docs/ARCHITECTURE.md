# 架构说明

## 目标与边界

Bilikodi Reborn 在 Kodi 插件进程中完成 Bilibili 浏览、选流和播放参数准备，最终
仍由 Kodi 原生播放器负责解码、同步、字幕渲染和遥控器交互。插件不会预下载或
合并 DASH 音视频，也不会接管系统显示链。

## 点播播放链

```text
插件路由（BVID / CID）
  ├─ playurl API ──> DASH video[] / audio[]
  │                   └─ stream_selector.py
  │                       └─ Pi 4 兼容画质与编码
  ├─ danmaku.py ──> 当前 CID 的原生 ASS 弹幕
  └─ subtitles.py
      ├─ 校验 BVID / CID 归属
      ├─ WBI 签名播放器接口
      └─ 每条官方字幕 + 当前弹幕的复合 ASS
             ↓
dash.py 生成临时 MPD
             ↓
manifest_server.py 提供 localhost MPD
             ↓
InputStream Adaptive + Kodi Player
```

视频和音频 Representation 始终独立交给 Kodi。临时 MPD 只描述远端流、初始化段
和索引范围，不保存媒体内容。

## 选流策略

`stream_selector.py` 先应用用户画质上限，再根据 Raspberry Pi 4 能力筛选：

- 默认编码顺序为 HEVC、AVC；AV1 只有用户显式开启后才进入普通候选。
- 2K/4K 与 HDR 优先选择 HEVC；高分辨率 AVC 可按兼容规则向下降级。
- `qn=125` 只接受明确的 HEVC Main10 HDR，并限制在约 60fps 内。
- 目标档不存在时逐级下降，不把不兼容编码伪装成目标画质。

## 字幕与弹幕

Kodi 的字幕选择器一次只能激活一个字幕流，无法同时选择独立 CC 和独立弹幕。
因此点播提供以下轨道：

1. `Bilibili Danmaku`：仅当前 CID 弹幕；
2. 每条 B站官方字幕对应一个“官方字幕 + 当前弹幕”的复合 ASS；即使关闭弹幕，
   官方字幕也会单独生成 ASS，以便使用插件设置的字号（默认 42，范围 16–96）。

官方字幕获取有三道隔离：

- view API 证明 CID 属于当前 BVID；
- 只调用 WBI 签名的播放器元数据接口；
- 输出按 `cid/track-id` 分目录，每次刷新前只清理当前 CID 的旧官方轨道。

弹幕防重叠按实际轨迹判断。同一行只要满足入场间距且后发弹幕不会追上前一条，
即可同时容纳多条，而不是让每条弹幕独占整段生命周期。

## 直播

`live.py` 展开直播源并选择 Pi 4 兼容的 HLS/编码/画质。`live_danmaku.py` 维护
WebSocket、心跳和重连，把实时消息轮换写入原生 ASS 字幕。退出播放器后 service
停止直播弹幕会话，不创建额外播放窗口。

## 常驻 service

`service.py` 负责：

- localhost MPD 服务；
- 播放进度回传；
- 直播弹幕生命周期；
- Kodi 主页/返回行为和用户级 keymap 同步。

短生命周期的插件路由只负责生成当前播放上下文，service 通过临时上下文文件识别
属于本插件的播放，避免影响其他来源。

## 目录职责

| 路径 | 职责 |
| --- | --- |
| `addon.py` | 菜单、路由、播放组装、登录与互动入口 |
| `core/` | B站请求、Cookie、WBI 和通用工具 |
| `resources/lib/playback/` | DASH、选流、字幕、弹幕、直播和进度 |
| `service.py` | Kodi 常驻生命周期逻辑 |
| `resources/settings.xml` | 用户可配置项 |
| `tests/` | 不依赖真实账号的回归测试 |
