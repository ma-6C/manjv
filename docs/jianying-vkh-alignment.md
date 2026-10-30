# 剪映工程流程对齐记录

本轮参考用户提供的 VKH7.0.3 剪映接口声明、函数索引及带常量注释的反编译材料，补写独立实现。资料中的 `.pyi` 没有函数体，关键 11 条记录只有汇编；本项目不声称逐行恢复了原代码或获得完全相同的输出。

## 已接入的代码路径

| 流程 | 本项目实现 | 边界 |
|---|---|---|
| 场景与切片 | `jianying_projects.py`、`jianying_timeline.py` | 采用已有场景分析，可生成独立视频文件；原视频保留 |
| 轻微变速 | `jianying_editing.mapped_intervals` | 分别保存源时长与目标时长，按同一映射重排原声、分离音轨和字幕 |
| 人声分离 | `jianying_ai.py` | 独立 Python 进程使用本地 Demucs 仓库；真实输出通过格式、时长检查后才生成两条轨道 |
| 语音识别 | `jianying_ai.py` | 优先已有 SRT；可通过本地 faster-whisper 产生逐词时间戳并分行；无文字时不插占位字幕 |
| 音频时间校准 | `jianying_editing.activity/captions` | 使用真实音频 RMS 区间微调分离人声的字幕边界；声音分段保留静音和微弱声音，不将低能量当作应删除内容 |
| 声音素材库 | `jianying_editing.library_files/select_materials` | 仅扫描用户选定的 `bgm` / `sfx` 子目录，按氛围关键词和稳定散列选择；不生成不存在的声音素材 |
| 配乐避让 | `jianying_timeline.append_audio` | 在测量的原声或人声活动区间加入音量关键帧；并非语义对白判断 |
| 画面包装 | `jianying_editing.style_video/layers` | 风格、推拉、亮度/对比度/饱和度关键帧、独立滤镜/特效层、短转场、文字角标 |
| 草稿登记 | `jianying_registry.register` | 仅登记本工具已导入的副本；进程退出后备份索引并置顶；原有其他草稿条目保留；写前再核对进程和原始索引 |
| 封面识别 | `jianying_registry.mark_cover/find_mark` | 独立封面标记，32 位目标编码，唯一匹配后双击；不修改源视频或原始封面；成功打开后恢复封面内容 |
| 自动出图 | `project_evidence.Manager.auto_capture` | 异步打开、核对标题及时间线、置前最大化、可选放大及预览、等待稳定、原始窗口截图；截图归属自动匹配与本人确认分开记录 |

## 依赖和模型

桌面程序仍使用既有 `pyJianYingDraft==0.3.1` 写工程。AI 依赖放在独立引擎 Python；依赖清单为 `engines/jianying-draft/requirements-ai.txt`。2026-10-30 已安装依赖、本地模型并完成真实GPU处理和剪映窗口核验；证据见 `jianying-runtime-20261030.md`。

本页模型目录结构：

```
剪映AI模型/
  faster-whisper/
    model.bin
    config.json
    tokenizer.json
    ... 模型所需的其他本地文件
  demucs/
    htdemucs.yaml
    ... 该 yaml 引用的官方 .th 权重
```

Demucs 的模型名和本地仓库必须匹配。GPU 失败会先结束进程，再启动 CPU 进程，保留两次错误；缺依赖或模型不执行无意义的 GPU 重试。禁止在处理过程中自动下载模型。`AI 处理失败时` 可以选择停止，或保留混合原声/已有 SRT 并明确标注缺失步骤。兼容降级不等于分离和识别完成。

实现依据为上游接口：
- https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/transcribe.py
- https://github.com/facebookresearch/demucs/blob/main/demucs/pretrained.py
- https://github.com/facebookresearch/demucs/blob/main/demucs/apply.py

## 尚不能宣称等同的部分

- 没有恢复原程序的私有模板、素材、具体随机策略或全部 262 个函数记录。
- 用户提供本机实际工程后，已从明文 `draft_info.json` 核对并补写原生独立 `adjust` 调节轨结构（placeholder + LUT + HSL 引用）。初始参数按样本保持中性；既有风格调色仍由画面关键帧实现。结构写入不等于本轮已完成剪映运行验收。
- 角标为可编辑文字，不宣称等同于原程序的贴纸资源管理器。
- 剪映滤镜/特效/转场使用已存在的组件资源编号；编辑器版本、会员状态和缓存资源是否适用，必须在真实剪映中核对。
- 不强制退出用户正在编辑的工程，也不在编辑器运行时重写其索引。
- 已完成本机第118集的语音、人声分离、媒体切片、首个草稿打开及实际窗口截图。切点和语音识别是本项目的独立算法，22个镜头、20条字幕不等于参考工程的10个镜头、19条字幕；没有声称逐帧相同或适配任意剪映版本。
- 尚未重新打包。旧版 0.9.3 安装程序和已发出的去字幕引擎包不包含本轮新增能力或对应模型。

## 下次发行必须核对

`build_hardened.py` 已加入任务串联、声音素材、原生素材库及可见标题识别模块，并收集Windows OCR依赖。打包桌面程序不会自动把 AI 模型和依赖放进已有去字幕引擎 ZIP；如要客户离线使用识别及分离，必须另行构建并签名包含上述依赖和模型的引擎组件，并记录实际模型、torch/torchaudio、CUDA 和 CTranslate2 版本。当前开发环境通过本机 `.pth` 复用已有torch，不能直接当作客户可移植引擎发送。
