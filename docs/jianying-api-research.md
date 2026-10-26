# 剪映接口核查与现有流程接入位置

核查日期：2026-10-26。范围为用户要求的“找到剪映接口”，未安装或调用新的第三方服务，未构建安装包。

后续根据用户提供的 `yichen-jianying-edit` 线索，已找到精确适配 Windows 剪映 11.6 的 `jy-draftc`，从源码构建并实际导出短样片。它解决的是原生引擎导出，仍不等于桌面打开指定工程。实时上游状态、试验结果与接入限制见 [Windows 原生引擎试验](jianying-native-engine-probe.md)。下文的 CapCut Mate 记录保留为 HTTP 草稿服务候选。

## 核查结论

已找到提供真实 HTTP API 的第三方开源项目 [CapCut Mate](https://github.com/Hommy-master/capcut-mate)。它可创建、编辑并保存剪映草稿；这是第三方草稿服务，不是剪映官方发布的本机控制 API。

目前没有找到剪映官方公开、可据文档调用的 Windows 本机“打开指定工程”接口。未检索到不代表绝对不存在，但不能据此承诺本机剪映 11.6 的全自动打开、播放或导出已经完成。

## 可接入的草稿 API

项目支持自部署，README 的本机示例基础地址为 `http://localhost:30000/openapi/capcut-mate/v1`。该地址需要另行启动 CapCut Mate 服务，当前漫剧工坊没有监听此端口，也没有新增这些路由。

| 请求 | 作用 |
|---|---|
| `POST /create_draft` | 创建草稿，返回 `draft_url` |
| `POST /add_videos` | 添加视频片段和时间线 |
| `POST /add_audios` | 添加音频片段 |
| `POST /add_captions` | 添加字幕片段 |
| `POST /save_draft` | 将草稿写入服务配置的草稿目录 |
| `GET /get_draft?draft_id=...` | 按草稿编号获取服务提供的草稿资源 |

接口契约见项目的 [OpenAPI 文件](https://github.com/Hommy-master/capcut-mate/blob/main/openapi.yaml)及 [README](https://github.com/Hommy-master/capcut-mate/blob/main/README.zh.md)。创建请求示例：

```http
POST /openapi/capcut-mate/v1/create_draft
Content-Type: application/json

{"width":1080,"height":1920}
```

后续请求沿用实际返回的 `draft_url`。`add_videos` 的 `video_infos` 是 JSON 字符串，片段时间使用微秒；不能直接用我们现有以秒为单位的数据或嵌套数组代替。请求示例仅说明文档契约，未做服务端调用验证。

保存实现见 [save_draft.py](https://github.com/Hommy-master/capcut-mate/blob/main/src/service/save_draft.py)：它保存缓存中的草稿对象。保存成功不证明本机剪映已发现、打开或接受该草稿。

## 自动打开及导出的限制

该项目的 `gen_video` 不是独立于剪映桌面界面的本机渲染接口。[video_task_manager.py](https://github.com/Hommy-master/capcut-mate/blob/main/src/utils/video_task_manager.py#L682) 仍调用 `JianyingController.export_draft()`。

核对 [jianying_controller.py](https://github.com/Hommy-master/capcut-mate/blob/main/src/pyJianYingDraft/jianying_controller.py#L511) 后确认：

- `export_draft` 注释明确声明当前仅支持剪映 6 及以下版本。
- 草稿定位仍依赖 `HomePageDraftTitle:<草稿名>` 的窗口控件。
- 导出等待逻辑还包含固定屏幕坐标点击，不能直接作为客户电脑兼容实现。

因此，新增一个 REST 调用层不会自动解决本机 11.6 的工程定位问题，不能把 `gen_video` 提交成功或草稿落盘作为“本机工程已打开”。

## 官方公开能力

[火山 VOD 控制台剪辑文档](https://docs.volcengine.com/docs/video_on_demand/ClippingthroughConsole?lang=zh)与[火山剧创 FAQ](https://docs.volcengine.com/docs/drama-creation/platform-function-faq?lang=zh)公开了导出剪映草稿包、解压/复制到本机草稿目录，再在剪映中打开的流程。这些资料没有给出本机 `OpenProject` 调用方法。

[火山云剪辑 OpenAPI](https://docs.volcengine.com/docs/video_on_demand/VideoclippingthroughOpenAPI?lang=zh) 的 `SubmitDirectEditTaskAsync` 属于云端视频剪辑，不能当成本机剪映工程打开接口。

## 漫剧工坊当前接入位置

当前源码已有真实草稿生成和本机导入功能，没有必要为了创建草稿重复部署一套服务。CapCut Mate 可保留为未来需要独立 HTTP 草稿服务时的候选。

| 当前代码/接口 | 实际行为 |
|---|---|
| `jianying_projects.py` | 使用已有草稿组件生成工程、校验素材与轨道 |
| `POST /api/jianying/install` | 复制并校验到实际剪映草稿目录，记录导入结果 |
| `POST /api/jianying/launch` | 启动已验证的本机编辑器，返回状态不冒充指定工程已打开 |
| `POST /api/jianying/open` | 打开工程文件夹；此路由不是打开剪映指定工程 |
| `jianying_automation.open_registered_project()` | 在实际控件可识别时尝试打开指定工程，并核对项目名和时间线；否则等待本人操作 |
| `studio_flow_adapter.py` 的 `editor_import` | 连续流程中交接本次工程；复制成功但未核验实际打开时保持等待，明确重检复用原导入副本 |

继续开发时应针对具体版本验证“指定工程打开”这一缺口，保留现有真实草稿和素材校验流程。只有实际打开了对应工程，才继续登记原生窗口截图；只启动应用不能算通过。

## 本次验证边界

本次仅完成上游文档、接口契约及自动导出实现的源码核查，没有新装依赖、上传素材、调用第三方草稿服务或云端付费接口。此前本机样片的剪映打开/播放验证与本次 API 研究分别记录，参见[真实工程接入说明](official-project-evidence.md)。
