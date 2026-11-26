# FX-004｜晨雾与低洼薄雾

**v001 · needs_review · Blender 5.2.2 LTS**。规格书第 14 页，任务清单执行顺序第 33 项。P0，S0，依赖 ENV-018/v001。

[可编辑 Blender 母版](FX-004_Fog_Start.blend) · [Fog_Start GLB](FX-004_Fog_Start.glb) · [资产清单](asset_manifest.json) · [QA 实测](qa.json)

[固定后上方短片](preview_fixed_rear.mp4) · [默认](preview_fixed_rear_default.png) · [减弱](preview_fixed_rear_reduced.png) · [关闭](preview_fixed_rear_off.png) · [位移关键帧](preview_fixed_rear_drift.png) · [斜俯布局](preview_layout.png) · [GLB 回导](preview_glb_roundtrip.png) · [回导比较基准](roundtrip_native_reference.png)

[固定机位灰盒](graybox_fixed_rear.png) · [斜俯灰盒](graybox_layout.png) · [生成与回验脚本](FX-004_generate.py) · [视频与交付封装脚本](FX-004_finalize.py)

## 形体、材质与依赖

先用两侧各三张卡片验证分层，再套用蓝灰贴地雾、暖白岸雾和远侧柔纱。三张独立 512 × 512 直通 RGBA 贴图由 ENV-018 母版里的 MistLow、CloudPatch 和 CloudStreak 内嵌贴图重绘，来源哈希与磁盘及上游清单一致。雾边 Alpha 归零。复用了 ENV-018 的 CloudPatch 与 CloudStreak 几何、贴图作为审阅远层。审阅以程序化湿地水色保留明亮开口，铺设 ENV-004 芦苇、ENV-009 远山与 CHR-001 静态角色用于看景。审阅地形是该候选的取景样段，最终 S0 布局、动作和玩家输入需在运行时复验。

母版在 `FX-004 | S0 fixed rear review` 场景打开。编辑集合 `Fog_Start | editable runtime cards` 中 6 张雾卡，合计 96 三角面。枢轴在起飞参考原点，比例为 1。Blender +Y 向前、+Z 向上，GLB 按 `(x,z,-y)` 转换。GLB 含 Fog_Start 根节点、6 张静态卡片和内嵌三张贴图，材质为双面、BLEND、CLAMP_TO_EDGE、KHR_materials_unlit。远层摆位见清单，供与 ENV-018 独立组装。雾卡为纯视觉对象。

## 编辑与接入

选择母版的 `Fog_Start` 空物体，在 Object Properties 里的 Custom Properties 调节雾层。时间轴以 12 fps 播放。Fog_Start 内的各卡片保留 `base_x_BU`、`amplitude_BU` 和 `phase_turns`，可改漂移形态和初始相位。地平线保持原有固定第三人称取景设定。Blender 材质增益和位移由驱动器控制。GLB 静态卡的生成程序先导出纹理原始 Alpha 和卡片基准位置，然后安装 Blender 驱动器。

| Blender 属性 | 运行时输入 | 值域 |
| --- | --- | --- |
| `opacity_strength` | `opacityStrength` | 0–1，乘直通贴图 Alpha |
| `motion_strength` | `motionStrength` | 0–1，乘每张卡的横向漂移幅度 |
| `period_seconds` | `periodSeconds` | 1–60 秒，默认 12 秒 |
| `phase_turns` | `phaseTurns` | 相位偏移 0–1 圈 |
| 时间轴 | `elapsedSeconds` | 由场景传入连续时间 |

运行时按起飞点和朝向摆置根节点。卡片在本地 X 轴以正弦往返。默认 Alpha 和位移均为 1，减弱均为 0.35，关闭均为 0。ENV-018 远层可共用透明度设置，摆位及雾退场时机由场景提供。碰撞、触发与摇杆语义由 App 保持。

## 离线回验

- 独立后台 Blender 重开实际交付母版、回导最终 GLB，逐张核对枢轴、缩放、朝向、三角面、UV、材质与内嵌贴图字节。在静态基准姿态渲染同一固定机位，回导比对平均每通道绝对差约 0.144/255，约 0.236% 的像素至少一个通道相差 5/255。最大局部差 12/255，集中在雾带区域。
- 复现源码机位距离 180、俯仰参数 0.48 rad、50° 垂直 FOV、注视点高度 6 与领队高度 8。按主雁喙尾 0.9900 BU 对齐 27.5 游戏单位。三个领队/相机姿态和 16 个漂移相位下，每档测 2,160 条起步、3,456 条开口和 18,432 条摇杆可视范围射线。三个位置采样含轻微偏航和抬升。三套安全区边距是审阅取样。摇杆视觉范围含 72 px 行程与 23 px 圆点半径。三档上述被测位置的合成 Alpha 均为 0；岸侧对照点的最大合成 Alpha 为默认约 0.461、减弱约 0.161。固定后上方材质帧的中部开口，按 QA 取样平均亮度比两侧高约 18.2/255。首次玩家的起飞方向辨识待试玩验证。
- 重开后分别在默认、减弱和关闭检查子节点 X 位移与材质增益。默认抽样最大位移约 1.290 BU、减弱 0.451 BU、关闭约 0。12 秒后回到同一姿态。4 秒无声视频用实际交付母版重新渲染 48 帧，帧源 852 × 393，H.264 底部补一行至 852 × 394，全部解码通过。

## 复现

在候选目录用 Blender 5.2.2 LTS、Python 3、Pillow、NumPy 和 FFmpeg，指定存在或可创建的空目录。由临时目录的候选开始复现时，可执行首条命令生成母版与导出，再复制 README 和两份脚本，随后独立验证和封装。

```sh
blender -b --factory-startup -t 3 --python-exit-code 1 \
  --python FX-004_generate.py -- /tmp/ft-fog-build
cp README.md FX-004_generate.py FX-004_finalize.py /tmp/ft-fog-build/
blender -b --factory-startup -t 3 --python-exit-code 1 \
  --python FX-004_generate.py -- /tmp/ft-fog-verify --verify /tmp/ft-fog-build --video
python3 FX-004_finalize.py /tmp/ft-fog-build /tmp/ft-fog-build /tmp/ft-fog-verify
```

## 待验与登记

待 Paco 复核色调、漂速及开口辨识。待 USDZ、RealityKit 透明排序与深度、S0 最终摆位、运行时可访问性、摇杆实际合成与首次玩家试玩。iPhone／iPad 显示、触控和性能待真机验证。既有 App 灰盒基线为 iPhone 18 Pro（iOS 27.2）构建及 340 项测试通过，本轮资产审阅沿用该记录。已对照设计红线。

- `Assets/docs/asset-index.json` 待补 v001、项目根相对路径、母版、GLB、贴图与 QA。
- `Assets/docs/asset-ledger.md` 与 `docs/references/asset-ledger.md` 待登记项目内 ENV-018 来源、Alpha 再绘与许可、候选证据、状态及后续运行时导出映射。
- `完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json` 与 `plans/active/goose-preview-model-cleanup.md` 待回写 Fog_Start、验证、候选状态及待验。
