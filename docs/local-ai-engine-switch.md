# 本地修复引擎切换与超人组件核对

2026-10-25，源码功能更新。本轮没有生成安装包或新的离线引擎包，也没有向既有引擎目录写入适配代码。

## 本次可以选择的两条本地修复路线

在「AI 去字幕 → 本地 AI 引擎 → 本地修复引擎」选择：

- **STTN · 时序视频修复**：保留原有路线，利用前后帧处理字幕区域。
- **LaMa · 框选区域逐帧修复**：新增独立适配器，用已有 `big-lama.pt` 对每帧的选区修复。上下文可从选区外读取，但模型结果只写回用户框选范围。

选择引擎会自动切换到本地 AI 处理模式。新任务固定当时的引擎和设备配置；之后修改设置不影响已排队任务。重启、页面刷新及离线引擎发现过程保留用户的模型选择。

两条路线都适用于 5/10 秒试处理、当前整集、所选多集连续处理，以及完整制作中的字幕步骤。试处理显示实际引擎名；切换引擎后，旧试处理标记为需要重新处理。

STTN 和 LaMa 分别复用自己的工作进程与模型。切换时关闭上一套进程，空闲 120 秒释放；关闭复用选项后逐集重新启动。暂停/停止会终止当前未完成视频，已完成检查点继续保留。

工作进程只监视自己的权重文件，避免原 VSR 初始化时合并其他模型分片而导致当前 STTN 缓存被误判失效。

LaMa 自动优先使用本机可用 CUDA，真实加载或推理失败时回退 CPU，也可单独选择 CPU。该选项独立于 FFmpeg 编码的 GPU 设置，不保证每个 NVIDIA 型号在当前 PyTorch/CUDA 环境中都能使用硬件推理。

LaMa 输出 H.264，音轨由应用恢复并核对完整时长。中文路径通过 Python 文件对象加载 TorchScript，避免 LibTorch 的窄字符路径失败。没有使用遮盖、模糊或 `delogo` 来冒充神经网络修复。

LaMa 是逐帧模型，动态背景可能有闪烁；STTN 与 LaMa 对不同素材的效果需要同片试处理比较，不承诺任意素材无痕或平台审核通过。

## 运行条件

使用现有本地 VSR Python 环境中的 PyTorch、NumPy、OpenCV。LaMa 需要：

`<VSR 项目目录>/backend/models/big-lama/big-lama.pt`

本机文件约 196.3 MiB，已有，无需再次下载。若其他客户的离线包没有这个模型，创建任务前会提示缺失，可先切回 STTN；不能仅因机器装过旧 AI 包就判断第二套模型可用。

`lama_local.py` 是本软件适配代码。工作进程源码由主程序持有，通过现有可选 Python 环境运行；不改已签名引擎目录，也不加载超人商业程序或授权模块。

## 超人包与恢复材料的实际结论

核对目录：`D:/超人/超人助手`、`D:/超人/源码恢复_6.08`。

- 包里实际有 RapidOCR 的检测、识别、方向分类 ONNX 模型，以及 faster-whisper Tiny。它们是画面文字识别、语音转文字模型，不是背景修复模型。
- Whisper 模型四个文件已与官方 `Systran/faster-whisper-tiny`、revision `d90ca5fe260221311c53c58e660288d3deb8d356` 的 Git/LFS 校验值匹配。`model.bin` 为 75,538,270 字节。
- 使用从公开 PyPI 安装的干净依赖独立验证，未运行超人主程序、注入脚本或授权服务。识别测试中禁用网络，客户样片没有上传。
- RapidOCR 实际读出样片中的「科学预防不慌张」「乱传谣言最荒唐」「学到了」，同时返回文字坐标。
- Whisper Tiny 实际生成 12 秒样本的时间码字幕，但有「预防不慌张」等词语的误识别，不能把这次可运行验证当成准确率验收。
- 临时语音测试的 PyAV 19 与 faster-whisper 1.2.1 的 `metadata_errors` 调用不兼容，固定 PyAV 18.1.0 后通过。这些识别依赖只位于 `tmp/local-ai-probe/vendor`，没有加入正式主程序依赖。
- 恢复目录的说明明确标注为接口声明、C 伪代码和常量等分析材料，并不是可重编译运行的完整 Python 工程。
- `quzimu_bridge` 和 `volc_quzimu_bridge` 有鉴权、上传、提交、轮询、下载等接口；当前材料支持云端去字幕的判断。未找到其另一套可独立调用的完整本地修复引擎。

**新增 LaMa 路线不等于已复现超人原版去字幕引擎。** 本次实现的是两套实际可运行的公开本地修复模型选择；超人同款 OCR/ASR 的独立验证另列，不混同为修复引擎，也尚未接成软件内的识别任务页面。

## 实际验证

- `verify_local_repair_engines.py`：12 项，两套真实模型、每任务固定选择、不同片段的 LaMa 缓存复用、完整音轨、完整解码、框选范围、重启保留选择、缺模型预检、真实 CPU 路径和原片哈希。
- `verify_lama_long.py`：6 项，180 秒、640×368、2fps 的 360 帧样片，完整输出、H.264、音轨、中途取消、原片保护。该样片是时长覆盖检查，不代表常规 25/30fps 素材吞吐。
- `verify_local_repair_ui.cjs`：16 项，真实 Edge 点击切换、分别提交实际试处理、引擎标签、旧预览提示、H.264 解码与播放、刷新保留及窄窗口。
- 原 `verify_subtitle_full.py`、`verify_production_handoff.py` 和 `verify_vsr_pool.py` 继续回归。

所有验收使用独立 `MANJU_DATA`，没有修改正常工作空间的客户任务。

## 公开组件来源

- LaMa：https://github.com/advimman/lama ，Apache-2.0。
- VSR：https://github.com/YaoFANGUK/video-subtitle-remover ，本机安装记录 commit `e109b9ddc1d0e8f153199dfa05c1d767546906d8`。
- RapidOCR：https://github.com/RapidAI/RapidOCR ，Apache-2.0。
- faster-whisper：https://github.com/SYSTRAN/faster-whisper ，MIT。

可复现识别探针：`tools/probe_local_ai.py`，需要显式提供本地模型、干净依赖目录、视频和输出路径；它不会自动下载模型或加载生产配置。
