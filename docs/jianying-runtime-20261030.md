# 2026-10-30 本机真实运行记录

此文记录本机源码运行证据，不包含模型、视频或原始运行日志。未构建新安装包，软件/模型运行与客户安装环境的验证分开记录。

## 工程与官方窗口

- 输入：本地示例第0118集，45.233秒，核对原片SHA256未变化；原文件和指纹记录保留在本机核验目录。
- 本机任务：`73b5129f97a3`；导出目录：`output/完整剪映工程-20261030/剪映工程/第0118集_20261030-132238_368532`。
- 22份独立视频素材，两份真实全长分离音频，20条可编辑字幕；素材区登记24份媒体。人声/背景声文件哈希不同，没有复制混合原声来冒充分轨。
- 同时写入 `draft_content.json`、`draft_info.json`、7类 `draft_materials` 和 `draft_virtual_store.json`，素材库ID关联时间线。导入新副本后全部素材重连，不更改参考工程。
- 官方剪映 `11.6.0.14552` 已打开目标工程，素材区可见两个WAV波形和视频切片缩略图，实际画面和时间线可读。源码数据中有独立中性调节轨；不把轨道存在当作明显调色效果。
- 首次截图因标题小字漏读而中断。对标题增加对比度识别并保持编号精确匹配，继续任务后复用原工程完成。截图标记 `projectIdentityVerified=true`、`projectTitleVerified=false`，通过实际可见唯一编号关联，没有声称完整截断标题已读出。
- 官方窗口原图：`tmp/jianying-final-20261030/data/official-project-evidence/bb83efd0b1346d55/9825ab82b29d4aa0.png`，未拼接、未修图。时间线缩放控件不可唯一识别，保留应用当前缩放并记录提示。

## GPU运行库组合

本机GPU：RTX4060 Laptop；torch/torchaudio `2.7.0+cu126`，Demucs4.0.1，faster-whisper1.2.1，CTranslate2 4.8.4。

| 选择 | 人声分离 | 语音识别 | 实际主要DLL来源 |
|---|---|---|---|
| PyTorch自带 | CUDA完成 | CUDA完成，20条字幕 | 原torch/lib |
| NVIDIA独立包 | CUDA完成 | CUDA完成，20条字幕 | 独立环境site-packages/nvidia/*/bin |

两种选择均无CPU回退，实际加载路径及输出哈希：`tmp/jianying-complete-20261030/cuda-switch/report.json`。

独立包版本固定为 cuBLAS `12.9.2.10`、cuDNN `9.7.1.26`、NVRTC `12.9.86`。包从NVIDIA官方PyPI发行文件下载，整包SHA256校验后安装。cuDNN9.27曾导致当前torch加载DLL入口失败；兼容测试记录保留在 `report-cudnn-9.27.json`，不能把安装成功视为推理成功。

- cuBLAS：https://pypi.org/project/nvidia-cublas-cu12/12.9.2.10/
- cuDNN：https://pypi.org/project/nvidia-cudnn-cu12/9.7.1.26/

自动模式按Torch GPU、NVIDIA GPU、CPU依次尝试，显式选择某套库则只尝试该套GPU后再回退CPU。每次使用独立工作进程；输入文件错误不会误触发设备重试。实际尝试在步骤开始、失败及完成时立即写日志与 `AI任务/*-attempts.json`，诊断摘要包含尝试和版本，隐藏完整本地路径。

客户RTX5060此前的 `no kernel image` 仍需支持其显卡架构的PyTorch/CUDA构建；本次4060测试不代表客户5060已验证，单独替换cuBLAS/cuDNN无法为旧Torch补入缺失内核。

## 发行边界

当前独立AI环境使用本机开发用 `.pth` 复用 `engines/vsr-env` 的torch依赖。模型来源记录在被Git忽略的 `engines/jianying-ai/models/model-sources.json`。发行时应构建包含匹配torch/torchaudio、推理依赖、本地模型的可移植引擎，再签名打包；不能直接复制当前venv或把旧去字幕ZIP当作新引擎。
