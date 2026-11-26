# 素材库迁移验证

2026-11-08（Asia/Shanghai）。旧新路径、文件身份及可恢复备份见 [迁移清单](../library-migration-2026-11-08.json)。

## 通过项

- 229 个原包文件全部迁入，原目录已移除；202 张 PNG、6 份色板与 9 张 JPG 原始字节保持一致。
- 现有 `Assets/` 的 12 个文件全部保留；只更新迁入的说明和索引，没有覆盖素材原稿。
- 索引 217 条完整覆盖图片 / 色板，ID 无重复、所有路径存在，候选台账与路径一致；补录原索引漏掉的 2 张参考图。
- 42 处本地 Markdown 链接已检查，新增素材库链接全部有效。根 README 原有 `problems/05-quality-readiness-verification.md` 目标缺失，迁移前即存在；本轮保持原引用，未编造该报告。
- `python3 Scripts/verify_assets.py` 通过：51 份 App 导出与 8 份运行时配方输入身份未变。
- `./Scripts/build.sh` 退出 0，见 [build.log](build.log)。初次沙箱运行无法连接 CoreSimulator，退出 70，原日志保留为 [build-sandbox.log](build-sandbox.log)；允许构建访问模拟器服务后构建通过。

## 未通过的完整回归

`./Scripts/test.sh` 退出 65：304 项中 303 项通过，`ArtVisualRepairTests.testV01V02RenderedCompositionAtLandmarksJoinsAndTransitionOnBothCanvases` 未通过。Xcode 结果摘要明确报告 **“Test crashed with signal kill.”**，随后自动重启并执行其余 303 项；不能将重启后显示的 303 项通过当成整套通过。

单独复核同一渲染测试仍退出 65，执行时进程意外退出。根因未定；本轮没有修改 Swift、测试、运行时资源或 Xcode 工程来消除失败。记录为后续现有渲染测试稳定性待查项，不以重跑或删测掩盖。

- [完整回归日志](tests.log)
- [单项复核日志](render-recheck.log)

## 红线与当前范围

本轮仅归并用户已有收藏与说明，没有新增游戏文案、评分、死亡计数、警报色、动物字幕或留存机制。来源与待确认许可保留；候选未加入 App target，未作正式美术验收或设备性能结论。迁移当时 M5 仍为 active，人工切片、静音开关及真机门槛继续保留。

2026-11-08 补记：Paco 随后报告 H01–H06 真机通过，M5 已移入 `plans/done/`。这次归并记录不补设备明细或性能数字。H07 仍开放。
