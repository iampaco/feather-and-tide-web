# ENV-003 湿地浅水面

**v001 · needs_review · Blender 5.2.2 LTS · 2026-11-14**。规格书第 9 页，任务清单第 17 项。直接依赖 ENV-002/v001、MAT-004/v001。

[可编辑 Blender 母版](ENV-003_wetland_water.blend) · [资产清单](asset_manifest.json) · [QA 实测](qa.json) · [生成与复验脚本](ENV-003_generate.py)

独立 GLB　[Channel](ENV-003_Channel.glb) · [ShallowPool_RestPatch](ENV-003_ShallowPool_RestPatch.glb) · [ShallowPool_StartMudflat](ENV-003_ShallowPool_StartMudflat.glb)


[灰盒顶视](graybox_top.png) · [水岸顶视](preview_top.png) · [浅洼近景](preview_shore_detail.png) · [固定后上方横屏](preview_fixed_rear.png) · [GLB 回导重拼](preview_glb_roundtrip_top.png)

两个 ShallowPool 分别贴合 StartMudflat、RestPatch。Channel 贴合 ReedIslet 的浅沟和东侧水面。所有导出沿用 ENV-002 中心枢轴，位于 Z = −0.18 BU。按地形三角面裁切水平几何，水线边缘与床面高度交于同处。导出时 Blender XYZ 映射为 glTF `(x,z,-y)`。

| 导出 | 三角面 | 水下覆盖面积 |
| --- | ---: | ---: |
| ShallowPool_StartMudflat | 42 | 2.4700 BU² |
| ShallowPool_RestPatch | 72 | 5.9912 BU² |
| Channel | 296 | 38.5652 BU² |

以 MAT-004 的经哈希核对的磁盘 PNG 提取水彩色带和纸纹，按实际地形深度重烘焙三张 **512 × 512 直通 RGBA**。岸线从 Alpha 0 起，沿 0.165 BU 深度渐入；深处偏灰蓝。Channel 南北接边网格采样与首末 RGBA 行逐字节一致。GLB 使用 BLEND，贴图内嵌与附带 PNG 一致。导出和独立回导后复查轴向、面积、水位、轮廓和 UV，水面探针最大越入干地误差小于 0.000001 BU。实际水位边缘与水下床面材质的分面均可在近景查看。浅洼的远景细节会随画幅缩小。

MAT-004 当前 .blend 和其清单记录的哈希不同。资产清单记录实读 .blend 哈希，色带来自已哈希核对的磁盘 PNG。GLB 的排序、真实天空反射方案、FX-006 波纹及运行时岸线接入留待后续。固定机位沿用 180 / 0.48 rad / 50°，用于取景的主雁比例为 0.9900 BU 对应 27.5 游戏单位。


## 复现

输出到独立空目录。生成脚本只读素材库内的输入。使用 Blender 5.2.2 LTS。

```sh
blender --background --factory-startup -t 6 --python-exit-code 1   --python ENV-003_generate.py -- /absolute/path/to/empty-output
blender --background --factory-startup -t 4 --python-exit-code 1   --python ENV-003_generate.py -- /absolute/path/to/empty-recheck --verify /absolute/path/to/ENV-003/v001
```

## 共用文件待登记

- `Assets/docs/asset-index.json` 增补候选母版、GLB、QA、贴图映射、依赖及 `needs_review`。
- `Assets/docs/asset-ledger.md` 与 `docs/references/asset-ledger.md` 增补原创几何及项目内材质来源、处理记录、审阅证据和待验项。运行时导出路径在接入后登记。
- `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 写回变体、交付路径与候选状态。
- `plans/active/goose-preview-model-cleanup.md` 补 Blender 验证记录与待验项。iPhone 18 Pro（iOS 27.2）模拟器构建和 340 项测试沿用现有记录。

本轮已对照设计红线。待负责人复核观感、USDZ / RealityKit 接入及 iPhone / iPad 真机验证。
