[app]

# 应用名称
title = A股分钟波动监控

# 包名
package.name = stockmonitor

# 包域名
package.domain = org.test

# 源码目录
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json

# 版本
version = 1.0.0

# 所需权限
requirements = python3,kivy,requests,pyjnius,android

# 应用图标 (可选，需要提供 icon.png)
# icon.filename = icon.png

# 横屏
orientation = portrait

# Android 特定配置
[app:android]

# 最低 SDK 版本
android.minapi = 21

# 目标 SDK 版本
android.api = 33

# NDK 版本
android.ndk = 25b

# 权限
android.permissions = INTERNET

# 允许备份
android.allow_backup = True

# 主题
android.theme = "@android:style/Theme.Translucent.NoTitleBar"

[buildozer]

# 日志级别 (0-2)
log_level = 2

# 显示警告
show_warnings = True

# 构建目录
build_dir = ./build

# 二进制目录
bin_dir = ./bin
