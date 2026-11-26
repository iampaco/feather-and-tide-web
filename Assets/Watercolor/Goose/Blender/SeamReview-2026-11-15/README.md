# 斑头雁线 S0–S6 接缝合看

2026-11-15 · Blender 5.2.2 LTS · 候选审阅

把七段主场景 GLB 从实际交付目录回导，按路线顺序在同一 Blender 坐标下逐对拼接。段间衔接只需平移，全程朝 +Y。Blender 为 +Z 向上，GLB 为 `(x,z,-y)`。审阅换算为 0.9900 BU 对应 27.5 游戏单位。

[接缝截图总览](seam_contact_sheet.png) · [接缝 QA](seam_qa.json) · [坐标约定](seam_contract.json) · [八项交付文件回验](delivery_audit.json) · [上游文件盘点](dependency_audit.json)

| 相邻段 | 路线世界坐标（BU） | 固定机位 | 技术顶视 |
| --- | --- | --- | --- |
| S0 → S1 | `(0,36,0)` | [跨缝](S0_S1_gate.png) | [顶视](S0_S1_top.png) |
| S1 检查点 A → S2 | `(0,96,0)` | [进入前](S1_S2_before.png) · [入口](S1_S2_gate.png) · [进入后](S1_S2_after.png) | [顶视](S1_S2_top.png) |
| S2 双路汇合 → S3 | `(0,172,0)` | [汇合后](S2_S3_before.png) · [入口](S2_S3_gate.png) · [进入后](S2_S3_after.png) | [顶视](S2_S3_top.png) |
| S3 → S4 | `(0,236,0)` | [跨缝](S3_S4_gate.png) | [顶视](S3_S4_top.png) |
| S4 → S5 | `(0,326,0)` | [跨缝](S4_S5_gate.png) | [顶视](S4_S5_top.png) |
| S5 → S6 | `(0,390,0)` | [进入前](S5_S6_before.png) · [入口](S5_S6_gate.png) · [进入后](S5_S6_after.png) | [顶视](S5_S6_top.png) |

S4 保留湿地原点。外部接缝用已交付 GLB 的 `MarshStitch` 地块边界，本地入口 `(2,-45,0)`，出口 `(2,45,0)`。同一坐标下的湿地内部通行门在 Y = −14 和 22 BU。S4 的世界平移为 `(-2,281,0)`。[S4 原有布局](../LVL-S4/v001/s4_layout.json)

接缝中心 24 BU 全宽的地边连续，两侧各有向内 2 BU 的平地。每道接缝共 1,164 条竖向探针，6 道合计 6,984 条。最大高程误差低于 0.000001 BU，命名锚点的位置和朝向均匹配。另裁切实交付网格，检查接缝全宽的空隙、穿边和邻段前 12 BU 内的跨界面片。记录颜色交接的固定机位帧和技术顶视。共享水位基准为 Z = −0.18 BU，各水面在干地接缝内侧收口。

S0 将越过航道的远山另存为可选背景，并在北侧接缝匹配 S1 草地贴图及 UV 相位。S1 的世界检查点标记和 S2 入口完全重合，实体补给岸在标记南侧。固定机位合看可见左侧山口、右侧湖面及补给岸。S2 的两条路线先在段内汇合，再从共同出口进入 S3 的河谷。S5 出口进入 S6 时，前方视线通向芦苇盆地。部分接缝留有地表纹理过渡，待美术终审。玩法触发与流送、USDZ、RealityKit／App 和 iPhone／iPad 真机待验。

## 复跑

在项目根目录执行。Blender 的报告保留 GLB SHA-256、世界摆位、锚点和逐段采样结果。文件盘点再核对候选清单的 SHA-256、README 链接及 FFmpeg 完整解码。

```sh
review="Assets/Watercolor/Goose/Blender/SeamReview-2026-11-15"
scratch=$(mktemp -d /tmp/ft-seams-check.XXXXXX)
blender -b --factory-startup -t 2 --python-exit-code 1 \
  --python "$review/verify_seams.py" -- --repo "$PWD" --out "$scratch"
python3 "$review/audit_deliveries.py" --repo "$PWD" --out "$scratch/delivery_audit.json"
```

固定机位按源码距离 180、俯仰参数 0.48 rad、纵向视场 50°、目标高 6 复现。画幅为 852 × 393，使用一只 CHR-001 提供尺度。关卡母版中的 12 雁走位及动画见各自短片。[Swift 机位](../../../../../Sources/FeatherTide/Systems/Camera/ThirdPersonRig.swift)
