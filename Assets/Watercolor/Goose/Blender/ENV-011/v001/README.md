# ENV-011 山石与碎岩组三型

**v001 · needs_review · Blender 5.2.2 LTS**。规格书第 11 页，任务 JSON 中为 P1、执行序第 51 项，适用 S1、S2、S3、S5。三款石组均为静态装饰。

[可编辑母版](ENV-011_rock_sets.blend) · [资产清单与贴图来源](asset_manifest.json) · [QA](qa.json) · [生成与独立复验脚本](ENV-011_generate.py)

| 模块 | 造型 | X × Y × Z（BU） | 组件 / 三角面 | 导出 |
| --- | --- | --- | ---: | --- |
| Rock_Round | 偏心宽肩的大圆石，底部有缓倒角 | 1.877 × 1.610 × 0.830 | 1 / 120 | [GLB](ENV-011_Rock_Round.glb) |
| Rock_Long | 前后向狭长低岩，保留斜肩与薄沉积带 | 1.335 × 2.946 × 0.540 | 1 / 120 | [GLB](ENV-011_Rock_Long.glb) |
| PebbleCluster | 5 枚错落的扁石，间距使用独立实体控制 | 1.688 × 1.349 × 0.320 | 5 / 400 | [GLB](ENV-011_PebbleCluster.glb) |

网格都在本地原点，基面与枢轴同为 **Z=0**。Blender +Y 朝前、+Z 向上，glTF 映射为 `(x,z,-y)`，单位缩放为 1。将各款按独立物件使用，碎岩簇的五枚实体可按松散部件分离编辑。建议落点取接近水平的稳定地面。网格具有完整的封闭底面；GLB extras 记录 `role=decoration` 与 `generate_hard_collision=false` 供接入读取，实际碰撞行为由关卡和游戏工程决定。

## 审阅与验证

- [灰盒排列](graybox_lineup.png) · [灰盒固定后上方](graybox_fixed_rear.png)
- [材质排列](preview_lineup.png) · [起始固定后上方](preview_fixed_rear.png) · [接近固定后上方](preview_fixed_rear_approach.png)
- [回导排列](preview_glb_roundtrip.png) · [回导固定后上方](roundtrip_fixed_rear.png)

先用灰盒测底面、摆位和轮廓，然后烘焙暖灰棕、低饱和苔斑和细层理。三款共用一张 [512 × 512 不透明岩石贴图](textures/ft_goose_env_rock_sets_basecolor.png)，颜色来自 MAT-003 的 MountainRock、MossStone、MudBank 和本轮色板。贴图已打包进 Blender 母版及三个 GLB，源贴图按 MAT-003 清单核对 SHA-256，沿 U 圆柱接边的 RGB8 首末列相同。MAT-003 当前母版与其清单记录哈希都留在资产清单。

审阅使用现行 `ThirdPersonRig.graybox` 的 180、0.48 rad、50°，注视高度 6，领队高 8，画幅 852 × 393。CHR-001 领队以 0.9900 BU 对应 27.5 游戏单位作尺度参考。画面中浅乌灰雁的白头、黑颈纹与暖棕岩块分开。远处的碎岩聚为小色块。QA 的颜色比较取各目标射线确认可见的原始 PNG 像素，再比较各色通道的中位 RGB，结果只适用于本候选的灯光与机位。

11 组样段落点在 ENV-001 Flat 上用 271 条垂直接地点探针测试，最大高度差为 0.00000048 BU。样段石体距直线航道中心至少 1.274 BU。两张固定机位中最近三个石组距领队投影包围框至少 16.96 px，实测可见中位 RGB8 的最小欧氏距离为 32.47。

GLB 逐件比对根点和缩放、轴向、三角面与绕序、点位置、UV、法线、材质和内嵌贴图，并用回导网格重摆审阅样段。独立复验从交付目录重开 Blender 母版和全部三个 GLB，核对几何和回导统计。位置最大差为 0 BU，法线最大差为 0.00643°，UV 最大差约 0.000000015。

## 复现

使用 Blender 5.2.2 LTS。脚本只读相邻的项目资产，输出请指定独立空临时目录。

```sh
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-011_generate.py -- /absolute/path/to/empty-output
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-011_generate.py -- /absolute/path/to/empty-recheck --verify /absolute/path/to/ENV-011/v001
```

## 待验与共用文件待登记

- 待负责人复核大圆石、狭长岩和碎石簇在正式场景的密度和颜色；待 USDZ / RealityKit、地形摆放与碰撞、iPhone / iPad 真机。已对照设计红线，App 沿用既有 iOS 27.2 模拟器构建与 340 项测试记录。
- `Assets/docs/asset-index.json` 待登记母版、三个 GLB、QA、候选状态和相对路径。
- `Assets/docs/asset-ledger.md` 与 `docs/references/asset-ledger.md` 待登记原创网格、MAT-003 输入及派生贴图、审阅证据和正式导出验收路径。
- `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 与 `plans/active/goose-preview-model-cleanup.md` 待补变体、交付路径、实测证据与运行时项目。
