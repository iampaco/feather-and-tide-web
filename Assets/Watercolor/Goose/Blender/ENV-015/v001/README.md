# ENV-015｜湖路岸边补给湿地

**v001 · needs_review · Blender 5.2.2 LTS**。制作规格书第 12 页、资源任务清单第 26 项，P0、S2。直接依赖 ENV-002 / 003 / 005 v001。参考样段使用 ENV-008 长湖和 ENV-010 山口，分别保留两条路线的方位。

[可编辑 Blender 母版](ENV-015_lakeside_rest.blend) · [LakesideRest GLB](ENV-015_LakesideRest.glb) · [材质来源与文件清单](asset_manifest.json) · [灰盒、材质与回导 QA](qa.json)

## 模块接口

- `LakesideRest` 根在模块本地原点，朝 +Y，Blender Z 向上，GLB 坐标映射 `(x,z,−y)`。地面覆盖 10 × 10 BU，边界每 0.625 BU 一点，陆边 Z = 0.00 BU，浅水 Z = −0.18 BU。`Ground`、`Water` 和 `Reeds` 三层合计 **6,446 三角面**，依次为 512 / 312 / 5,622。边界尺寸按地面计算，芦苇叶尖可越过地边约 0.17 BU。
- 在 ENV-008 中把根放在 `(4,10,0) BU`，替换原 `RestPatch`，覆盖湖路坐标 X −1 至 9、Y 5 至 15。样段剔除原占位地面 512 面。东、南、北侧匹配保留的 ENV-008 地面／法线／UV，相接西侧为平坦审阅地。新地面外沿保留长湖纹理相位，并沿 MAT-003 草滩、泥岸、浅滩和少量苔石烘焙渐变。浅水按 ENV-003 的贴底与床深 Alpha 方法生成。ENV-005 六款原型保留在可编辑散布组，固定种子 15026，导出冻结后的稀疏岸边轮廓。
- 母版含灰盒、独立导出和湖路材质审阅场景。母版审阅场景的雁与山口、湖岸、镜头及布光用于对照。出口与入口的审阅位置记录在 QA。

## 审阅证据

[灰盒横屏](graybox_before_fork.png) · [灰盒顶视](graybox_top.png) · [分岔前固定横屏](review_before_fork.png) · [离开湖面进岛](review_entry.png) · [离岛并回湖路](review_exit.png) · [十二雁顶视](review_top.png) · [浅滩近景](review_shore_detail.png) · [GLB 回导重拼](roundtrip_before_fork.png) · [固定跟随短片](review_lake_route.mp4)

- 灰盒先测，材质阶段复测。地边四组各 17 点，最大缝位和 UV 周期差均为 0，法线偏差小于 0.004°。法线比较容差 0.03°，位置和 UV 周期容差各 0.00001。36 条环向水线探针均检出浅水，浅滩水面约 **26.35 BU²**，水面压入干地最大约 0.0000002 BU，容差 0.000001 BU。
- 两段进出航线共测 **1,800 个**地面及芦苇探针，芦苇命中 0，CHR-001 中性翼展约 1.60 BU，静态几何最小地面净空 **0.183 BU**。左侧山口与右侧长湖出现在分岔前同一固定画幅。补给岛落脚区 25 个样点有 **23** 个可见，在 852 × 393 源画幅占约 **123 × 24 px**，以地平高度、浅水和偏西芦苇形成辨识轮廓。
- 12 只原尺寸雁使用 ANM-007 `Land_Mudflat` 第 81 帧，沿用 ENV-002 RestPatch 位置。66 对占位凸包最近间距 **0.108 BU**；24 只脚共 1,560 个足底样点，最近支持差最大 **0.00397 BU**，足底样点离地差最大 **0.00877 BU**，足下地面高出水位至少 **0.175 BU**。
- Blender 回导检查根节点、命名、轴向、缩放、三角面、顶点位置、UV、角点法线、材质和内嵌贴图 SHA-256。回导最大法线差约 **0.00569°**。在独立后台进程重新打开交付母版并重拼，从同一位置重新核对底床、接缝、航线以及十二雁落脚。原生和回导横屏逐像素复核，8 位通道平均差 0.00566，通道差超过 36 的像素为 0，新增近黑像素为 0。
- 机位依据现行 `ThirdPersonRig.graybox`、`PlayfieldView.swift` 与 ENV-001 预览函数，距离参数 180、俯仰参数 0.48 rad、纵向视场 50°、注视高度 6、领头雁根高 8，单位为游戏单位。喙尾 0.9900 BU 对齐 27.5 游戏单位供审阅取景。独立 Blender / FFmpeg 视频以相同固定机位分别取分岔前、进岛、回湖三个短段。

## 复现

用 Blender 5.2.2 LTS，在本目录运行脚本，各输出项使用独立空临时目录。

```sh
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-015_generate.py -- /absolute/path/to/empty-output
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-015_generate.py -- /absolute/path/to/empty-recheck --verify "$PWD"
blender -b --factory-startup -t 4 --python-exit-code 1 \
  --python ENV-015_motion.py -- "$PWD" /absolute/path/to/empty-motion --per-shot 12
```

可传 `--gray-only` 单独生成灰盒，视频脚本可传 `--ffmpeg` 指定工具路径。重拼记录见 [独立复验](recheck.json)，图像对比可用 [像素复查脚本](ENV-015_compare_previews.py) 复现（需 Pillow 和 NumPy），视频编码及解码结果见 [视频记录](motion_report.json)。

## 待验与待登记

- 待负责人复核分岔前辨识、浅水轮廓、芦苇疏密与 MAT-003 水彩表现。S2 实际进出路线、碰撞、动画、补给触发、持久化及重试，水面排序、USDZ、RealityKit 接入、iPhone / iPad 真机画面和性能待验。App 基线引用既有 iOS 27.2 记录，本轮未运行 App 构建或模拟器。
- `Assets/docs/asset-index.json` 待登记候选路径、母版、GLB、两张生成贴图、预览和 QA；`Assets/docs/asset-ledger.md`、`docs/references/asset-ledger.md` 待登记仓库内派生来源及审阅状态。
- `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 与 `plans/active/goose-preview-model-cleanup.md` 待回写 v001 候选位置、实际 ENV-008 插槽、验证摘要和运行时待验。

已对照项目红线清单。
