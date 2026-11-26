# FX-008 · V 形结阵引导光痕

**v001 · needs_review · Blender 5.2.2 LTS**

[可编辑母版](FX-008_FormationGuide.blend) · [FormationGuide GLB](FX-008_FormationGuide.glb) · [暖灰金 RGBA 贴图](textures/ft_goose_fx_formation_guide_basecolor_alpha.png) · [运行时输入与材质映射](runtime_mapping.json) · [交付清单](asset_manifest.json) · [离线验收](qa.json)

## 审阅

- [固定第三人称短片](preview_fixed_rear_formation.mov)，852 × 393、8 秒、静音。按镜头顺序可见松散、约 2 秒结阵、1 秒释放、再结阵和急转散开。
- 灰盒 [固定后上方](graybox_fixed_rear.png) · [顶视](graybox_overhead.png)
- 材质 [松散](preview_loose.png) · [渐显](preview_forming.png) · [结阵完成](preview_formed.png) · [释放中](preview_releasing.png) · [释放结束](preview_released.png) · [急转后](preview_broken.png) · [结阵顶视](preview_top_formed.png)
- 回验 [同帧关闭光痕](comparison_formed_without_trace.png) · [GLB 回导固定机位](roundtrip_fixed_rear.png)

母版打开在结阵后，时间线标记记录松散、渐显、释放和急转。12 只预览雁使用已确认的 CHR-001/v001 网格及 ANM-006/v001 母版中的同相位巡航和结阵曲线，各雁振翅错相。审阅采用 ANM-006 的紧凑摆位，让两翼同时进入源码固定取景。其实际队形由游戏控制。审阅脚本按领队平移和航向跟随相机，距离参数 180、俯仰参数 0.48 rad、纵向 FOV 50°，注视高度 6，领队高度 8、同伴高度 6。喙尾 0.9900 BU 对齐 27.5 游戏单位。

## 母版和运行时

在 `FX-008 | portable ribbon` 编辑独立带状网格、UV 和材质。带长 0.64 BU、最大截面宽约 0.155 BU，10 三角面，中心枢轴，应用缩放为 1。源场景 +Y 朝向队首、+Z 向上，GLB 转为 −Z 朝前、+Y 向上。GLB 仅含单条可复用光痕、内嵌 RGBA PNG 与双面 unlit 材质。无绑定、相机、雁或预置队形。柔边和色调由原创程序贴图提供，普通 alpha 混合；光痕无附加闪动和音轨。

在 `FX-008 | fixed rear and V trace` 的 `Formation Guide | Review Controls` 中可调整渐显、释放、急转淡出、透明度、外偏、离地、长度比例及宽度。参数写入属性并由脚本重建审阅动作，也可在 Graph Editor 修改已烘好的材质包络和摆位。青灰底色仅供预览对照。

游戏提供实际队列、航向、高度、结阵完成度及断开/取消信号。对两翼相邻有效锚点各放一段，沿同一翼向近端，侧移 0.91 BU；长度按间距乘 0.67，再依据真实水面或地形高度约束。正常释放保留当前透明度在 1 秒内淡出；急转时约 0.15 秒退去，余下队员继续解阵。运行时建议输入、动态摆放规则和透明度公式见映射；Swift 当前由羽毛按钮进入结阵，手势与队形事件依游戏实现接入。

## 复现与待登记

在仓库根目录用 Blender 5.2.2 和 ffmpeg，使用新的临时输出目录。台前 Blender 会话可继续工作。

```sh
/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -t 4 \
  --python-exit-code 1 --python Assets/Watercolor/Goose/Blender/FX-008/v001/FX-008_generate.py \
  -- /tmp/ft-fx008-rebuild
/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -t 4 \
  --python-exit-code 1 --python Assets/Watercolor/Goose/Blender/FX-008/v001/FX-008_verify.py \
  -- /tmp/ft-fx008-recheck
```

编辑并另存母版后，以 `FX-008_generate.py -- /tmp/FX-008-edited.blend --rebuild-controls /path/to/saved.blend` 重建预览关键帧。生成器从相邻 ANM-006/v001 读取角色与两段动作。QA 默认直接读取实际交付目录，再用独立 Blender 会话重开母版与干净 GLB 场景，严格解码短片。

艺术审阅、最终关卡背景下的透明排序与辨识、运行时动态包络和阵形断开、USDZ、App 接入和 iPhone / iPad 真机均待验证。可引用 active 计划既有 iPhone 18 Pro 模拟器（iOS 27.2，340 项测试）基线。依红线清单，候选仅提供静音、低饱和视觉反馈。

待登记文件为 [共用素材索引](../../../../../docs/asset-index.json)、[候选素材台账](../../../../../docs/asset-ledger.md)、[正式素材台账](../../../../../../docs/references/asset-ledger.md)、[任务 JSON](../../../../../../完整AI建模任务包/羽与潮_斑头雁_资源任务清单_v1.0.json)和 [active 计划](../../../../../../plans/active/goose-preview-model-cleanup.md)。本候选来源为项目内程序化图形与既有角色动作，待登记时保留 CHR-001 / ANM-006 依赖身份、文件 SHA-256、`needs_review` 和上述待验项。
