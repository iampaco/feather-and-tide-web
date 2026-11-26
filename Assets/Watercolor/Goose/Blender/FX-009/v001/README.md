# FX-009｜离队同伴呼唤光点

**v001 · needs_review · Blender 5.2.2 LTS**

[可编辑母版](FX-009_RescueBeacon.blend) · [RescueBeacon GLB](FX-009_RescueBeacon.glb) · [运行时输入](runtime_mapping.json) · [清单](asset_manifest.json) · [QA](qa.json)

`RescueBeacon` 由水平暖金浅雾环和竖直柔光点组成。两层羽化色纹分别打包进 GLB，也提供原始 RGBA PNG。GLB 只包含定位根节点和两片可复用网格，使用直通透明度混合和 `KHR_materials_unlit`。母版中 `FX-009 | RescueBeacon asset` 场景保留中性定位，`Review | Separated companion` 场景保留逐帧可调的接应演示。

- 灰盒 [固定后上方](graybox_fixed_rear.png) · [顶视](graybox_overhead.png)
- 材质 [呼唤](preview_fixed_rear_call.png) · [顶视](preview_overhead_call.png) · [接应中](preview_fixed_rear_escort.png) · [归队后](preview_fixed_rear_rejoined.png) · [同帧无光痕对照](comparison_without_cue.png)
- [固定机位静音片](preview_fixed_rear_silent.mp4) · [GLB 回导](roundtrip_fixed_rear.png)
- [环贴图](textures/ft_goose_fx_rescue_ring_basecolor_alpha.png) · [光点贴图](textures/ft_goose_fx_rescue_soft_point_basecolor_alpha.png)

审阅从 ANM-009/v001 载入 12 只雁及 `Call_Loop` 和 `Rejoin`。离队个体的审阅载体提前放到右外侧，归队末位沿用原动画。审阅空物体提供光环相对偏移，母版中的 `Review | RescueBeacon control` 可调三轴偏移、光强和收敛尺寸。审阅中光环在约 0.33 秒渐显，接应阶段约 2.00 秒渐收并淡出。可达性与危险区交给引擎依据关卡 Zone 和实际航道判断。审阅场景为开阔诊断平面，接应路径以及在 S3 雾、岩面与植被前的观感待关卡实测。

画幅 852 × 393，固定机位按 `ThirdPersonRig.swift` 的 180 游戏单位、0.48 rad、50° 纵向 FOV 和 6 游戏单位注视高。静音短片为 H.264/yuv420p，最后一行补黑以满足偶数高度，实际审阅画面仍为 852 × 393。Blender 轴为 +X 右、+Y 前、+Z 上，GLB 为 +X 右、−Z 前、+Y 上。喙尾 0.9900 BU 对齐 27.5 游戏单位，光环外半径 0.40 BU，光点半径 0.155 BU。

接入由引擎选择与离队同伴相邻且可达的世界坐标，确认实际危险 Zone 外再显示。接应状态和 `escortProgress` 控制整个根节点的缩放及淡出。可将光点绕竖轴转向相机。屏幕外方位可使用同一世界锚点计算，由现有界面流程处理。GLB 内的透明度和定位为静态基础，可参照 [运行时输入](runtime_mapping.json) 接入淡显和收敛。

## 复跑

在项目根目录用 Blender 5.2.2 和 PATH 中的 `ffmpeg`、`ffprobe` 运行。构建输出和回验输出各用空目录。

```sh
asset="Assets/Watercolor/Goose/Blender/FX-009/v001"
build=$(mktemp -d /tmp/ft-fx009-build.XXXXXX)
review=$(mktemp -d /tmp/ft-fx009-review.XXXXXX)
/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -t 4 \
  --python-exit-code 1 --python "$asset/FX-009_generate.py" -- \
  --library "$PWD/Assets/Watercolor/Goose/Blender" --output "$build" --scratch "$review"
/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -t 4 \
  --python-exit-code 1 --python "$asset/FX-009_generate.py" -- \
  --library "$PWD/Assets/Watercolor/Goose/Blender" --output "$PWD/$asset" --scratch "$review" --validate
```

## 待验与登记

Paco 美术复核、S3 实际安全锚点与接应可达性、USDZ / RealityKit / App 接入、iPhone 与 iPad 实际显示和性能待验。本轮沿用已有 iPhone 18 Pro / iOS 27.2 灰盒构建及 340 项通过测试的基线。该基线的 App 资源未包含本候选。

后续在 `Assets/docs/asset-index.json` 登记候选路径，在 `Assets/docs/asset-ledger.md` 与 `docs/references/asset-ledger.md` 登记程序生成来源、ANM-009 审阅依赖、贴图和 GLB 映射，在任务包资源清单 JSON 的 FX-009 条目登记候选状态，并回填 `plans/active/goose-preview-model-cleanup.md` 的离线回验和待验项。
