# 漫剧工坊 0.9.2：STTN 显卡兼容性回退

日期：2026-10-28。

## 问题与原因

客户提供的完整日志在 STTN 第一批帧推理时报告 `CUDA error: no kernel image is available for execution on the device`，随后在写入器收尾时显示 `STTN video encoder received no frames`。前者是此次失败的首个明确原因，说明当前 GPU 执行链没有适合该设备的 CUDA 内核；后者是未生成修复帧的结果。

离线 v1 引擎的 STTN 循环会打印并吞掉推理异常，导致最终错误被收尾异常覆盖。0.9.1 中的设备回退仅作用于 LaMa 框选路线，STTN 未实现同样的回退。

主程序与 v1 引擎的组件格式及签名兼容，不代表其 GPU 运行库覆盖所有显卡架构。已核对本机 `release/v0.6.0/对外发送/漫剧工坊-AI离线引擎-v1.zip`，它与 v0.5.0、v0.8.1 保存的同名包完全一致。包 SHA256 为 `5c70c7ae0fcbad1fa705b0d43e0c5777d164a6c45d8af74a42db315b4c61ab1c`。

NVIDIA 对该 CUDA 错误的定义见[CUDA runtime 错误类型](https://nvidia.github.io/cuda-python/cuda-bindings/latest/module/runtime.html)。运行环境支持的架构与实际设备能力可分别通过 PyTorch 的 [get_arch_list](https://docs.pytorch.org/docs/stable/generated/torch.cuda.get_arch_list.html) 和 [get_device_capability](https://docs.pytorch.org/docs/stable/generated/torch.cuda.get_device_capability.html) 查看。

客户随后提供了环境截图：RTX 5060 Laptop GPU，驱动 577.05，NVENC 编码检测通过。原 v1 包为 PyTorch 2.7.0+cu126、torchvision 0.22.0+cu126。针对该显卡另行制作 CUDA 12.8 的 v2 引擎包，保留同版本 PyTorch/torchvision API 及原模型。Blackwell 支持与 cu128 构建依据见 [PyTorch 2.7 官方说明](https://pytorch.org/blog/pytorch-2-7/)；NVENC 通过仅证明视频编码链路，与 AI 推理支持是独立检查。

## 本版修改

- AI 去字幕页面设置中新增独立的「STTN 推理设备」：自动，或 CPU；保留独立的 LaMa 设备选择。
- 自动模式识别明确的 CUDA 内核/架构/驱动兼容性错误后，关闭失败的工作进程，在启动新进程前隐藏 CUDA，再从头使用 CPU 处理当前视频。只回退一次，CPU 失败仍明确报错。
- 本次应用运行期间记住相同引擎的兼容性失败，后续视频使用 CPU，避免每集重复触发同一个 GPU 错误。重启应用或引擎指纹变化后重新判断。
- 回退时显示警告、原始原因和耗时提示，重置当前视频的帧进度与速度采样；成功后记录实际推理设备。
- 在工作进程内保留 STTN 首个推理异常及其堆栈，避免被「没有收到画面帧」覆盖。CUDA 清理出错也不覆盖首个异常。
- 诊断优先识别 CUDA 兼容性错误，明确给出 CPU 设备设置入口。

## 交付与边界

安装文件位于 `release/v0.9.2/对外发送/`。客户退出旧版后覆盖安装主程序。安装程序可选的引擎导入会优先识别同目录的 v2-cu128 ZIP，没有 v2 时沿用 v1。RTX 50 系列客户也可从「授权与组件」导入 `漫剧工坊-AI离线引擎-v2-cu128.zip`，导入后使用自动推理设备。该包导入到独立新目录，原 v1 引擎保留；不要手工覆盖旧引擎内部文件。

CPU 回退会增加处理时间；它绕过 GPU 故障，不代表已使该显卡支持旧 cu126 引擎。v2 改为匹配 Blackwell 的 cu128 运行库，未在客户显卡上实测。ONNX 未安装的跳过提示不是此次 STTN 错误的根因。

按用户要求，本轮只做源码修改、静态核对、编译和安装包构建，不运行模型、浏览器或安装验收测试，不宣称已在客户电脑复现或实测修复成功。具体构建记录位于 `versions/v0.9.2/`。
