# 羽与潮 / Feather & Tide 素材库

`Assets/` 是项目指定素材库，统一管理原稿、候选、参考与制作说明。2026-11-08（Asia/Shanghai）已归并原游戏素材包；原文件名与 Asset ID 保留。

先读[素材库使用约定](docs/素材库使用约定.md)，再读[素材说明与接入指南](docs/素材说明与接入指南.md)（[English index](docs/ASSET_GUIDE_FOR_AGENTS.md)），按[素材索引](docs/asset-index.json)与[候选素材台账](docs/asset-ledger.md)取图。索引路径均相对**项目根目录**。

## 目录

```text
Assets/
  README.md
  Watercolor/
    Goose/       # Characters / Scenes / Traces / UI / VFX / Palette
    Whale/
    Deer/
    Shared/
  refs/          # 风格与构图参考
  Graybox/
  Audio/         # 保留既有分类及原包占位目录
  UI/
  Haptics/
  docs/          # 使用约定、指南、台账、索引和迁移记录
```

## 当前候选库存

| 类别 | 数量 | 当前状态 |
| --- | ---: | --- |
| 雁线 PNG | 89 | 原稿 / 待加工 |
| 鲸线 PNG | 50 | 后续章节候选 |
| 鹿线 PNG | 58 | 后续章节候选 |
| 共享 PNG | 5 | 光晕与粒子候选 |
| 色板 JSON | 6 | 待对照已选风格与现有系统适配 |
| JPG 参考 | 9 | 含 2 张本次补录的构图 / 风格参考 |

原批次风格板为 `SB-2026-11-07-v1`；它是来源标记。当前湿地基准继续以[已选 V07 方向](../docs/references/m5-style/v07-layers/README.md)及 active 计划为准。

## 使用状态

- 全部 202 张 PNG 均无有效透明区域；其中部分具有 RGBA 通道，但 alpha 全为不透明。角色、叠加图和粒子需按用途抠透。
- 循环帧未像素对齐；需统一锚点、身体比例和动作相位。
- 场景多为完整构图，非生产级无缝图层；需检查拆层、地平线和接缝。部分图片有烧录文字，需清理。
- Paco 已于 2026-11-08 在当前对话确认本批 Grok Imagine 素材用于本游戏的权利，并授权加工与接入；依据为负责人声明，服务条款证据待其归档，不据此宣称普遍商用或免署名。
- 本批原包没有音频或触觉文件。项目已经使用的声音仍在运行时资源目录中。

当前[斑头雁单线 Demo](../plans/active/goose-linear-demo.md)优先复用湿地、浅岸、风机外围及落脚盆地的现有资源。山口、海岸的正式美术扩展依 H07，鲸鹿随对应计划处理。素材库不整体打包进入 App，验收后的导出按项目 `ft_…` 命名放入 `Sources/FeatherTide/Resources/`，登记[正式素材台账](../docs/references/asset-ledger.md)。

本轮按用户授权加工并技术接入的湿地、雁姿态、痕迹和羽毛，见 [接入报告](../docs/references/assets-integration-2026-11-08.md)。加工图集及完整提示词保存在 [Processed/Goose/2026-11-08](Processed/Goose/2026-11-08/README.md)，原稿保留不变。技术合成不代替人工美术终审和真机验证。

## 迁移与历史资料

[迁移清单](docs/library-migration-2026-11-08.json)记录全部旧新路径、文件哈希及本地备份；[迁移验证](docs/migration-validation-2026-11-08/README.md)记录构建与回归结果。[原分卷恢复说明](docs/如何合并分卷.md)仅用于历史归档恢复。既有风格研究、生产配方与验证证据由[使用约定](docs/素材库使用约定.md)链接，继续保留可追踪来源。
