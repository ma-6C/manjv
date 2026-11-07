# 0.10.8打包记录

按用户2026-11-05要求，将当前更新打包为新版本，原0.10.7交付包保留。

## 本次输入

与0.10.7构建记录对比，更新涉及server.py、xiaovmiao.py、小v喵module.json、resources/app.asar和EXE；另加入平台网页网络规则源码作为构建输入。用户更新中的平台webview联网修复和显式原数据目录传递均已合入。

打包时补充了随包程序内容变化后的数据连续使用：首次启动记录明确的数据目录；历史随包运行目录中仅有一份数据库时，直接继续使用该目录，不复制原数据；多份历史数据且未明确选择时提示指定，避免静默新建空库。已经配置的原数据目录优先，目录失效仍报错。

工作区小v喵修复副本按当前module.json逐个核验134个文件，实际文件集合与清单完全一致。未重新运行旧版准备脚本覆盖用户的更新副本。归档内网络脚本与engines/xiaovmiao-platform-network.js哈希一致。main.js支持MANJU_XIAOVMIAO_PROFILE。

## 构建与验收

- 246项构建输入核对无漂移，43个产品模块重新编译，2140个发行清单文件完成签名。
- 实际编译模块的小v喵检查11项通过，含旧数据目录延续及多目录歧义处理。
- 设置辅助程序25项、NSIS升级分支25项检查通过。
- 完整0.10.7→0.10.8升级分别测试默认保留配置与明确重置配置。两种模式通过，项目、授权、模型和小v喵数据保留，注册表和快捷方式按测试前快照恢复。日志记录32/34项检查（含恢复检查）。
- 安装出来的EXE实际启动，36项桌面运行检查通过；小v喵程序134个文件校验、真实启动、独立SQLite数据库与持久化数据目录选择通过。原修复版数据库哈希保持不变。
- Defender保持启用，自定义扫描未发现匹配本版本的检测记录。

## 网页验证边界

使用实际安装出来的小v喵EXE、新建隔离会话访问creator.douyin.com。平台webview网络请求被允许，DOM加载到1042字符、5张图片，未使用用户现有登录会话。

隐藏诊断窗口截图全黑，软件渲染重试截图仍只显示加载提示；尝试通过临时本机主进程诊断端口显示窗口也未取得可用接口。因此，本次只确认网页网络与DOM内容加载，不将完整登录画面列为通过，不声称扫码、账号识别、云同步或发布成功。诊断截图没有冒充正常登录页截图。

本次没有修改用户提供的第三方网络修复内容或关闭Electron归档完整性验证。主应用已有后端云调用限制沿用。新增的是漫剧工坊启动器的数据目录连续使用处理。

## 证据

versions/v0.10.8中的build-inputs.json、payload-verification.json、installation-report.json、installation-reset-report.json、native-ui-report.json、defender-scan.json、update-summary.json、xiaovmiao-network-payload.json、xiaovmiao-bundle-files.json、xiaovmiao-page-load.json和xiaovmiao-page-capture-review.json。

交付目录：release/v0.10.8/对外发送，包含安装程序、安装说明与SHA256SUMS.txt。安装程序大小685825335字节，SHA-256为df87ca06714977609365737f0686df197e766d27592900186bcb6f71c7b0583d。
