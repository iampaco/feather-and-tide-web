# ENV-014 检查点 A：芦苇洲

**v001 · needs_review · Blender 5.2.2 LTS**。规格书第 12 页，清单第 25 项，S1 / S2。直接依赖 ENV-002、ENV-003、ENV-005。采用现行固定后上方机位，从同一个检查点看山口、湖面和右侧休整岸。

[可编辑母版](ENV-014_checkpoint_a.blend) · [CheckpointA_Visual GLB](ENV-014_CheckpointA_Visual.glb) · [资产清单、贴图来源和文件哈希](asset_manifest.json) · [QA 实测](qa.json) · [生成与回导脚本](ENV-014_generate.py)

## 场景与导出

- `ENV-014 | Tile layout and live reeds` 保留 4 × 3 地形铺装、可编辑盆地和活的 Geometry Nodes 芦苇散布。复用 ENV-002 泥滩、RestPatch 和 ENV-003 水面，主盆地按 ENV-003 方法另烘焙床深 Alpha。ENV-005 的六款芦苇、顺岸密度及避让节点用于低风场景，新种子为 14025。
- `ENV-014 | Baked CheckpointA_Visual` 的根节点下有地面、水和冻结芦苇三个可单独编辑的层。资产覆盖 X −25 到 15 BU、Y −25 到 5 BU，参考水位 Z −0.18 BU。根节点在检查点 `(0,0,0)`，方向为 +Y，Blender XYZ 转 GLB 为 `(x,z,-y)`。山口、长湖、远山、审阅雁、镜头和审阅标记位于 Blender 取景场景。
- 以右岸 RestPatch 作为干地休整面，入洲航线沿开阔主水面进入泥滩与停歇区。母版中的 `Checkpoint_A`、`Dry_Pad`、`Pass_Exit` 和 `Lake_Exit` 是审阅用的布局参照。

## 灰盒、材质与取景

[灰盒进洲](graybox_fixed_rear_incoming.png) · [灰盒停歇](graybox_fixed_rear_rest.png) · [灰盒顶视](graybox_top.png) · [材质进洲](preview_fixed_rear_incoming.png) · [12 只停歇](preview_fixed_rear_rest.png) · [全景顶视](preview_top.png) · [检查点 A 同框](preview_fixed_rear_fork.png) · [回导停歇](roundtrip_fixed_rear_rest.png) · [回导顶视](roundtrip_top.png)

[固定跟随进洲短片](preview_checkpoint_motion.mp4) · [短片复现脚本](ENV-014_motion_preview.py)

从灰盒起核对镜头、各层、水岸和站位。固定相机按现行 `ThirdPersonRig.graybox` 使用 180 距离参数、0.48 rad 俯仰参数、50° 纵向视角、注视高度 6。领队根高 8，源横屏为 852 × 393，采用 CHR-001 的既有审阅换算。以微暖日光、低幅芦苇倾角和浅水过渡区构成水陆地标。审阅同框使用实际 ENV-008、ENV-009、ENV-010 母版，并以水陆边界限定审阅拼装区。

- 17 道地块陆边对接，中心盆地水面 **54.84 BU²**，与各贴合池的高度、干地探针与纹理 Alpha 均可复验。水缘源几何有低模分面。
- 136 株芦苇复现同一种子，网格离保留区最少约 0.39 BU。入洲、离洲三条横向位置对机身及两翼共测 **1,494 处**，芦苇无命中，静态雁最低地形净空约 **0.183 BU**。
- ANM-007 的第 81 帧收翼姿态，12 只原尺寸雁的 66 对占位凸包均分离，最小 **0.108 BU**。最近足底接点的最大离地差为 **0.00842 BU**，在既有 0.009 BU 容差内。12 只均进入固定后上方停歇画幅。
- 同一检查点 A，山口 13 条视线、湖面 9 条、补给岸 9 条均通过。双路线视觉方位可辨；资源补给、飞行动画和重试恢复由 S1 / S2 运行时验证。
- 回导复查三个层、原点与坐标、几何和 UV、角点法线、材质和内嵌贴图。水陆覆盖和进出走廊在回导件重拼后复测，并从实际交付目录独立重开验证。进洲短片使用 24 个 Blender 源帧，已通过 H.264 解码。

## 复现

从此素材目录运行 Blender 5.2.2 LTS，输出到独立空目录。脚本只读本项目相邻素材。

```sh
blender -b --factory-startup -t 5 --python-exit-code 1 \
  --python ENV-014_generate.py -- /absolute/path/to/empty-output
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-014_generate.py -- /absolute/path/to/empty-recheck --verify /absolute/path/to/ENV-014/v001
```

进洲视频用相同后台参数运行 `ENV-014_motion_preview.py`，传入独立空输出目录和 `--frames 24`，并提供 ffmpeg。

## 待验与待登记

- 待负责人复核材质、密度与地标辨识。待 S1 / S2 的路线选择、落脚和恢复动作、补给容量、重试复位、碰撞、水面排序、USDZ / RealityKit 与 iPhone / iPad 真机。App 基线沿用已有 iOS 27.2 构建和 340 项测试记录。
- `Assets/docs/asset-index.json` 待加素材相对路径、母版、GLB、贴图清单、QA 和候选状态。
- `Assets/docs/asset-ledger.md`、`docs/references/asset-ledger.md` 待记录项目内素材、生成纹理、场景审阅证据与正式接入后路径。
- `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 与 `plans/active/goose-preview-model-cleanup.md` 待记录候选交付、固定镜头证据和下一轮待验。

已对照设计红线。清单下一项为 **ENV-015｜湖路岸边补给湿地**。
