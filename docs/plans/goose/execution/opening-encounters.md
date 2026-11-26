# 雁篇开场试玩记录 · 堤岸与共享空域

版本为 `goose-p0-9`。从标题页选择「进入游戏 → 斑头雁」，从晨雾湿地重新出发。已有 A 点的玩家可在入口选择重新开始。标题页的「顺风转弯试飞」保留为单独的风带练习。

## 从玩家视角复核

| 场面                                                                        | 操作                                 | 观察                                                                                                      |
| --------------------------------------------------------------------------- | ------------------------------------ | --------------------------------------------------------------------------------------------------------- |
| [堤上开始收线](evidence/opening-encounters/desktop-S0-reeling.jpg)          | 起飞后沿岛侧前进，再轻收推程         | 燕形纸鸢向岸边降低，大人俯身。擦近空中纸鸢的雁短暂收翅。                                                  |
| [领队已过，队尾仍在经过](evidence/opening-encounters/mobile-S0-waiting.jpg) | 越过堤岸后回望，或在外侧水面绕宽弧   | 大人和孩子持线等候。所有成员越过下游通过线后，孩子重新放线。                                              |
| [默认视角的起伞预告](evidence/opening-encounters/mobile-S1-warning.jpg)     | 沿第一道顺风继续飞；在伞衣鼓起时减速 | 从伞后通过后能斜切第二道顺风。                                                                            |
| [保阵走外弧](evidence/opening-encounters/desktop-S1-outer.jpg)              | 早转向宽水面，给 V 字末端留余量      | 整队通过；近侧的伞翼继续按自己的节奏离开。[横屏镜像布局](evidence/opening-encounters/mobile-S1-outer.jpg) |
| [起飞坡](evidence/opening-encounters/desktop-S1-launch.jpg)                 | 若晚察觉，解阵转入宽水面             | 离开影响范围可按原有节奏重整队形。                                                                        |

## 固定输入结果

每秒 60 个模拟 tick。下表为正常旅程从出生点起飞到 S2 的记录。五条航线均经过 A 点、保有 12 只雁，全部未触发救援。`inputs` 保存每一 tick 的世界移动向量与能力状态；`samples` 和 `changes` 保存阶段、航迹及首次散阵时的成员 ID。

| 回放                                                          | 到 S2 的 tick | 擦近滑翔伞的结果                                                                     |
| ------------------------------------------------------------- | ------------: | ------------------------------------------------------------------------------------ |
| [保阵外弧](evidence/opening-encounters/outer.json.gz)         |          1513 | 雁群避开伞翼                                                                         |
| [收速让行](evidence/opening-encounters/yield.json.gz)         |          1510 | 雁群避开伞翼，在第二道顺风内飞行 271 tick                                            |
| [解阵飞向宽水面](evidence/opening-encounters/release.json.gz) |          1534 | 雁群避开伞翼                                                                         |
| [直飞交会](evidence/opening-encounters/brush.json.gz)         |          1432 | 开始充气后 283 tick，`goose-1` 首先擦近，队形散开一次                                |
| [外弧收得过紧](evidence/opening-encounters/tail.json.gz)      |          1482 | 领队已过，最后一只 `goose-11` 在 tick 1137 擦近；持续按住结阵后在 tick 1278 恢复满阵 |

[改前输入与航迹](evidence/opening-encounters/baseline-p0-8.json.gz) 包含直飞、较窄外弧、收速三条路线。将同一组输入逐 tick 送入新版，三条路线均仍可到 A；较窄外弧会擦到队尾。[同输入复测结果](evidence/opening-encounters/same-input-comparison.json)

## 验证方式

- `npm run check` 覆盖严格类型、lint、格式、数据和资源校验、单元与集成测试、生产构建。
- `FEATHER_AIR_EVIDENCE=/tmp/ft-air-replays npx vitest run tests/integration/air-encounters.test.ts` 可重新生成五条新版回放。覆盖全队通过、近岸擦近、队尾擦近、两秒重整、暂停、30/60/120 FPS、检查点和旧 A 档升级。
- `npx playwright test air-encounters.spec.ts tailwind-practice.spec.ts --project=chromium --project=mobile-webkit` 可复测正式入口和独立试飞。浏览器证据使用桌面 Chromium 和横屏移动 WebKit；后者分别使用常规触控和镜像大按钮，开启低画质与减少动态。
- 人物、堤面、燕形纸鸢、伞翼、悬线均为项目内程序几何。收翅沿用现有滑翔 Clip 并叠加双肘收拢。音轨沿用当前雁篇音乐与环境音。

## 真实设备与首次玩家

待用真实 iPhone、iPad 横屏复核画面、触控手感及帧率。首次试玩只说明「带全队抵达」，记录玩家何时看见人、是否主动回望，以及何时因起伞改变速度或航线。首轮目标为五名首次玩家中至少四人能解释堤岸收线的原因，并说出 S1 自己的飞行选择。当前截图和自动回放未计入这项验收。
