# 小v喵模块替换为用户提供的重建版本

2026-11-05，按用户指定的新版本目录 `D:\超人\小V猫_脱壳_20261103` 替换当前模块。实际采用 `可运行验证/runtime/vcat-local.exe`，其 package.json 标记为 3.1.0 build 17。目录内的代码分析 ZIP 和旧 ASAR 版不是本次入口。

## 程序与数据

- 模块入口：`D:\ai视频助手\modules\xiaovmiao\程序\vcat-local.exe`。
- 继续使用新版现有数据：`D:\超人\小V猫_脱壳_20261103\可运行验证\profile`。
- 新版实际数据库布局：`profile/workspace/.vcat/offline-local/vcat.db`；会话由新版 Electron 管理。
- 原旧版数据 `D:\小v喵\本地初始化修复_20261103\本地数据` 原样保留，没有混入新布局，也没有清空。
- 旧模块及旧启动配置整体备份在 `tmp/xiaovmiao-replacement-backups/1793870970022913300`。
- 模块清单只包含 9,225 个程序文件，不携带真实 profile、Cookie、数据库或测试日志。

新版采用解包的 `resources/app`，没有 `resources/app.asar`。启动器现支持两种布局，并从清单读取 EXE 名。对旧文件名、旧数据布局保持兼容。只在暂存副本的 `resources/app/main.js` 增加 `MANJU_XIAOVMIAO_PROFILE` 覆盖；新源目录、业务代码、原 EXE 均不修改。

模块整体切换，不在旧目录上叠加文件。`data/xiaovmiao.json` 已指定新 EXE 和新版原 profile。旧版账号识别适配器不再注入新版本；新版本自身提供其账号、评论和话术等业务实现，本次不重复应用旧补丁。

## 验证与证据

- 全部程序文件逐文件 SHA-256 核对；正式切换前再次核对清单。
- 22 项启动器、路径、复制、布局隔离、环境变量和 profile 适配检查通过。
- 空白独立 profile 中实际运行新 Electron：前端文件加载成功，重建 JavaScript 服务端加载，6 个 IPC 通道注册，本地内存查询有效，43 个数据库模型初始化。进程按测试参数正常退出，无启动错误。
- 测试明确使用空白数据，不使用真实登录会话，不执行真实评论、私信或发布。新源说明中此前的账号和作品读取结论不等同于本次验证。
- `tmp/xiaovmiao-reconstructed-20261105/smoke.json` 为隔离启动结果，`tmp/xiaovmiao-reconstructed-replacement.json` 为切换、备份和运行副本记录。

## 使用与回滚

正在运行的漫剧工坊服务缓存了旧启动器与路径，旧小v喵进程也不会自动更新。完全退出旧小v喵及漫剧工坊，再从本目录 `启动.ps1` 打开漫剧工坊，点击左侧“小v喵”。`启动小v喵.ps1` 也会从新配置直接启动新版。无需移动或重建 profile。

当前本机程序与启动器已更新，漫剧工坊 EXE 和安装包未重新制作。真实账号在替换后的实际读取、评论操作及发布结果仍需现场核对，不能用空白环境启动成功代替。

回滚时须先退出相关程序，保留两套现有数据，然后将备份的 `module` 与 `xiaovmiao.json` 恢复到原位置。回滚程序不删除或转换新 profile。
