# LVL-S0 晨雾湿地起飞

**v001 · needs_review · Blender 5.2.2 LTS**。规格书第 17 页关卡组装，任务执行顺序第 42 项，变体 `S0_StartWetland`。

[可编辑 Blender 母版](LVL-S0_S0_StartWetland.blend) · [湿地场景 GLB](LVL-S0_S0_StartWetland.glb) · [可选远山 GLB](LVL-S0_S0_StartWetland_Backdrop.glb) · [12 雁动作审阅 GLB](LVL-S0_S0_StartWetland_ReviewFlock.glb) · [布局与引擎接口](s0_layout.json) · [资产清单](asset_manifest.json) · [独立回验 QA](qa.json)

- 灰盒：[固定机位](graybox_fixed_rear.png) · [起飞区顶视](graybox_top.png)
- 材质：[起飞](preview_fixed_rear_takeoff.png) · [滑翔](preview_fixed_rear_glide.png) · [左盘旋](preview_fixed_rear_circle.png) · [出口](preview_fixed_rear_fog_exit.png) · [全队顶视](preview_top_flock.png)
- 审阅：[14 秒固定第三人称起飞、滑翔、左盘旋与通过雾线](preview_fixed_rear.mp4)
- GLB 回导：[起飞](roundtrip_fixed_rear_takeoff.png) · [滑翔](roundtrip_fixed_rear_glide.png) · [出口](roundtrip_fixed_rear_fog_exit.png) · [全队顶视](roundtrip_top_flock.png)

## 母版与交接

以 ENV-002 的 StartMudflat 为接触面，按原网格边缘 0.625 BU 的步长接续陆面。以 `(0,−5,0)` 作为 ENV-002 泥滩与 ENV-003 浅洼的共同原点，平水面为 Z = −0.18 BU。两侧水带沿着续接地形下切的河床起伏铺设，ENV-005 稀疏与岸边分布落在航道外缘。ENV-009 的远山采用蓝灰层叠，两侧近山位于出口通行切面以外，远层三座山另存为可选背景 GLB。串联 S0 和 S1 时加载主场景 GLB，远山以视景背景单独管理。FX-004 的六张雾卡摆在航道两侧，地表渐暖、两侧水色渐冷，前方留开口。各输入的 v001 文件路径和哈希见[依赖映射](dependencies.json)，山体、芦苇、泥滩、浅洼、雾卡和标记可在母版分组编辑。

Blender +Y 向前，+Z 向上，导出 GLB 为 `(x,z,-y)`。`S0_Entry` 位于本地 `(0,0,0)`。`S0_Exit_to_S1` 位于 `(0,36,0)`，朝向 `(0,1,0)`。出口从 Y = 34 至 36、X = −12 至 12 为标高 0 的干地。同一标高和朝向供 S1 接入。Y = 30 至 36 的水彩乘色平滑还原为中性白，接缝草地使用 S1 同一张 GrassFlat，UV 的 V 相位一致。浅洼及水带止于接缝之前。雾线为 Y = 33 BU。

相机按 Swift 的后方距离参数 180 游戏单位、俯仰参数 0.48 rad、纵向视场 50°、相对地面注视高度 6 游戏单位。其中 0.9900 BU 对齐 27.5 游戏单位，动作载体根高度减去 8 游戏单位后作为 `depthLift` 同时加到眼高和注视高度。技术顶视仅用于检查摆位。H.264 编码在 852 × 393 源帧底部补一行，短片共 168 帧，无音轨。规格中的约 30 秒为实际玩法目标。

## 动作与运行时接口

母版保留 CHR-001 共享网格、12 套可编辑骨骼和四个来源动作。起飞使用 ANM-002 的 `Takeoff_Climb` 和同一脚底载体数据，随后按相位过渡到 `Cruise_Flap_Loop`、ANM-003 `Glide_Loop` 和 `Circle_Loop`。并行起飞的错相延迟最大 0.155 秒，滑翔、左盘旋再转回北向退出。审阅用的位移与转向直接可查母版关键帧。审阅 GLB 的单条 `S0_Review_Takeoff_Glide_Circle` 同步驱动 12 套蒙皮。环境 GLB 可独立加载。游戏代码提供实际飞行状态、飞行轨迹、地形与碰撞查询、全队通过雾线的判定和雾退场。

母版 `Fog_Start` 的可编辑参数为 `opacity_strength`、`motion_strength`、`period_seconds` 和 `phase_turns`。运行时对应 `opacityStrength`、`motionStrength`、`periodSeconds` 和 `phaseTurns`，另传秒钟 `elapsedSeconds`。默认两个强度为 1，减弱为 0.35，关闭为 0，漂移默认周期 12 秒。每张卡片保留 `base_x_BU`、`amplitude_BU` 和 `phase_turns`，本地 X 位移按 FX-004 公式求值。环境 GLB 保留静态基准位置和内嵌直通 Alpha，应用播放时从节点参数取样。

## 离线回验与待验

从交付目录以独立 Blender 后台进程重开 .blend，再清空场景回导主场景、远山可选背景及 12 雁审阅 GLB。按实际变形网格检查出生点与起飞过程、雾线通过、入场和出口标高、视野和植被。FFmpeg 执行全片解码。详细实测见 [QA](qa.json)。

| 离线回验 | 实测 |
| --- | --- |
| 全队通过雾线 | 第 325 帧已通过，末帧全队最低 Y = 34.674 BU |
| 群体与芦苇 | 122 个采样帧，1,464 次雁与芦苇网格复测，8,052 次雁对探测，均无相交 |
| 出生视线 | 480 条植被视线，未命中遮挡。固定画幅下雁体保守投影距画边最少约 60 px |
| 前方开口 | 中心路径射线的雾叠加 Alpha 峰值为 0。固定起飞画面的中心取样比两侧平均更亮 |
| 接缝 | 245 处平面探针标高无偏差，出口另查 1,029 条景物遮挡探针 |
| 雾参数 | 母版重开后默认、减弱和关闭各验证 102 次，最大位移依次为 1.290、0.451、0 BU |
| 审阅视频 | 168 帧全量解码，无音轨 |

待负责人复核晨光色调及真实首次玩家的前方方向辨识，待 USDZ、RealityKit 透明排序及 App 接入，待运行时验证实际飞行输入、起飞地形接触、碰撞、队形和全队过线。iPhone / iPad 显示、触控、相机和性能待真机验证。App 基线引用计划中的 iPhone 18 Pro（iOS 27.2）模拟器构建和 340 项测试。已对照项目红线清单。

## 复跑

需要 Blender 5.2.2 LTS、Python 3 及 PATH 中的 ffmpeg、ffprobe。第一条命令从任务目录读取版本依赖，输出到空目录。第二条独立进程从交付目录验证。重新封装时将 README 和两个脚本复制到候选目录，封装脚本会复制独立回验证据并重算交付哈希。

```sh
blender -b --factory-startup -t 3 --python-exit-code 1 \
  --python LVL-S0_generate.py -- /tmp/ft-s0-build
blender -b --factory-startup -t 3 --python-exit-code 1 \
  --python LVL-S0_generate.py -- /tmp/ft-s0-recheck --verify "$PWD"
python3 LVL-S0_finalize.py "$PWD" /tmp/ft-s0-recheck
```

[生成与验证脚本](LVL-S0_generate.py) · [封装脚本](LVL-S0_finalize.py)

## 共用文件待登记

- [素材索引](../../../../../docs/asset-index.json) 待登记母版、三个 GLB、预览、布局与 QA 的项目根相对路径。
- [候选素材台账](../../../../../docs/asset-ledger.md) 和 [正式素材台账](../../../../../../docs/references/asset-ledger.md) 待记录项目内组装来源、继承贴图、候选状态与运行时导出路径。组装使用既有项目资产和本轮原创地形、水色与摆位。
- [任务 JSON](../../../../../../完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json) 与 [active 计划](../../../../../../plans/active/goose-preview-model-cleanup.md) 待回写候选文件、离线验收和 App / 真机待验。
