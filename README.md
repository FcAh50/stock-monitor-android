# A股分钟波动监控 - Android APP 打包指南

## 项目文件
```
stock_monitor_kivy/
├── main.py           # Kivy 主程序
├── buildozer.spec    # 打包配置
└── README.md         # 本说明文件
```

## 新增功能
- ✅ 持仓量列（可手动输入持仓股数）
- ✅ 持仓金额列（自动计算：持仓量 × 当前价）
- ✅ 修改持仓按钮
- ✅ 监控预警（分钟变幅 > 0.5% 发邮件）

---

## 方式一：WSL 打包（推荐）

### 1. 安装 WSL
```powershell
# 在 Windows PowerShell（管理员）中运行
wsl --install Ubuntu
```
安装后重启电脑，完成 Ubuntu 初始化。

### 2. 进入 WSL
```powershell
wsl
```

### 3. 安装依赖
```bash
sudo apt update
sudo apt install -y git zip unzip openjdk-17-jdk autoconf libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo5 cmake libffi-dev libssl-dev automake

# 安装 pip 和 buildozer
pip3 install --user buildozer
```

### 4. 复制项目到 WSL
```bash
# 在 WSL 中执行
cp -r /mnt/c/Users/L/.qclaw/workspace/stock_monitor_kivy ~/stock_monitor
cd ~/stock_monitor
```

### 5. 初始化并打包
```bash
# 首次运行会下载 Android SDK/NDK（较慢）
buildozer init  # 如果没有 buildozer.spec

# 打包 APK
buildozer android debug

# 打包 Release 版本（需要签名）
# buildozer android release
```

### 6. 获取 APK
打包完成后，APK 位于：
```
~/stock_monitor/bin/stockmonitor-1.0.0-armeabi-v7a-debug.apk
```

复制到 Windows：
```bash
cp bin/*.apk /mnt/c/Users/L/Desktop/
```

---

## 方式二：Docker 打包（更简单）

### 1. 安装 Docker Desktop
下载：https://www.docker.com/products/docker-desktop

### 2. 运行打包容器
```powershell
cd C:\Users\L\.qclaw\workspace\stock_monitor_kivy

docker run --rm -v "%cd%":/home/user/app kivy/buildozer android debug
```

### 3. 获取 APK
APK 会生成在当前目录的 `bin/` 文件夹中。

---

## 方式三：GitHub Actions 自动打包

创建 `.github/workflows/build.yml`：

```yaml
name: Build Android APK

on: [push]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Build APK
        uses: kivy/buildozer-action@master
        id: buildozer
        
      - name: Upload APK
        uses: actions/upload-artifact@v3
        with:
          name: stockmonitor-apk
          path: bin/*.apk
```

推送到 GitHub 后，在 Actions 页面下载编译好的 APK。

---

## Windows 本地测试

在打包前，可以先在 Windows 上测试 Kivy 界面：

```powershell
# 安装 Kivy
pip install kivy[base]

# 运行测试
cd C:\Users\L\.qclaw\workspace\stock_monitor_kivy
python main.py
```

---

## 安装到手机

1. 将 APK 传到手机（微信、数据线等）
2. 打开 APK 文件
3. 允许安装未知来源应用
4. 完成安装

---

## 常见问题

### Q: 打包报错 "SDK location not found"
A: 删除 build 目录重新打包：
```bash
rm -rf .buildozer build
buildozer android debug
```

### Q: 网络问题导致下载慢
A: 配置国内镜像或使用代理

### Q: APK 安装失败
A: 确保手机开启了"允许安装未知来源应用"
