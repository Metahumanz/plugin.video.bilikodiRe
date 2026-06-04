# 如何使用本地 cookies 快捷导入账号
1. 请使用你自己的方法获取账号 cookies 以及 refresh\_key，此处不提供详细方法 **（注意一定需要 cookies 和长期保存的 refresh\_key ，refresh\_key 如果不正确将可能导致部分功能无法正常使用！）**
2. 在插件根目录下创建一个 cookies.json 的文件，并按照下方文件格式要求完成配置
```json
{
  "cookies": {
     "buvid": "xxxxxx",
     "SESSDATA": "xxxxx",
     // 按照上方格式将你获得的 cookies 转换成该格式
  }
  "refkey": "xxxxxxxx" // 这里填写你的 refresh_key，一定要正确！
}
```
3. 启动 Kodi -> 设置 -> 插件 -> 找到 Bilikodi Reborn -> 插件设置，在登录选项选择 “导入 cookies.json 登录” 并点击是。如果检测到 cookies 可用会自动使用此账号登陆，并自动保存 cookies 和 refresh\_key