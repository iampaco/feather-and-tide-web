# ENV-016 风电场下方保护湿地

**v001 · needs_review · Blender 5.2.2 LTS**。规格书第 12 页，清单执行顺序第 40 项，P0 / S4。直接依赖 ENV-002、ENV-003、ENV-005、STR-002。

[可编辑母版](ENV-016_protected_marsh.blend) · [ProtectedMarsh GLB](ENV-016_ProtectedMarsh.glb) · [资产清单与贴图来源](asset_manifest.json) · [QA](qa.json) · [生成与验证脚本](ENV-016_generate.py)

## 场景接口

- 地形由 4 × 5 个 10 BU 方格组成。根枢轴在中央 RestPatch 的陆地基准 `(0,0,0)`，Blender X 范围 −25 到 15 BU、Y 范围 −25 到 25 BU，+Y 为绕行前进方向，参考水位 Z = −0.18 BU。沿用 ENV-001 的分段网格、L 型陆接边及整数 UV 相位。Blender XYZ 对应 GLB `(x,z,-y)`。
- StartMudflat 标记开阔入口，中央 RestPatch 承接 12 只落脚。两块新塑造的缓岸池与两片复用的 ENV-003 浅水构成四处水陆过渡，205 株 ENV-005 芦苇分为六款，沿外圈与浅池岸缘散布。飞行走廊预留 19.6 BU 的连续植物避让宽度。
- 母版包含可编辑的分块地形和 Geometry Nodes、固定后上方审阅场景、单独可选的地面／水面／芦苇烘焙层。GLB 根为 `ProtectedMarsh`，其下为 `ProtectedMarsh_Ground`、`ProtectedMarsh_Water`、`ProtectedMarsh_Reeds`。
- 审阅风机按 `PlayfieldView.swift` 的灰盒尺寸搭建。局部轴心 `(18.6,9.2)` BU 是候选布局选择，圆由 `GrayboxPlaces.swift` 的 78 游戏单位半径换算为 2.808 BU。褐灰圆、路径刻度、标记点、审阅雁和相机均位于母版的独立审阅场景。正式 STR-002 的整组布设和 FX-010 的扫掠表现待联合验证。

## 审阅照片与短片

[灰盒进场](graybox_fixed_rear_approach.png) · [灰盒落脚](graybox_fixed_rear_landing.png) · [灰盒顶视](graybox_top.png)

[材质进场](preview_fixed_rear_approach.png) · [12 只落脚](preview_fixed_rear_landing.png) · [出场](preview_fixed_rear_exit.png) · [顶视队形与扫掠边界](preview_top.png) · [固定跟随绕行短片](preview_fixed_rear_egress.mp4)

[GLB 回导落脚](roundtrip_fixed_rear_landing.png) · [GLB 回导顶视](roundtrip_top.png) · [独立回导报告](recheck.json)

先验证灰盒的陆边、落脚和绕行，再审阅 MAT-003 草滩／泥岸／浅滩过渡，水面沿用 ENV-003 和 MAT-004 候选纹理。母版打包贴图，GLB 内嵌 PNG。新增两张 RGBA 水面图对应东西浅池，文件和源图 SHA-256 见清单。

固定相机采用现行 180 游戏单位距离、0.48 rad 俯仰、50° 纵向视角、6 游戏单位注视高和 852 × 393 横屏审阅画幅。CHR-001 喙尾 0.9900 BU 对齐 27.5 游戏单位仅为审阅换算。短片以静态原尺寸雁姿记录绕行，使用 24 个 Blender 源帧并通过 H.264 解码。翼侧和后排超出固定画幅时，可在顶视核对完整队形。

## 测量结果

- 31 道内部对接各采样 17 个边点。最大位置差和 UV 相位误差均为 0，最大法线差 0.00511°。位置与相位容差均 0.00001，法线容差 0.03°。另在南北接口拼接 ENV-001 Flat 验证 6 道外接缝。
- 四片水面合计 114.2964 BU²。回导后的水面顶点与三角中心通过地表探针检查，最大干地侵入约 0.00000065 BU，容差 0.000001 BU。地面、水面和芦苇包围盒到扫掠边各有约 0.792、3.890、0.496 BU 的保守间隔。
- 领队沿 X = 2 BU 走中段 Y = −14 至 +22 BU，外接验证延伸到 −28 至 +35 BU。采用现行槽位计算与 36 游戏单位收拢排距。按 1+11 只的源轮廓向外扩 0.8194 BU 后，所有连续槽位轨迹到扫掠区的最小间隔为 6.4926 BU。队形翼尖间宽 15.8564 BU。中段和外接线路各采样 121 个站位，每段身体与两翼合计 4,356 条地表探针、4,356 条芦苇探针，芦苇零命中。领队与跟随者用源码的 8／6 游戏单位高度，最低离地约 0.1110 BU，阈值 0.08 BU。起点所有雁距南边至少 2.1806 BU，终点最后一只雁完整越过北边 1.4046 BU。
- ANM-007 第 81 帧收翼姿态用于站姿审核。12 只原尺寸雁的 66 对投影凸包全部分离，最小 0.10815 BU，阈值为 0.03 BU。最近足底接点的最大离地差 0.008419 BU，沿用 0.009 BU 容差。24 只脚的 1,560 个探针中，地面最少高于水位 0.17045 BU。12 只雁都在 852 × 393 的落脚画幅内，单只投影约宽 35–58 像素。
- 回导为 37,066 个三角面。核对根与三个层名、原点与单位变换、XYZ 边界、三角逐角位置和 UV、角点法线、11 个材质绑定和内嵌 PNG 字节。最大角点法线差 0.02471°，容差 0.12°。四个水面材质沿用上游颜色与透明度节点，导出器对共用采样器发出提示。回导件复跑水陆覆盖和完整队形绕行。

## 复现

从本素材目录运行 Blender 5.2.2 LTS，三次均传入不同的空目录。短片生成另用本机 ffmpeg。

```sh
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-016_generate.py -- /absolute/path/to/empty-build
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-016_generate.py -- /absolute/path/to/empty-recheck --verify /absolute/path/to/ENV-016/v001
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-016_generate.py -- /absolute/path/to/empty-motion --motion /absolute/path/to/ENV-016/v001
```

## 待验与登记

- 待负责人复核材质、浅水轮廓、湿地与绕行方向在手机上的辨识。实景拼接待 STR-002 正式方案与 FX-010 联合对照。S4 的实际补给、落脚触发、队形变化、碰撞、退出逻辑及水面透明排序待运行时验证。USDZ、RealityKit 接入和 iPhone／iPad 真机亦待验证。
- App 基线引用已有 iPhone 18 Pro／iOS 27.2 构建与 340 项测试记录。本轮在独立 Blender 后台进程验资产，App 脚本未重跑。已对照设计红线。
- `Assets/docs/asset-index.json` 待填相对路径、母版、GLB、清单和 QA。
- `Assets/docs/asset-ledger.md` 和 `docs/references/asset-ledger.md` 待登记项目内来源、派生纹理、审阅状态与接入后路径。
- `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 和 `plans/active/goose-preview-model-cleanup.md` 待登记候选、固定机位证据和 S4 待验项。
