# 2026-10-27 主分支同步与分支整理

本次将 `codex/unified-production-window` 的 15 个新增提交以快进方式纳入 `main`，功能提交截至 `03afd1da20f69b9b6395fd5423d1388937adc02f`。未改写已有提交历史或 `v0.8.6` 标签。

主分支包含 0.9.0 交付源码及其后的错误诊断、STTN 输出校验、原生文件选择和 AI 去字幕页面设置改进。最新本地安装包仍为 0.9.0，后续源码修复尚未重新打包。

## 保留分支

- `main`：主代码。
- `codex/unified-production-window`：保留的开发分支，本轮功能提交已纳入主分支。
- `design/start-work`：独立设计原型，包含尚未纳入主分支的提交，继续保留。
- `v0.8.6`：发行基线标签，继续保留。

## 清理范围

以下 7 条旧功能分支的提交均已纳入主分支。主分支推送并核验后，删除其本地及远端分支名称；对应提交仍可通过主分支历史和下列提交号查阅。

| 旧分支 | 清理前提交 |
| --- | --- |
| `codex/continuous-studio-flow` | `714dafcc480a1220b27605ca51cb5a5ddf4f982c` |
| `codex/jianying-highlight-worker` | `3193727ae459098127624ef762cde4d0f134fd9e` |
| `codex/local-ai-engine-switch` | `a8ade65d6524f0bf12d968279c3682f5861016b3` |
| `codex/official-project-evidence` | `3dcb40e10a2353c521b85d069b4a00e8f88998f9` |
| `codex/publishing-workspace` | `811cf3470e293cdacbabf4ced83ffbd41a09b190` |
| `feature/full-video-subtitles` | `7236b8e33a803553048d69c4485a6d6e2d9069bc` |
| `feature/remove-video-generation` | `ea0713565bf2917b0546a401a264e50a9e4b3546` |

模型、引擎运行环境、安装包、真实素材、账号和密钥不属于本次源码上传或分支清理范围。
