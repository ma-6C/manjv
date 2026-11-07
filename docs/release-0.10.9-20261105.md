# 0.10.9 安装包

按用户要求将本次更新打包。保留0.10.8安装包和本机原有安装、配置及数据。

## 本次程序

随包小v喵已替换为当前模块中的3.1.0 build17重建版本，mode为local-reconstructed，profileLayout为workspace，入口vcat-local.exe。采用resources/app解包布局，9225个程序文件约811510646字节，实际文件集合和每个SHA-256都与模块清单一致。没有重新运行旧版复制/修复流程覆盖此次更新。

启动器、清单入口支持、新旧profile布局隔离均使用当前更新源码。明确选择的原profile不自动搬移或重建，旧版数据不自动合并到新版布局。实际配置数据库和原旧版数据库在安装版测试前后哈希保持一致。

## 验证

- 启动器和程序准备源码检查共22项通过，其中实际编译启动器检查19项通过。
- 43个产品模块重新编译；9338项构建输入记录；11231个发行文件完成清单签名。
- 安装运行库前置检查36项、配置备份重置辅助程序25项、NSIS升级场景25项通过。
- 完整0.10.8→0.10.9隔离升级：默认保留配置与明确重置配置均通过，日志分别记录32/34项检查（含恢复系统集成检查）。旧版移除、新版文件校验、配置备份、项目/账号/历史/授权/模型及小v喵数据保留通过。测试后原注册表与快捷方式恢复。
- 实际安装的小v喵在独立空白profile中启动：前端加载、重建JavaScript服务端、6个IPC通道、内存查询、43个数据库模型和新数据库路径均核对，9项启动检查通过；未使用真实账号。
- 实际安装的漫剧工坊EXE运行：37项通过，包括从真实入口打开随包小v喵，9225个运行副本文件哈希、新布局SQLite数据库、明确profile持久化和两份现有数据哈希。桌面测试结束只关闭本次创建的进程树。
- 编译版既有授权兼容31项通过，原签发工具、密钥及既有授权不变。
- Defender自定义扫描完成，防护保持启用，未发现匹配本版本的检测记录。

上游node-gyp依赖带有test/fixtures/server.key静态HTTPS测试夹具。核对其测试脚本引用及源码、模块清单和发行文件哈希后记录为上游测试资源；没有放宽其他.key文件或客户凭证的排除检查。安装包不含用户profile、Cookie、SQLite账号数据库、客户API密钥或签发私钥。

## 验收边界

本次为打包与隔离安装/启动验收，不重新验证真实账号读取、扫码、评论、私信、发布或云同步。用户此前软件内测试与旧模块结果没有移作当前版本的业务验收。离线AI引擎继续单独导入，本次不更换。

证据位于versions/v0.10.9：build-inputs.json、update-summary.json、payload-verification.json、installation-report.json、installation-reset-report.json、native-ui-report.json、xiaovmiao-reconstructed-startup.json、signing-compatibility.json、defender-scan.json等；编译导入证据位于release/v0.10.9/验收证据。

交付路径：release/v0.10.9/对外发送/漫剧工坊-安装程序-0.10.9.exe，大小687428591字节。SHA-256：94761f3e7005f22ae3ad07b1ddaa620a64db5a41a4d3da3ba4cbdc8bf32de2e3。
