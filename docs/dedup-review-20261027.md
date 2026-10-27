# 去重设置：现状与 GitHub 改进建议

后续实施和实际验收见 [去重设置改进与源码验收](dedup-implementation-20261027.md)。本文保留改进前的审查记录。

核查日期：2026-10-27。当前源码提交 `3cdb6c30`。本次为只读代码审查、官方仓库及文档检索、FFmpeg能力枚举；未修改产品处理逻辑、安装包或客户数据，也未执行平台审核测试。

## 当前实现

`web/app.js:52` 提供亮度、对比度、饱和度、播放速度、中心裁切五项参数，另有三组固定预设及片头AI标识。修改影响以后创建的任务，任务入队时固定配置；已经排队的任务不随全局配置变化。

`server.py:720` 的滤镜顺序是变速、30fps归一化、中心裁切、保持比例缩放及补边、像素比例、调色与可选标识。

当前已具备的优化应保留：尺寸一致时跳过无效缩放；原速音轨跳过atempo；重组的帧计划和关键帧对齐满足条件时，后续分集复用视频流；连续高光包装不会再次施加之前的调色、裁切和速度。GPU编码也已按实际尺寸探测并提供CPU回退。

## 优先修复

| 顺序 | 问题或改进 | 当前证据 | 建议行为 |
|---|---|---|---|
| 1 | 数字与滑块显示不一致 | `web/app.js:158,169-171` 只实现滑块向数字框同步 | 双向同步；显示保存中、已保存、失败；不重建正在输入的DOM |
| 1 | 数值类型边界 | `server.py:181,213` 检查float转换结果但未写回全部配置；数字字符串和bool可通过部分范围校验 | 数值字段拒绝bool，统一写回数值；空输入不静默转0；错误回到最后有效值 |
| 2 | 本页没有真实处理前后对比 | `web/app.js:52` 无视频选择与试片任务 | 选视频、选时间点、处理5/10秒、同步播放；预览和正式制作使用同一滤镜计划 |
| 3 | 裁切效果难以预判 | 单边15%会使宽高各剩70%，原画面面积约剩49% | 显示裁切框、保留比例、输出画幅；允许分别调整四边；显示字幕安全区 |
| 4 | 操作范围不清楚 | 本页底部“开始制作”仍启动完整pipeline，配置全局共享 | 显示本次剧集/集数、启用步骤；分清短片试处理与完整制作；保存具名方案 |
| 5 | 编码与包装仍可能两次编码 | `server.py:1397` 后接 `highlight_render.py:62`；变换已归零但画面仍再编码 | 对兼容路径合成一次渲染计划，保留已有检查点/恢复策略 |
| 6 | GPU主要负责编码 | `server.py:824-834` 的crop/scale/eq仍为CPU滤镜 | 明确显示实际负责环节；逐条测试GPU滤镜链，失败回兼容路径 |

`highlight_render.py:62` 直接计算时长除以速度，因此配置以数字字符串传入却未正规化时会失败。普通网页输入会发送Number，这一类型问题主要影响外部配置/API边界。

## GitHub核查

以下列的是上游公开能力及本项目建议，尚未作为新功能接入。

| 项目与核查入口 | 可参考的能力 | 本项目采用建议与边界 |
|---|---|---|
| [rigaya/NVEnc 参数说明](https://github.com/rigaya/NVEnc/blob/master/NVEncC_Options.en.md) | NVDEC硬解、VPP画面处理、NVENC编码；tweak/resize/transform等参数 | 研究NVIDIA的硬解—滤镜—编码链路，减少往返CPU。它是NVIDIA专用路线，原AMD/Intel/CPU路径应保留；需要实际驱动、画幅和滤镜组合测试 |
| [mifi/lossless-cut 故障与Smart Cut说明](https://github.com/mifi/lossless-cut/blob/master/docs/troubleshooting.md) | 流复制、关键帧边界、仅重编码必要部分的实验性Smart Cut | 参考减少重复编码的思路。Smart Cut上游明确为实验性，不能替代所有精确分集任务；有画面变换时通常仍需编码 |
| [Breakthrough/PySceneDetect](https://github.com/Breakthrough/PySceneDetect) 与 [AdaptiveDetector源码](https://github.com/Breakthrough/PySceneDetect/blob/main/scenedetect/detectors/adaptive_detector.py) | 镜头边界；自适应检测减少快速镜头运动带来的误分段 | 为高光选段、镜头衔接提供候选切点，接入现有镜头分析缓存。镜头切分不等于情节理解，也不提供平台审核保证 |
| [Netflix/vmaf 的FFmpeg集成说明](https://github.com/Netflix/vmaf/blob/master/resource/doc/ffmpeg.md) | 参考源和处理结果的画质比较，时间戳及帧率对齐 | 在短片对比中增加编码损失检查。刻意裁切/变速/调色会影响比较，须对齐、控制变量；指标不能叫“平台去重率” |
| [0x90d/videoduplicatefinder](https://github.com/0x90d/videoduplicatefinder) | 本地素材相似匹配、部分片段匹配、缓存复查 | 作为素材库重复集数/重复片头提醒的参考；属于单独的素材检查能力。仓库当前标注AGPLv3，不能把公开仓库视作可直接复制进闭源主程序的授权 |

以前提到的 `sdlw7757/Video-Dedup-Tool` 本次直接访问仓库返回404；搜索仍可看到旧README缓存。未将缓存当作当前完整可用、已获授权的依赖，不作为本轮首选接入对象。

## 当前发行引擎能力

实际枚举的文件：`release/v0.9.0/漫剧工坊/_internal/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe`。

已列出 `cropdetect`、`scdet`、`blackdetect`、`freezedetect`、`ssim`、`psnr`、`libvmaf`、`scale_cuda`、`colorspace_cuda`、`hwupload_cuda`、`signature`。这是滤镜清单核对，未证明每种GPU链路在本机或客户显卡上都可运行，也没有新增速度基准。

建议先利用既有FFmpeg与已有镜头缓存，避免为预览、简单裁切检测或短片画质比较新增整套运行环境。

## 实施顺序与验收

1. 修参数同步、错误恢复与数值正规化，验证数字输入、滑块、空值、保存失败和任务配置固定。
2. 增加真实短片对比、裁切框、输出时长及处理范围；前后播放器同步、离开页面停止播放，保持输入焦点。
3. 建立具名方案和中性滤镜优化。当前30fps用于准确分集及尾帧保护，不能直接删掉fps归一化；保留原帧率/流复制需单独检测兼容性。
4. 用相同素材、相同画幅和同等编码质量，对比合并渲染与GPU滤镜路线；验收完整解码、时长、帧数、音轨、原片哈希、取消及恢复。
5. 再扩展镜头辅助选段和本地重复素材提醒。

界面检查参考已读取的 `ui-ux-pro-max`：使用明确的保存反馈和就地错误恢复，避免只弹一次toast后留存错误数值。以上为待实施方案，已交付的0.9.0安装包保持原样。
