# Raspberry Pi 4 / Kodi 21 验收步骤

验证插件浏览、Bilibili DASH、InputStream Adaptive、HEVC 选流、官方字幕合成 ASS、原生弹幕、
播放进度，以及 Kodi 已有的 Pi 4 硬件解码与 DRM/KMS 输出。不要修改 Kodi、
FFmpeg、DRM/KMS 或 mpv 配置。

## 1. 安装与基础浏览

1. 在 Kodi 中确认 `InputStream Adaptive` 已安装并启用。
2. 通过“从 zip 文件安装”安装 `plugin.video.bilikodiRe-1.4.3.zip` 或更新版本。
3. 重启一次 Kodi，使新增的本地 MPD service 启动。
4. 打开插件，依次确认首页推荐、入站必刷、搜索、历史、稍后再看、收藏夹、
   动态、视频详情、分P和相关推荐能打开。
5. 如需 1080P 以上画质，在插件设置中用二维码或 `cookies.json` 登录，再用
   “检测登录状态”确认成功。

## 2. DASH 播放功能

先将插件画质设为“最高”，选择一个确认提供 HDR 真彩 HEVC（最好同时提供
4K60）的 B站视频并开始播放。可使用 `BV1bW4y1F7Tz` 的第一分P作为接口样本；
视频画质与账号权限以后续实际返回为准。检查：

- 有画面和独立音频，音画同步；
- 暂停/继续正常；
- 左右快退、快进和长距离拖动正常；
- 返回键退出播放器后回到原插件页面；
- Kodi 原生播放器 OSD 和遥控器操作正常。
- 开启弹幕后，Kodi 日志出现 `CDVDSubtitlesLibass` 且弹幕可见；
- 选择一个在 B站网页端确有 CC/AI 字幕的视频，Kodi 字幕列表应出现弹幕轨道，
  以及以 B站 `lan_doc` 命名的官方字幕轨道；选择任一官方字幕后弹幕仍应显示；
- 在插件设置中调整“官方字幕字号”，重新播放后确认官方字幕大小随设置变化；
  关闭弹幕后官方字幕仍应保持可调字号，不应退化为固定的系统样式；
- 连续播放两个 `cid` 不同的视频，第二个视频不得显示第一个视频的字幕或弹幕；
- 对 B站网页端没有字幕的视频，插件只能保留弹幕轨道，不能出现其他视频的 CC/AI
  字幕；字幕身份校验或 WBI 签名失败时也必须如此；
- 开启播放历史后，日志出现 `playback progress ... result=True`。

播放期间通过 SSH 查看插件选择结果：

```sh
grep -E "MPD service|DASH selected|inputstream.adaptive" ~/.kodi/temp/kodi.log | tail -n 30
```

目标日志应包含类似：

```text
MPD service listening on 127.0.0.1:<随机端口>
Subtitle tracks prepared: official=1 danmaku=True
DASH selected: qn=125 range=hdr codec=hevc 3840x2160 fps=60.0 ...
```

`qn=125` 表示 B站 HDR 档，且插件只会接受明确标识为 HEVC Main10、最高约
60fps 的 HDR Representation。`codec=hevc` 表示没有选到 AV1。若视频或账号
没有 HDR 权限，选择 `qn=120 range=sdr` 属正常降级；超过 60fps 的 HDR 源也会
向下选择 Pi4 兼容档位。

## 3. Pi 4 HEVC 硬件解码

保持 4K HEVC 视频正在播放，在另一个 SSH 会话执行：

```sh
sudo -n fuser -v /dev/video19
```

应看到 `kodi.bin` 占用 `/dev/video19`。然后执行：

```sh
sudo -n /usr/local/sbin/kodi-drm-state
```

在视频 plane 中确认：

```text
allocated by = kodi.bin
size = 3840x2160
src-pos = 3840x2160
crtc-pos = 3840x2160
```

HDR Main10 的视频 plane 应为 `P030`，并显示 `ITU-R BT.2020 YCbCr`；普通 SDR
HEVC 通常为 `NV12`。在同一输出的 CRTC 状态中确认当前模式是
`3840x2160 @ 60Hz`，HDR 时 HDMI connector 还应显示 `BT2020_YCC` 和有效的
高位深输出。该辅助命令只读取 DRM state；不要改显示配置。

当前机器上的辅助脚本若提示 `/sys/kernel/debug/dri/1/state` 不存在，是因为脚本
硬编码到了 V3D 节点；实际显示节点是只读的 `/sys/kernel/debug/dri/0/state`。
不要因此修改 Kodi、DRM/KMS 配置或系统辅助脚本。

最后观察负载和播放稳定性：

```sh
top -p "$(pidof kodi.bin)"
```

连续播放至少 10 分钟，并做三次拖动。验收条件是无持续掉帧/卡顿、CPU 负载符合
硬解特征，且退出后仍能返回插件页面。

## 4. 常见失败定位

- 日志选择不到 `qn=125`：先确认画质设置为“最高”、视频确有 B站 HDR 档、账号
  已登录且有对应观看权限；显式选择“4K”会把上限保留在 `qn=120` SDR 档。
- 提示“本地 MPD 服务未启动”：重启 Kodi，并检查插件 service 的启动日志。
- `DASH selected` 是 `codec=avc`：HDR 已安全降级，且兼容档没有可选 HEVC；插件
  不会把 AVC 或 AV1 当作 `qn=125` HDR 交给 Pi4。
- `fuser` 看不到 `kodi.bin`：确认播放仍在进行且日志实际选择了 HEVC，再检查正确的
  video device；不要因此修改已验证正常的 Kodi/DRM 配置。
- `official=0`：先确认插件登录状态有效，并在 B站网页端确认当前分P确实提供字幕；
  官方字幕属于具体 `cid`，不同分P可能不同。

## 5. 直播画质与弹幕

进入一个正在直播的房间。插件会向 B站请求最高 `qn=20000`，再按 Pi4 能力选择：

- HEVC 优先，AV1 永不进入候选；
- 2K（`qn=15000`）和 4K（`qn=20000`）只有 HEVC 流才会选择；
- 若直播间只提供高分辨率 AVC，自动降级到最高 `qn=10000`；
- 实际最高画质仍取决于直播间当前推流和账号权限。

日志应出现类似：

```text
Live selected: room=... codec=hevc ... qn=10000 quality=原画
Live danmaku started: room=...
Live danmaku subtitles enabled: room=...
```

有新弹幕后，Kodi 的当前字幕应为 `live <房间号> a/b（外挂）`，日志可看到
`CDVDSubtitlesLibass`。直播弹幕复用普通弹幕的字号、透明度、显示区域、类型过滤
和防重叠轨道。退出播放器后应出现 `Live danmaku stopped`，且直播不能在后台继续。

若当前房间只有 `qn=10000`，这是源站没有提供兼容的 HEVC 2K/4K，并非插件把
画质固定在 1080P。应换到确实在推送高画质 HEVC 的直播间再次检查。

## 6. 点赞、投币、收藏与三连

连续观看几个视频后，从详情页执行一次点赞。互动请求会先访问对应官方视频页，
持久化 `buvid3`、`b_nut` 等会话 Cookie，再携带 `Origin`、视频 `Referer` 和双
CSRF 字段提交。投币和三连都只提交一次，不因超时或风控响应自动重试。

若仍提示账号异常，检查日志中的 `POST ... code=<值> message=<信息>`：

- `-403`、`-352`、`-412`：不要连续点击；稍后再试，持续出现时重新登录；
- `-101`：登录态已失效，需要重新登录；
- 读取视频状态正常但只有写请求失败，通常是 B站当前风控，而不是整个登录态失效。
