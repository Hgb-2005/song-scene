> 本文保留V7本地交付时的说明；GitHub发布信息与下载入口请以根目录README.md为准。

# 开发与维护

日常运行：Python3.10+。媒体功能：FFmpeg + FFprobe。前端契约测试：Node22+。没有pip或npm运行时依赖。

## 本地检查

```text
python tools/check.py
python -m unittest discover -s tests -v
node --test tests/timeline.test.mjs tests/composition.test.mjs
```

测试使用隔离临时目录，不能指向用户真实data目录。没有FFmpeg时集成测试会跳过媒体部分；准备交付时应在安装FFmpeg的环境完整通过，不应把跳过称作通过。

新增功能必须保留三项轻量首页；复杂制作选项放在需求详情。涉及保存、恢复或合成的变更应补充真实契约测试。存储更新遵循revision冲突检查，跨记录关联用同一事务完成。外部输入不得进入shell命令；媒体工具通过参数数组启动。

打包前确认data、测试产物、密钥、临时文件和用户新增媒体不会进入源码包：

```text
python tools/package.py --kind all --output ../release
```

打包工具拒绝覆盖已有同名ZIP，避免误覆盖旧交付。运行数据与程序分开；更新版本前建议通过界面导出完整备份。不要直接复制正在运行的SQLite WAL文件作为唯一备份。

仓库已按项目所有者授权公开发布，V7 历史版本保留。新的私人工作数据始终排除在提交和打包之外。

## Windows 桌面打包

使用官方 Python 3.14.10 创建干净 venv，安装 PyInstaller 6.22.3；准备官方 Inno Setup 7.1.1 编译器。不要把个人 Anaconda 环境直接打进发行版。

```text
python -m venv ../build-env
../build-env/Scripts/python -m pip install pyinstaller==6.22.3
../build-env/Scripts/python tools/build_windows.py --output ../release-v8 --work-dir ../build-v8 --iscc C:/path/to/InnoSetup/ISCC.exe
```

构建目录和输出目录必须位于源码目录外。脚本打包轻量样片、界面、Python/Tk 依赖和授权文本，生成安装版和免安装版；不包含用户 data，也不包含 FFmpeg 二进制。Python 构建版本变化时，应同步第三方版本说明与 Tcl/Tk/OpenSSL 许可文件。安装器保持 AppId 和独立数据目录不变，禁止添加删除用户数据的卸载规则。

预览规则在 server/composition.py 与界面/composition.mjs 两端对应，修改取景、字幕或时间约定时，应同时检查真实 FFmpeg 输出与浏览器预览。桌面代码没有控制台，错误应进入日志并向页面返回明确提示。
