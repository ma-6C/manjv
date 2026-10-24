# 剪映草稿组件来源

- 上游：https://github.com/GuanYixuan/pyJianYingDraft
- 使用版本：PyPI `pyJianYingDraft==0.3.1`
- 许可证：Apache-2.0，原文保存在同目录 `LICENSE`。
- 本项目适配代码：`jianying_projects.py`；没有复制第三方商业软件的代码、模板、音效或素材。
- 依赖由根目录 `requirements.txt` 固定版本，开发时安装到被 Git 忽略的 `vendor/`；发行收集规则已更新，本轮未执行打包。

当前仅使用公开的草稿创建、画面/音轨/字幕轨写入和草稿重新读取能力，不执行加密草稿解密，也不假定任意剪映版本均兼容。

文件结构、素材校验与时间线测试通过，不代表剪映主程序已经成功打开；本机未安装剪映，编辑器预览和真实截图尚待核验。
