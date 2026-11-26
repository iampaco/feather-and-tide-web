# RD-CHR-001 · 驯鹿预览角色

原创建模和动画，使用仓库内的 [生成脚本](generate.py)。保留 [Blender 源](reindeer-v001.blend) 与 Web GLB 导出。权属和哈希见项目运行时资产清单。

- 坐标为 glTF 的 +Y 向上、+Z 向前，原点位于蹄下地面。动画只修改骨架和纵向体态，世界位移由模拟提供。
- 一个骨架与一个合批网格，共六种色材质。领鹿、幼鹿和成年同伴共享资源。角色尺寸和动画相位由运行时分别设置。
- `Idle` 站立，`Walk` 行走，`Run` 奔跑，`Call` 呼唤，`Settle` 卧下。前四个动作可循环播放，卧下保持最后姿态。
- 以 Blender 5.2.2 执行 `--background --factory-startup --python` 加本目录的 `generate.py`，可重新生成源及 Web 导出。重新导出后同步清单中的文件长度和 SHA-256。
