# 剪映草稿组件来源

- 上游：https://github.com/GuanYixuan/pyJianYingDraft
- 使用版本：PyPI `pyJianYingDraft==0.3.1`
- 许可证：Apache-2.0，原文保存在同目录 `LICENSE`。
- 本项目适配代码：`jianying_projects.py`、`jianying_timeline.py`、`jianying_editing.py`、`jianying_ai.py`、`jianying_registry.py`、`jianying_automation.py`。本轮根据用户提供的 VKH 剪映接口和反编译索引补写处理流程；没有获得其完整原始源码或附带其私有素材。
- 依赖由根目录 `requirements.txt` 固定版本，开发时安装到被 Git 忽略的 `vendor/`；发行收集规则已更新，本轮未执行打包。

当前使用组件支持的草稿创建、画面/音轨/字幕/滤镜/特效写入和草稿重新读取能力，不执行加密草稿解密，也不假定任意剪映版本均兼容。独立调节轨尚未实现，色彩调整使用可编辑关键帧。

本轮仅完成源码静态检查，没有运行模型、媒体或剪映验收，尚未重新打包。之前的历史检查不能作为本轮新增功能的运行证据。

语音识别和人声分离需要独立引擎内的 `requirements-ai.txt` 依赖及本地模型；主程序打包清单不等于 AI 引擎已包含它们。具体对齐范围、缺口和下次发行注意事项见 `docs/jianying-vkh-alignment.md`。
