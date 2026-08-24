# Bilikodi Reborn · Kodi 21 / Raspberry Pi 4 增强版

![Bilikodi Reborn](icon.png)

这是一个面向 Kodi 的非官方 Bilibili 客户端。本分支基于
[`Toad114514/plugin.video.bilikodiRe`](https://github.com/Toad114514/plugin.video.bilikodiRe)，
重点补全 Kodi 21、Raspberry Pi 4、DASH、直播、弹幕和遥控器使用体验。

项目坚持使用 Kodi 原生播放链路：不调用 mpv，不预下载或合并音视频，不创建
自定义播放器窗口，也不修改 Kodi、FFmpeg、DRM/KMS 或系统硬解配置。

## 功能概览

### 视频播放

- Bilibili DASH 独立视频、音频轨交给 InputStream Adaptive 和 Kodi Player。
- Raspberry Pi 4 默认按 `HEVC > AVC > AV1` 选择编码，AV1 默认禁用。
- “最高”画质支持 B站 `qn=125` HDR，只接受 Pi 4 可解码的 HEVC Main10、约
  60fps 以内流；不可用时自动向下选择兼容画质。
- 支持 4K60、4K、1080P60、1080P、720P 等画质上限和安全降级。
- 播放进度可定时回传；暂停、拖动、快进/快退和退出均保持 Kodi 原生行为。

播放链路：

```text
BV/aid → cid → playurl API → dash.video[] / dash.audio[]
       → Pi 4 兼容选流 → 本地临时 MPD → InputStream Adaptive → Kodi Player
```

### 弹幕与直播

- 普通视频弹幕由 B站 XML 转换成 Kodi 原生 ASS 外挂字幕。
- 登录后自动获取视频可用的 B站 CC/AI 官方字幕；每条官方字幕都与当前视频的
  原生 ASS 弹幕合成一个可选轨道，菜单名称直接使用 B站返回的字幕名称。
- 弹幕和官方字幕按 `cid`、字幕轨道分别存放，不复用其他视频的本地字幕路径。
- 官方字幕先校验 `BVID/CID` 归属，再通过 WBI 签名播放器接口获取；不回退到会
  返回错误缓存轨道的旧字幕接口。
- 每次刷新字幕只清理当前 `cid` 的旧生成轨道，避免残留文件被播放器缓存复用。
- 直播弹幕通过 B站 WebSocket 实时接收并转换成轮换 ASS 字幕。
- 字号、透明度、显示区域、弹幕类型和跨类型防重叠轨道可配置；滚动弹幕按屏幕
  轨迹复用行，只要保持间距且不会追尾，同一行可同时显示多条。
- 直播最高请求 `qn=20000`；2K/4K 只选择 HEVC，遇到高分辨率 AVC 或 AV1 时
  自动降级到 Pi 4 安全画质。
- 直播弹幕连接支持心跳和重连，长时间播放不会因临时识别上下文过期而停止。

### 浏览与账户

- 首页推荐、入站必刷、搜索、历史、稍后再看、收藏夹、关注、投稿和视频动态。
- 动态首页可直接进入已关注且正在直播的主播房间。
- 视频详情页包含立即播放、分P、合集、UP 主、相关推荐、点赞、投币、收藏和
  一键三连。
- 收藏夹会跳过已删除、私密或失效稿件，不会因单条坏数据导致整页打不开。
- 互动写请求会刷新官方视频页会话并持久化必要 Cookie；投币和三连不会自动
  重试，避免重复提交。
- 支持二维码登录及二维码过期刷新。

### Kodi 与遥控器体验

- 可设置点击视频后直接播放或先进入详情页。
- 视频列表中的返回键进入上一级，全屏播放返回键执行 Kodi 原生停止。
- 返回 Kodi 主页时可停止正在播放的视频，避免后台继续播放。
- 提供用户级 Estuary 派生皮肤安装工具，可在 Kodi 主页增加“哔哩哔哩”入口，
  不覆盖系统皮肤。

## 环境要求

- Kodi 21；当前硬件重点验证 Raspberry Pi 4B。
- 已安装并启用 `inputstream.adaptive` 21.x。
- Python 3 Kodi 插件环境及 `requests`、`xbmcswift2`、`pyqrcode` 依赖。
- 1080P 以上、4K 或 HDR 能否获得取决于账号权限和视频源。

## 安装

1. 将仓库内容打包为目录名为 `plugin.video.bilikodiRe` 的 Kodi 插件 zip，或复制到
   Kodi 用户插件目录。
2. 在 Kodi 中确认 InputStream Adaptive 已安装并启用。
3. 安装/更新插件后重启一次 Kodi，使本地 MPD 与播放进度 service 启动。
4. 打开插件设置，通过二维码登录并执行“检测登录状态”。
5. Raspberry Pi 4 建议保持默认的 HEVC 优先和 AV1 禁用设置。

完整的 DASH、硬解、DRM/KMS、直播和互动验收步骤见
[TESTING_PI4.md](TESTING_PI4.md)。

## 文档导航

- [架构说明](docs/ARCHITECTURE.md)：播放链、模块边界、字幕/弹幕和 service 生命周期。
- [工程经验与故障记录](docs/ENGINEERING_NOTES.md)：WBI 字幕串台、Kodi 字幕模型、
  弹幕轨道、登录存储和 PuTTY 共享连接经验。
- [Raspberry Pi 4 / Kodi 21 验收步骤](TESTING_PI4.md)：功能、硬解、直播和互动验证。
- [自动化协作规则](AGENTS.md)：仓库边界、安全、测试和部署要求。

## 设置说明

| 分类 | 主要选项 | 建议值 |
| --- | --- | --- |
| 画质 | 最高/4K/1080P60/1080P/720P | 有权限时使用“最高” |
| 编码 | HEVC/AVC | Pi 4 使用 HEVC |
| AV1 | 是否允许 | Pi 4 关闭 |
| 官方字幕 | 自动获取、首选语言 | 开启，简体中文优先 |
| 弹幕 | 字号、透明度、区域、类型、防重叠 | 按电视观看距离调整 |
| 导航 | 列表返回、全屏返回、回主页停止 | 遥控器环境建议开启 |
| 视频点击 | 详情页/直接播放 | 任选，所有视频列表统一生效 |

## 开发与测试

项目的播放代码位于：

```text
resources/lib/playback/
├── stream_selector.py   # DASH 画质与编码选择
├── dash.py              # MPD 与 Kodi resolved URL
├── manifest_server.py   # 本地临时 MPD 服务
├── subtitles.py         # B站官方字幕 JSON → SRT / 弹幕合成 ASS
├── danmaku.py           # 普通视频 ASS 弹幕
├── live.py              # 直播选流
├── live_danmaku.py      # 直播 WebSocket 与轮换 ASS
├── progress.py          # 播放上下文与进度
└── settings.py          # 播放设置映射
```

运行回归测试：

```powershell
python -m unittest discover -s tests -v
python -m compileall -q addon.py service.py core resources tests
```

提交问题时请删除日志中的 Cookie、令牌、局域网地址、用户名和本地绝对路径。仓库
默认忽略 `cookies.json`、日志、构建包、缓存和测试产物。

## PuTTY 共享连接：免重复认证的远程开发

PuTTY 可以让 `plink` 和 `pscp` 复用一条已经人工认证的 SSH upstream。它不是把
密码写进脚本，而是让后续批处理连接共享现有会话，适合频繁上传插件和读取 Kodi
日志。

1. 在 PuTTY 保存一个会话，并在 `Connection > SSH > Sharing` 中允许连接共享。
2. 用 PuTTY 正常打开该会话并人工完成认证，保持这个 upstream 窗口在线。
3. 脚本先用 `-shareexists` 检查共享连接，失败时立即停止。
4. 后续命令统一使用 `-batch -load`；不要使用 `-pw`、密码文件或脚本内密码。

脱敏的 PowerShell 示例：

```powershell
$plink = Join-Path $env:ProgramFiles 'PuTTY\plink.exe'
$pscp  = Join-Path $env:ProgramFiles 'PuTTY\pscp.exe'
$session = '<saved-session>'

& $plink -shareexists -load $session
if ($LASTEXITCODE -ne 0) {
    throw 'SSH shared upstream is not available.'
}

& $plink -batch -load $session 'tail -n 200 ~/.kodi/temp/kodi.log'
& $pscp -batch -load $session '<local-file>' '<host>:/home/<user>/<target>'
```

示例只使用占位符。不要把真实主机、用户名、Cookie、密码、私钥或会话令牌提交到
公开仓库。

## 已知限制

- 最高画质受登录状态、账号权限、地区和源站实际 Representation 限制。
- 直播间只有实际提供兼容 HEVC 2K/4K 时才能升档；高分辨率 AVC 会安全降级。
- 高级脚本弹幕不转换。
- B站风控响应可能要求稍后重试或重新登录；插件不会自动重试不可逆互动操作。
- HDR 亮度映射由 Kodi、显示链路和电视共同决定，插件不会修改系统 HDR 配置。

## 鸣谢

- [Toad114514/plugin.video.bilikodiRe](https://github.com/Toad114514/plugin.video.bilikodiRe)
- [chen310/plugin.video.bili](https://github.com/chen310/plugin.video.bili)
- [bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect)

## 声明与许可

本项目是非官方第三方客户端，仅供学习与个人使用，与哔哩哔哩官方无关，也未获得
官方授权。请遵守相关服务条款并自行承担账号和网络风险。

项目沿用上游的 [MIT License](LICENSE)。
