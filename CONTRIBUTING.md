> 本文保留V7本地交付时的说明；GitHub发布信息与下载入口请以根目录README.md为准。

# 开发与维护

日常运行：Python3.10+。媒体功能：FFmpeg + FFprobe。前端契约测试：Node22+。没有pip或npm运行时依赖。

## 本地检查

```text
python tools/check.py
python -m unittest discover -s tests -v
node --test tests/timeline.test.mjs
```

测试使用隔离临时目录，不能指向用户真实data目录。没有FFmpeg时集成测试会跳过媒体部分；准备交付时应在安装FFmpeg的环境完整通过，不应把跳过称作通过。

新增功能必须保留三项轻量首页；复杂制作选项放在需求详情。涉及保存、恢复或合成的变更应补充真实契约测试。存储更新遵循revision冲突检查，跨记录关联用同一事务完成。外部输入不得进入shell命令；媒体工具通过参数数组启动。

打包前确认data、测试产物、密钥、临时文件和用户新增媒体不会进入源码包：

```text
python tools/package.py --kind all --output ../release
```

打包工具拒绝覆盖已有同名ZIP，避免误覆盖旧交付。运行数据与程序分开；更新版本前建议通过界面导出完整备份。不要直接复制正在运行的SQLite WAL文件作为唯一备份。

本目录已附GitHub Actions检查配置，但未替用户创建远程仓库、选择公开范围或发布版本。公开发布前请由项目所有者确定代码许可证与示例素材发布范围。
