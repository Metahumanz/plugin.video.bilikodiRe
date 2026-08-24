# AGENTS.md

本文件适用于整个仓库。除非用户明确要求，否则后续自动化修改必须遵守以下规则。

## 项目边界

- 本项目是 Kodi 的非官方 Bilibili 视频插件，硬件重点是 Raspberry Pi 4B + Kodi 21。
- 始终复用 Kodi Player、InputStream Adaptive、FFmpeg 和 DRM/KMS 既有播放链。
- 不引入 mpv，不下载或合并音视频，不创建自定义播放器窗口。
- 不修改已经验证正常的系统 Kodi、FFmpeg、DRM/KMS、硬解或 HDMI 配置。
- Raspberry Pi 4 选流保持 HEVC 优先、AV1 默认禁用；HDR 只接受明确兼容的 HEVC Main10。

## 代码组织

- 播放相关实现放在 `resources/lib/playback/`，不要把新播放逻辑继续堆入 `addon.py`。
- `addon.py` 负责路由和组装；`service.py` 负责需要跨插件调用持续存在的生命周期逻辑。
- 浏览器、API 返回和路由参数都视为不可信输入；固定接口、严格校验，不执行任意 shell。
- B站官方字幕必须校验 BVID/CID 归属并使用 WBI 签名接口，不得回退到已知会返回错误轨道的旧接口。
- Kodi 同一时刻只能选择一个字幕流。需要同时显示字幕和弹幕时，继续生成“官方字幕 + 当前视频弹幕”的复合 ASS 轨道。

## 安全与脱敏

- 不提交 Cookie、token、验证码、密码、私钥、ADB key、Android ID、真实局域网地址、设备序列号或配对码。
- 不在日志中输出字幕签名 URL、Cookie 值或其他长期身份标识。
- `cookies.json`、日志、构建包、缓存、测试产物以及 `raspberry-tv-connection/` 必须保持忽略。
- 树莓派连接规范只存在于本机 `raspberry-tv-connection/`；远端操作前必须先按其中规则检查 PuTTY 共享 upstream。连接不可用时停止，不回退到其他认证方式。
- 仅使用本地连接规范明确列出的 sudo 白名单；普通插件文件操作不使用 sudo。

## 验证要求

修改 Python、XML 或播放逻辑后至少运行：

```powershell
python -m unittest discover -s tests -v
python -m compileall -q addon.py service.py core resources tests
```

涉及树莓派部署时还应：

1. 校验安装包 SHA-256；
2. 部署前创建可回滚备份；
3. 重启 Kodi 后检查 service、插件日志和实际生成文件；
4. 确认临时诊断路由、真实地址和敏感文件未进入 ZIP 或 Git diff。

## Git 与上游

- 保留上游作者、MIT License 和 fork 关系说明。
- 不覆盖用户已有改动，不使用 `git reset --hard` 清理工作区。
- 除非用户明确要求，不强推、不改写公共历史、不自动创建 release。
- 提交前运行 `git diff --check` 和脱敏扫描；只提交源代码、测试和正式文档。
