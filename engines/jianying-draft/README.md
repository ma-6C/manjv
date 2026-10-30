# 剪映草稿组件来源

- 上游：https://github.com/GuanYixuan/pyJianYingDraft
- 使用版本：PyPI `pyJianYingDraft==0.3.1`
- 许可证：Apache-2.0，原文保存在同目录 `LICENSE`。
- 本项目适配代码：`jianying_projects.py`、`jianying_timeline.py`、`jianying_editing.py`、`jianying_ai.py`、`jianying_registry.py`、`jianying_automation.py`。本轮根据用户提供的 VKH 剪映接口和反编译索引补写处理流程；没有获得其完整原始源码或附带其私有素材。
- 依赖由根目录 `requirements.txt` 固定版本，开发时安装到被 Git 忽略的 `vendor/`；发行收集规则已更新，本轮未执行打包。

当前使用组件支持的草稿创建、画面/音轨/字幕/滤镜/特效写入和草稿重新读取能力，不执行加密草稿解密，也不假定任意剪映版本均兼容。独立调节轨按用户提供的真实 `draft_info.json` 结构写入，初始参数中性，色彩调整使用可编辑关键帧。

2026-10-30 已在本机实际运行45秒第118集原视频，生成22个独立视频、真实人声/背景声和20条识别字幕，原生素材库登记及官方剪映窗口截图通过。PyTorch自带库和NVIDIA独立包分别完成GPU分离/识别，实际DLL路径有记录。证据见 `docs/jianying-runtime-20261030.md`。本轮未重新打包，客户显卡和旧安装包不能据此视为已验证。

语音识别和人声分离需要独立引擎内的 `requirements-ai.txt` 依赖及本地模型；主程序打包清单不等于 AI 引擎已包含它们。具体对齐范围、缺口和下次发行注意事项见 `docs/jianying-vkh-alignment.md`。
