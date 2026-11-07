# 抖音登录后未进入账号分组：恢复原始账号流程

> 最新状态：已交付保持直接进入主界面的本地账号适配版，见 `docs/xiaovmiao-local-accounts-20261105.md`。以下内容为此前阶段记录。

> **本方案已撤回。** 用户指出重新出现了小v猫软件自身的扫码登录页，这偏离了直接进入主界面再添加抖音账号的需求。当前模块已按备份逐字节恢复至此前的 `local-platform-browser` 版本，原数据路径保持不变。恢复记录见 `tmp/xiaovmiao-direct-entry-restored.json`。下文仅保留探索过程，不能当作当前交付状态。抖音账号自动入组的问题仍未解决。

用户的目标是在添加账号窗口完成抖音登录后，左侧默认分组出现真实头像、昵称和账号，点击后能打开该账号的创作者中心。

## 实际诊断

当前修复版日志显示，添加流程在 `LoginAccount.getUidAccount` 处报 `Offline local mode: external operation unavailable`。前端在这一检查之后才调用 `AccountManager.addAccount`。对用户数据库的只读副本查询显示，`account` 和相关账号表仍为 0 条，因此不是左侧分组过滤隐藏了已有账号。

进一步检查发现，用户指定的本地修复版不仅限制联网，还改写了软件自身的登录响应，并绕过原始的账号初始化。11 月 4 日的修复只恢复了平台 webview 网页联网，未恢复这套完整账号流程。

尝试在空白数据库用合成资料验证原生本地保存和恢复，未得到完整通过的结果。所有这些探索只发生在 `tmp/xiaovmiao-account-probe`；没有把合成账号写入用户数据库，也没有把未验证的本地账号适配器加入交付程序。实验源码已归档在该目录的 `source` 中。

## 当前采用的修改

以 `D:\小v猫` 中保留的原始程序为基准恢复完整账号流程，其 EXE 与 ASAR 的 SHA-256 分别与之前原件记录一致：

- EXE：`b98eac57282fdff719b185cff2a2f9c186ea2cf566d6ceedece8e6cd58cabbb2`
- ASAR：`8a70a8240265f4bffee4be98ec715cd7530f504189249946a83b29e41f41a33b`

保留原始的 `preload.js` 和 `server/server.jsc`，恢复原始软件登录、`runner.beforLoadAccounts`、`AccountManager.loadAllAccounts`、账号查重、登记和分组调用。没有修改软件会员、权限或平台认证逻辑。

只做两处适配：在 `main.js` 前加入用户选定数据路径的配置；在前端保留跳过启动时自动清理非缓存数据的处理。全局离线 DNS、网页拦截、Node/Electron 网络禁用、模拟登录响应、强制离线数据库初始化均已从当前交付归档移除。

当前程序放在 `modules/xiaovmiao/程序`，模块清单的模式为 `standard-account-flow`。启动入口和 `data/xiaovmiao.json` 中选定的数据路径保持不变。当前状态接口会报告 `accountFlow: original-online`、`localMode: false`。

原程序和原数据仍在原目录。上一交付程序的 ASAR、EXE、模块清单备份于 `tmp/xiaovmiao-account-flow-backups`，具体路径记录在 `tmp/xiaovmiao-account-flow-promotion.json`。

构建工具：

- `tools/restore_xiaovmiao_account_flow.py`：从原始程序准备正常账号流程副本，并核对未修改的归档条目。
- `tools/verify_xiaovmiao_account_flow.py`：只用全新测试目录观察正常启动，不操作账号登录。
- `tools/promote_xiaovmiao_account_flow.py`：备份旧程序，检查文件锁后更新模块与完整性清单。

## 验证与待核对部分

已通过：原始桥接与编译后端哈希核对、正常主文档真实启动检查、11 项启动与数据路径测试、模块程序 SHA-256 清单核对。启动测试不使用用户现有账号或会话。

尚未通过真实账号验收：软件自身正常登录、抖音账号识别、登记到左侧、重启后账号恢复。不能用启动成功或合成记录声称这些步骤已完成。

下一步由用户完全退出旧小v猫，再通过 `启动小v喵.ps1` 或重启源码版漫剧工坊后点击“小v喵”。如果程序要求软件自身登录，应先在原始正常登录流程中完成，再添加抖音账号。代理、云同步等功能也将遵循原程序的正常权限和服务状态。本轮未重新制作漫剧工坊安装包。
