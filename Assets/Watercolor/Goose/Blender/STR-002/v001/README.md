# STR-002 弧形风电场布局预设

**v001 · needs_review · Blender 5.2.2 LTS**。规格书第 13 页，制作清单第 39 项，P0 / S4。直接依赖 STR-001 与 FX-010。FX-010 第 38 项仍待制作，规格见第 16 页。

[可编辑母版](STR-002_CurvedFarm_Layout.blend) · [最终阵列 GLB](STR-002_CurvedFarm_Layout.glb) · [审阅轮廓 GLB](STR-002_RotorFootprint_Review.glb) · [可编辑布局与扫掠数据](farm_layout.json) · [清单及素材映射](asset_manifest.json) · [QA](qa.json) · [复跑脚本](STR-002_generate.py)

[灰盒顶视](graybox_top.png) · [灰盒进场](graybox_fixed_rear.png) · [材质顶视](preview_top.png) · 雾层 [默认](preview_fog_default.png) / [减弱](preview_fog_reduced.png) / [关闭](preview_fog_off.png) · [12 只落脚](preview_wetland_rest.png) · [出场](preview_egress.png) · [固定跟随短片](preview_fixed_rear_flight.mp4) · GLB 重拼 [顶视](roundtrip_wetland_array_top.png) / [固定后上方](roundtrip_fixed_rear.png)

## 布局与源码映射

- 七台 STR-001 共享八个网格，从南到北布在 ENV-016 东侧。Blender 地面中心 X = 18.30–20.90 BU、Y = −3.00–21.45 BU，场根与 40 × 50 BU 湿地根都在 `(0,0,0)`。各台中心、方向、等比缩放和叶轮初相记录在 JSON。导出七路错相旋转为一个 9 秒 GLB 动画。
- 审阅比例为 0.036 BU / 游戏单位，由 CHR-001 喙尾 0.9900 BU 与 27.5 游戏单位对齐。Blender +Y 为行进方向，GLB 坐标为 `(x,z,-y)`。以 T04 `(18.6,9.2)` BU 对齐出生点相对坐标 `(920,-10)`。候选 XY = T04 XY + 0.036 ×（出生点相对游戏坐标 − `(920,-10)`）。各台逆算结果在 QA。灰盒保护带中心 `(920,-78)`、尺寸 `200 × 52` 对应此映射下 `(18.6,6.752)` BU、`7.2 × 1.872` BU。实际 ENV-016 落脚区采用其独立母版坐标。
- 现行 `TraceOverlay.swift` 用领队 XY 到出生点平移后的单圆心距离 ≤ 78 判定进入。首次跨入产生提示。旅程模式在圈内可散乱并推开路径，保护带独立判定。RealityKit 的 `PlayfieldView.swift` 仍绘制单台几何代理，塔身 `16 × 70 × 16` 游戏单位、叶片横条长度 86、中心高 68。候选把相同半径复制为七个基座中心的地面圆，半径 2.808 BU，独立于实例视觉缩放。最终的碰撞、触发和保护区采用游戏的 Zone。
- 候选轮廓从同一份 JSON 取圆心、半径，求圆并集外边界并离散成一圈灰紫边线和浅填色。六段相邻圆均重叠，轴向重叠最小 1.322 BU，公共弦最小 3.619 BU。外边界闭合，弧段接合误差小于 0.000002 BU，折线弦中点误差小于 0.000062 BU。最小叶尖地面包络余量 0.883 BU。正式 FX-010 及约 3 秒预警时间待联验。

## 航道与湿地

| 离线测量 | 实测 |
| --- | ---: |
| 完整 V 形，领队加 11 只原尺寸 CHR-001，含翼尖 | 15.856 BU |
| 2 倍要求 | 31.713 BU |
| 最窄净宽，西侧预留线 X = −18.6 到扫掠外缘 | **34.092 BU** |
| 最窄处与实测比值 | T05，Y = 13.280 BU，**2.150 倍** |
| 余量与验收容差 | 2.379 BU；距离 0.005 BU，比值 0.01 |
| 入场 / 湿地中段 / 出场，整队到扫掠最小间隔 | 17.515 / **6.193** / 6.445 BU |
| 12 只落脚范围保守外包框到扫掠 | 15.046 BU |
| 整片湿地地面 / 水面 / 芦苇包围盒到扫掠 | 0.492 / 2.014 / 0.196 BU |

采用 `FlockFormation.swift` 的交替 V 形槽位和 `FlockTuning.swift` 的收拢排距 36 游戏单位，默认灰盒配置为 8 名跟随者，S4 审阅按要求使用 11 名。复用 ENV-016 的 X = 2 BU 航线，接通 Y = −28 至 +35 BU，入口和出口为 Y = −14 / +22 BU。每只雁的连续槽位用 0.8194 BU 全尺寸中立姿态包围圆扩展。离场时最后一只全身已越过北接缝至少 1.405 BU。飞行最低离地 0.111 BU，121 个站位共检查 4,356 个中心／翼尖地形点和 4,356 条芦苇探针。回导阵列 GLB 与实际 ENV-016 GLB 后从南到北重拼湿地，复查六道接口、落脚、整队轨迹及几何。净宽、队形宽、落脚间隔和整队最近距离均与源样段一致。早期单风机的 6.49 BU 属于旧样段。

## 取景与复跑

镜头沿用现行后上方 180 游戏单位、0.48 rad、纵向 50°、注视基高 6，源帧为 852 × 393。远景接近图采用 +48 游戏单位抬升和略朝阵列的 0.28 rad 航向取景，短片沿 +Y 跟随，落脚及出场图使用基准高度。完整 V 形和全部扫掠轮廓可看技术顶视。近处的阵列逐渐移出前方固定画幅。

复用 ENV-018 的三类原始卡片、12 秒审阅漂移及默认 100%、减弱 35%、关闭 0% 的样式。每档在 9 个沿线机位、8 个漂移相位检测 11,887 条可见目标视线，扫掠边、航路和风机抽样点的最大雾合成 Alpha 均为 0，正控制约 0.222。按相同进场渲染与关闭档比较，默认有 1,292 像素相差至少 5/255，减弱有 51 像素。七台轮毂均在至少一个抽样画幅内，每台在最佳抽样画幅中轮毂距基座的投影约 47–62 px。每档均有公开对照帧。短片保留 48 个源帧，编码尺寸底部补一行至 852 × 394，H.264 全解码通过。

在本目录用不同的空输出目录和 PATH 中的 ffmpeg / ffprobe 运行。编辑 `farm_layout.json` 后重新生成以同步资产、轮廓与 QA。

```sh
blender -b --factory-startup -t 7 --python-exit-code 1 \
  --python STR-002_generate.py -- /tmp/ft-str002-build
blender -b --factory-startup -t 6 --python-exit-code 1 \
  --python STR-002_generate.py -- /tmp/ft-str002-verify --verify "$PWD"
```

## 待验与待登记

- 待负责人复核材质、阵列轮廓、雾层在小屏上的对比度。待 FX-010 正式视觉、Zone 边界、FX-011 预警时间、运行时补给、触发、碰撞、飞行动画和队形变化、USDZ / RealityKit / App 接入、iPhone / iPad 真机。App 引用已有 iOS 27.2 构建和 340 项通过的灰盒测试基线。已对照红线清单。
- `Assets/docs/asset-index.json` 待登记母版、阵列 GLB、轮廓 GLB、布局与证据相对路径。
- `Assets/docs/asset-ledger.md` 和 `docs/references/asset-ledger.md` 待记录已有材质、雾层与湿地依赖映射、候选状态和接入路径。
- `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 第 39 项与 `plans/active/goose-preview-model-cleanup.md` 待登记候选、回导和湿地证据、FX-010 与真机依赖。
