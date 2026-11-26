# 斑头雁单线全航程 3D 预览

运行 `./Scripts/goose_linear_preview.sh <输出目录>` 生成私有 Debug 资源。使用项目现有 M10a ZIP 及 Blender 5.2.2 的 USD Python 绑定。开场沿用已登记的雁群、湿地和浅岸配方。源文件保持在素材库，App 预览通过数据目录加载导出。

| 资源 | 来源和适配 |
| --- | --- |
| 风机 | STR-001/v001 的 GLB，保留塔架、机舱、轮毂和三叶网格。RealityKit 将同一模型实例化至单线扫掠圆心。叶轮绕原枢轴转动，角速度为源资产的每 9 秒一周。 |
| 保护湿地 | ENV-016/v001 的 GLB。边缘降低并叠入河面，中间修整平坦休整区，贴合单线已有休整槽的高度。 |
| 远山与过渡河面 | ENV-009/v001 远山 A 导出为 USDZ。MAT-004/v001 的河面纹理逐字节复用，沿飞行方向铺设在河道网格上。 |
| 芦苇盆地 | M10a 的 LVL-S6/v001 精修 USDZ。降低入段边缘并保留 12 个原始落脚锚点和水陆表面。单线将盆地整体平移到现有终段。 |

[素材来源和状态](../../../../docs/references/asset-ledger.md) · [实测导出的 SHA-256](preview-manifest.json) · [试玩证据](../../../../docs/playtests/goose-linear-route-3d/README.md)

重包装 USDZ 的容器时间戳可能改变输出哈希，表中清单对应交付并测试的文件。
