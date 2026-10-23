# 开源复用记录

核对日期：2026-10-18。以下版本来自当日实际读取的仓库树和许可证。公开仓库不等同于已经安装或验证。

| 项目 | 核对版本及许可证 | 本项目采用方式 |
|---|---|---|
| [mifi/lossless-cut](https://github.com/mifi/lossless-cut) | `0cf3976506b411e595aea60f0f797f41171a5b31`，GPL-2.0 | 核对能力，不复制源码；分集使用自行编写的FFmpeg流程 |
| [sdlw7757/Video-Dedup-Tool](https://github.com/sdlw7757/Video-Dedup-Tool) | `bfe7438f6ed675c2dd80ccc40a5e6cbe42468556`，未发现仓库项目级许可证 | 不复制源码；捆绑Python或FFmpeg自身许可证不能替代作者工具代码的授权 |
| [YaoFANGUK/video-subtitle-remover](https://github.com/YaoFANGUK/video-subtitle-remover) | `e109b9ddc1d0e8f153199dfa05c1d767546906d8`，Apache-2.0 | 按已核对命令行编写独立引擎适配，不捆绑模型与源码 |
| [dreammis/social-auto-upload](https://github.com/dreammis/social-auto-upload) | `0012d2c355f88f683cc38dde2a2db209e14091bc`，MIT | 实际复用腾讯上传模块、基类及所需utils，源文件位于 `engines/social-auto-upload`，保留原许可证 |
| [DevilJie/social-auto-upload-web-ui](https://github.com/DevilJie/social-auto-upload-web-ui) | `fbf79a49b639a1b762e4d5c4ec48c87094e860cd`，MIT | 核对能力与结构，不复制其界面；当前桌面界面独立实现 |

`engine_bridge.py` 是本项目编写的适配层。引擎目录的 `conf.py` 是本地运行配置，`SOURCE.json` 记录源仓库和固定提交。上游运行日志只写本地，账号文件和用户素材不进入源码包。

上传复用只涉及视频号普通视频后台，不能视为短剧机构整剧提审实现。当前尚未使用真实账号验证平台兼容性。

FFmpeg、Python、WebView2及各Python依赖分别遵循各自许可证，发布运行版保留相应许可证和通知文件。开源引擎代码不代表平台官方SDK。
