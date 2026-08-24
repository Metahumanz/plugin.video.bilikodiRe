# 工程经验与故障记录

这份文档记录已经通过日志、接口对比或树莓派现场验证的结论，避免后续重复踩坑。

## 1. 不要信任旧播放器字幕接口

在有效登录会话下，旧 `/x/player/v2` 曾对完全相同的 BVID/CID 返回不同视频的
轨道 ID 和正文，表现为“字幕串到莫名其妙的视频”。本地文件名和 ASS 合并本身
没有出错，错误数据在元数据请求阶段就已经产生。

稳定方案是：

1. 用 view API 确认 CID 确实属于当前 BVID；
2. 调用 `/x/player/wbi/v2` 并携带 WBI 签名；
3. 签名或归属校验失败时不加载官方字幕，绝不回退旧接口；
4. 当前 CID 每次刷新前清理旧生成轨道，避免播放器路径缓存继续引用坏文件。

## 2. Kodi 不能同时选择两条字幕流

独立官方字幕和独立弹幕都能加入 Kodi 字幕列表，但用户切换官方字幕后，弹幕轨道
自然会被关闭。这不是 InputStream Adaptive 的音视频限制，而是 Kodi 字幕选择模型。

当前折中是为每条官方字幕生成一份复合 ASS：保留原生 libass 弹幕样式，再追加
底部官方字幕样式。这样切换语言时仍有弹幕，同时保留一个“仅弹幕”选项。

## 3. 弹幕行不能按生命周期独占

只用“该行是否已有活跃弹幕”判断，会造成屏幕只有少量弹幕，每行同一时刻最多
一条。正确做法需要同时检查：

- 新弹幕进入屏幕时与前一条的尾部间距；
- 两条速度不同时，剩余时间内是否会追尾；
- 顶部、底部和滚动弹幕是否共享同一条物理轨道。

允许安全复用轨道后，密度接近网页端，同时仍可丢弃确实无法安置的溢出弹幕。

## 4. xbmcswift2 存储不是裸字典

`.storage/user` 的原始 pickle 会把值保存为类似 `(value, timestamp)` 的 tuple。
直接把 `storage['cookies']` 当普通字典检查，会误判为 Cookie 为空。应通过
`Plugin.get_storage()` 读取，或在离线诊断时先识别并解包 tuple。

一次 Kodi service 重启会清空进程内存；重启后仍能访问账号 API，说明登录态确实
从磁盘恢复，不能据此推断“因为机器没断电所以 Cookie 一直在内存”。包含会话的
存储文件应限制为当前用户可读写。

## 5. PuTTY 共享连接适合频繁部署

开发机先维持一条人工认证的 PuTTY upstream，后续 `plink`/`pscp` 使用 saved
session 共享连接，可以避免把密码放进命令行、脚本或环境变量。通用流程是：

```powershell
& '<plink>' -shareexists -load '<saved-session>'
& '<plink>' -batch -load '<saved-session>' '<remote-command>'
& '<pscp>' -batch -load '<saved-session>' '<local-file>' '<host>:<remote-path>'
```

注意事项：

- 每组远端操作前先执行 `-shareexists`，失败立即停止；
- `pscp` 的目标语法在不同版本上有差异，应先用无敏感文件验证；
- PowerShell 不使用反斜杠转义 `$()`，复杂远端 Python/JSON 可先本地 base64 编码；
- 部署前备份，上传后比较 SHA-256，安装后检查 service 和日志；
- 真实主机、用户、saved session、sudo 白名单和家庭网络信息只保存在本机忽略目录。

## 6. 验证顺序比“看起来能播”更可靠

一次完整播放修复至少核对：

1. API 返回的画质、编码、字幕轨道数；
2. 生成的 MPD/ASS 是否属于当前 CID；
3. Kodi 是否加载 InputStream Adaptive 与 libass；
4. 远端硬解设备和 DRM plane 是否由 Kodi 占用；
5. 退出播放器后 service、进度和后台播放状态是否正确；
6. ZIP 与 Git diff 中是否混入日志、Cookie、本机地址或临时诊断代码。

优先保留可复现的轨道 ID、条目数量、哈希和布尔状态；避免在日志中记录完整字幕
签名 URL、Cookie 值或账号标识。
