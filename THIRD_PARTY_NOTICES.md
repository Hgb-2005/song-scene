# 代码、工具与素材说明

本项目基于所有者提供的 V5/V6 项目升级。MoneyPrinterTurbo、Remotion 仅作为设计参考，没有直接复制其代码或捆绑其运行时。

## V8 桌面运行环境

- Windows 桌面版包含官方 CPython 3.14.10 运行库，以及 Tcl/Tk 9.0.4、OpenSSL 3.5.9 等依赖。Python 完整授权文本随桌面包 PYTHON_LICENSE.txt 提供，其他授权原文位于 licenses/。
- 桌面封装使用 [PyInstaller 6.22.3](https://pyinstaller.org/)。其 GPL 许可证包含允许分发生成程序的 bootloader exception；原文见 desktop/licenses/PyInstaller-COPYING.txt。
- 安装器由 [Inno Setup 7.1.1](https://jrsoftware.org/inno-setup) 构建，当前为个人、非商业用途交付。以后用于商业业务时，请核对其当时适用的商业许可条件。
- 原始许可证来源：[Tcl](https://github.com/tcltk/tcl/blob/core-9-0-4/license.terms)、[Tk](https://github.com/tcltk/tk/blob/core-9-0-4/license.terms)、[OpenSSL](https://github.com/openssl/openssl/blob/openssl-3.5.9/LICENSE.txt)。打包使用相符版本的官方运行库。

## 视频引擎

本仓库及发布包不捆绑 FFmpeg/FFprobe 二进制。源码版调用本机程序。桌面版先寻找兼容的本机工具；缺少时，首次启动直接从 [Gyan 官方构建站](https://www.gyan.dev/ffmpeg/builds/) 下载未经修改的 9.0.2 essentials ZIP，按代码中固定的 SHA-256 校验后解压到用户缓存，不上传作品。

该上游构建为 GPLv3，原始许可说明保留在下载的引擎目录。供应方、源代码链接与构建信息见 [上游 9.0.2 发布页](https://github.com/GyanD/codexffmpeg/releases/tag/9.0.2)。不要把缓存里的第三方二进制直接加入本项目交付包；如另行分发，应单独履行对应许可义务。可替换为其他同时支持 libx264、libass 的 FFmpeg 构建。

## 样片与项目许可

项目所有者已选择公开发布最新源码、文档、图片、视频样片与交付包。原素材来源记录保留在“素材署名”目录与歌曲数据中。公开可访问不代表这些媒体改变了原有使用条件，也不等于取得商业使用授权。

当前仓库未指定统一对外开源许可证，没有替所有者签署或授予第三方素材的新授权。复用、修改或分发前请确认对应代码和媒体的适用条件；程序代码、歌曲音轨、视频和图片分别看待。
