# 安静航道 · P2 执行与验收记录

当前关卡修订为 `whale-p2-9`，关卡及快照 Schema 1。模拟以 60 Hz 运行。开发服务器与显式启用 `VITE_FEATHER_WHALE=1` 的预览构建可从生物选择进入鲸篇旅程。[俯视布局](layout.md) · [ADR-010](../../adr/010-journey-only-entry.md)

## 人类活动航段 · whale-p2-9

- W2 外侧无网水道用成对浮标指路，边界外的码头展示回收渔具。过网后可沿缓弧进海藻湾，原短网口继续可用。
- W3 近航道增设疏浚水域。水面浮标和清水边线通向同一静水区，泥沙色晕随观察水层变化。必要航标和队尾提示独立于泥沙色晕与声音。
- C2 后增设防波堤横流。堤体绘制与碰撞使用同一个多边形，流带对区内每只鲸施加最高 3.1 世界单位／秒的横向流速。宽线保留水面和借流走法，出流后有静水换气空间。
- W4 静水内侧可以巡航或停留，并显示实际入区且上浮的鲸数。船在可游边界外减速通过浮标，尾迹随航速缩短。观景区位于汇合区之前，免于触发结算。
- C1、C2、路线锁定及 `6/6` 水面汇合规则照旧。p2-8 检查点可载入 p2-9。历史编号副本保留在工作区，构建和关卡校验识别现行源文件与关卡入口。

以下截图取自 macOS 上的横屏 iPhone 15 模拟 WebKit，视口为 852 × 393 CSS 像素。疏浚和横流用例开启静音、低画质和减少动态。[无网水道](evidence/human-activity/W2-outer.png) · [疏浚水域](evidence/human-activity/W3-dredging-entrance.png) · [横流预告](evidence/human-activity/W4-breakwater-preview.png) · [穿越横流](evidence/human-activity/W4-breakwater-crossing.png) · [观鲸船减速区](evidence/human-activity/W4-watching-reach.png)

309 项 Vitest、类型、lint、格式、关卡和资产校验及鲸篇生产构建通过。固定步回放覆盖疏浚两线、横流短线和宽线，以及两条 W0–W4 主航道的 C1、C2 与 `6/6` 汇合。Chromium 与横屏 WebKit 各通过 9 项定向用例，涵盖无网水道、疏浚、横流、观鲸、原岸外顺流、旧 C2 存档及安静航道。Chromium 的三个用例在提高资产加载与软件渲染的测试等待上限后复验通过。真实 iPhone/iPad 触控与新航段性能尚待实测。

## 初版原型规则 · whale-p2-1

- 巡航 6.8 单位/秒，最快 9.5，领鲸转向上限 0.85 弧度/秒。巡航松手约 2 秒停稳，继续沿惯性轨迹判定碰撞。镜头沿用 ADR-009 的 A/B 设置。
- 按住 60 tick 下潜到浅层，再 120 tick 到深层。浅、深层满呼吸预算分别为约 40、20 秒。上浮由深到浅需 72 tick，由浅到水面需 48 tick。每个槽位响应错开 12 tick。松手可反转尚未完成的层间过渡。
- 耗尽时渐进上浮。持续按键会保持上浮后的下潜锁，松开并恢复至少 45% 呼吸后可继续。水面从零到满约 7 秒。切层前的位移使用旧层，切换端点单独测试新层。船体相对扫掠与显示使用同一轮廓和 tick，相位在重试时从快照恢复。
- W2 网外可触发单只队尾离队，外侧也可继续绕行。接应限时 40 秒，在 10 单位内、同层完成过渡且速度不超过 2.2 时累计 2 秒接应。
- C1 在船后静水，C2 在两航道汇流后的静水；两个检查点均要求全队在区内并完成上浮，保存逐鲸状态、补给、路线、触发器与模拟 tick。重试恢复满能量。始终使用一个名单计算 HUD 人数和汇合条件；六鲸水面就绪后锁定模拟并保存一次结果。
- `WL-CHR-001` 为项目原创原型 GLB，运行文件 126,652 字节，前向为 `-Z`，以 0.53 倍装配为约 5.7 世界单位长。模型包含骨架，游姿由运行时调整尾骨和俯仰。水彩海面和层间反馈由 Three.js 绘制，可用 `?whaleGraybox=1` 对照原型。配乐来源见项目资产清单，使用记录为业主提供的游戏用曲。

[俯视布局](layout.md) · [鲸模型原始清单](../../../Assets/Watercolor/Whale/Blender/WL-CHR-001/v001/asset_manifest.json) · [Web 资产清单](../../../public/assets/manifest.json)

## 可重现的航程

回放含初始快照、有效世界输入、事件及最终状态。将以下命令指向任一输出目录即可重新生成 gzip JSON。

```sh
FEATHER_REPLAY_DIR=/tmp/feather-whale-replays npm test -- tests/integration/whale.test.ts
```

| 回放                                                                                                                      | 结果                                                                                         |
| ------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| [旅程近航道](evidence/replays/W0-W4-journey-shipping.json.gz)                                                             | 两处检查点，6/6 汇合，约 4 分 11 秒                                                          |
| [旅程安静航道](evidence/replays/W0-W4-journey-quiet.json.gz)                                                              | 两处检查点，6/6 汇合，约 4 分 42 秒                                                          |
| [水面等船](evidence/replays/W1-surface-wait.json.gz) · [深潜过船](evidence/replays/W1-deep-crossing.json.gz)              | 两种解法均避开船体接触并抵达 C1                                                              |
| [低呼吸刹停与换气](evidence/replays/W1-low-air-refill.json.gz)                                                            | 从 W1 船前低呼吸快游状态刹停，等队伍完成上浮后按提示折返安全水域，全队恢复呼吸且没有船体接触 |
| [旅程接应](evidence/replays/W2-journey-rescue.json.gz)                                                                    | 折返低速同层接应，同伴游回队列                                                               |
| [C1 接应超时重试](evidence/replays/retry-C1-rescue.json.gz) · [C2 能量耗尽重试](evidence/replays/retry-C2-energy.json.gz) | 两类失败均恢复原快照及船相位，重试能量回满                                                   |

从 W1 几何预警区边界到理论最早接触有约 7.25 秒巡航时间。升级版从待航水域入口即可看到受阻层提示。玩家首次辨认及操作时机由真机与首次试玩测量。

W3 对照使用同一份入口快照 `tick=9290`、满能量，量到 C2。近航道游行约 416.5 单位、65.2 秒，最低能量约 94.4%、最低凝聚约 91.0%。安静航道约 611.4 单位、96.0 秒，最低能量约 94.9%、凝聚维持满值。两路都能补给或休整并以满能量到 C2。渠道中段巡航的平均队尾间距约 23.52 与 23.17 单位；全段最大间距分别约 23.80 与 23.97，包含转弯。共享边界只记一次路线，汇流前可折返越线重选，汇流后锁定。[逐项量测](evidence/replays/W3-route-comparison.json)

## 体验升级 · 2026-11-18

可跳过的海湾教学会记录提前完成的动作。有效水层、浮潜方向和换气解锁分开显示。船道前后优先指向同侧静水，进入船道后先提示离开，再指向换气水域。网外航标避开可选接应区，HUD 显示同伴的实时水层、操作步骤、计时和接应进度。岔口两路同时可见，越线后显示路线和实际凝聚。汇合区按接应、归队、上浮和空间位置解释未就绪原因。六鲸同框进入短尾奏，减少动态模式使用静止水纹与构图。

检查点和碰撞沿用 `whale-p2-1`。本次重新导出的两条整章回放、W1 两种解法、低呼吸折返、W2 接应、两类失败回档和 W3 比较，与当前旅程基线逐文件相同。W3 噪声强度为 `0.78`，待按试玩单取得首次玩家结果后评估调参。

| 航段 | 模拟横屏 WebKit 截图                                                                                                      |
| ---- | ------------------------------------------------------------------------------------------------------------------------- |
| W0   | [起游教学](evidence/experience-upgrade/w0-tutorial.jpg)                                                                   |
| W1   | [默认视角](evidence/experience-upgrade/w1-default-low.jpg) · [低画质下转镜](evidence/experience-upgrade/w1-orbit-low.jpg) |
| W2   | [网口低画质](evidence/experience-upgrade/w2-orbit-low.jpg) · [实际接应进度](evidence/experience-upgrade/w2-rescue.jpg)    |
| W3   | [选择前](evidence/experience-upgrade/w3-branch.jpg) · [近航道与凝聚反馈](evidence/experience-upgrade/w3-shipping.jpg)     |
| W4   | [等待上浮 5/6](evidence/experience-upgrade/w4-waiting.jpg) · [汇合 6/6](evidence/experience-upgrade/w4-gathering.jpg)     |

### 浏览器回归

- `npm run check` 通过，Vitest 130 项通过，含鲸集成 28 项。通过关卡校验、素材校验与 TypeScript 严格检查。
- 显式启用鲸篇的构建在 Chromium、桌面 WebKit 和模拟横屏 WebKit 中通过 58 项，3 项按平台跳过。因船道 HUD 的最后一处重叠调整，三种浏览器各重跑 W1/W2 低画质回望，共 6 项通过。
- 默认构建完整 Playwright 回归通过 157 项，67 项按平台或鲸篇预览开关跳过。回归包含首屏物种选择、旧漫游档隔离、雁篇操作及检查点和落脚。
- 在本地 WebKit 对已解码的尾奏监测播放调用。W4 进入汇合后暂停、继续、连点两次跳过，录音启动调用共一次。

### 同环境性能对照

macOS 27.0 arm64、Playwright WebKit 27.2、模拟 iPhone 15 横屏 852×393。两个构建从相同的诊断快照进入各航段，使用默认鲸模型、静音、默认镜头和同一画质。基线与升级版每个样本含 111–146 帧，W4 模拟保持在 `tick=15073`。[完整原始读数与构建标识](evidence/experience-upgrade/webkit-performance.json)

W1 从水面等船回放的初始队形取样，领鲸位于 `(0, 380)`，初始 tick 为 3540。W2 平移同一队形至 `(20, 716)`，初始 tick 为 6900。W4 使用近航道回放的最终队形，在 `tick=15072` 进入旅程继续首帧。

| 场景    | 中位帧时，基线 → 升级 | 标准／低画质 P95，基线 → 升级 | 绘制调用，两档相同 |
| ------- | --------------------- | ----------------------------- | ------------------ |
| W1 船道 | 17 → 17 ms            | 18 → 18 ms ／ 18 → 18 ms      | 44 → 44            |
| W2 网口 | 17 → 17 ms            | 18 → 17 ms ／ 17 → 18 ms      | 35 → 37            |
| W4 汇合 | 17 → 17 ms            | 18 → 17 ms ／ 18 → 18 ms      | 26 → 26            |

本机回环地址新开标准画质航程，点击「鲸」到首个可操作模拟 tick 的 3 次中位值为 58 → 59 ms。该结果仅用于同环境对照。真实 iPhone、iPad Safari 的帧时、触控手感、W1 真人辨认时间和 3 位首次玩家的全章数据待测。[真机试玩单](05-real-device-handoff.md)

## W0 海湾起游 · 2026-11-19

从 `(0, 0)` 沿水面箭头朝 `bay-turn (-33, 105)` 转弯，玩家可以在海湾任意位置松手滑行、停稳、回望与复位。下潜提示适配按住和点按设置。领鲸上浮后，呼吸条显示换气，队尾标记跟随尚未上浮的实际同伴。浅色水纹随每只鲸接近水面与换气出现。低画质保留水纹，减少动态使用定形环。箭头按现有航标坐标生成，换气水纹复用鲸的尾迹环。[俯视布局](layout.md)

全队上浮且呼吸回满后，可留在海湾再练习或沿 `bay-exit (0, 248)` 出湾。略过提示后，航标和水面箭头一起转为指向出湾口。两种走法都越过 `z=270` 进入同一待航水域，水面箭头接到 `ship-wait (0, 340)`。

### W0 回放与试玩

- 两份固定步回放从真实开局出发。直游在 tick 2783（46.4 秒）六鲸全进待航水域。沿缓弯停稳、浅潜和换气后出湾，在 tick 3278（54.6 秒）全队抵达。两路结束时六鲸均在水面、呼吸满值、维持跟随。重导出的近航道与安静航道整章回放与原基线逐字节相同。[完整练习回放](evidence/w0-bay/W0-bay-practice-to-W1.json.gz) · [直游回放](evidence/w0-bay/W0-direct-to-W1.json.gz)
- `npm run check` 通过，共 159 项 Vitest 测试。Chromium 和 iPhone 15 横屏模拟 WebKit 各通过 6 项 Playwright 用例。完整练习分别使用桌面按住和模拟触控点按，另复测略过直游、双指输入、A/B 镜头映射、镜像布局、暂停恢复和 W1 低画质回望。六张截图来自 852×393 模拟横屏，开启低画质和减少动态，配乐关闭。
- 首次玩家能否独立停稳、换气和出湾，以及 iPhone／iPad Safari 真机双手触控，待按试玩单记录。[真机试玩单](05-real-device-handoff.md)

```sh
VITE_FEATHER_WHALE=1 npm run check
VITE_FEATHER_WHALE=1 npm run test:e2e -- tests/e2e/whale.spec.ts --project=chromium --project=mobile-webkit --workers=2 -g 'W0|WH-A01|WH-A02|W1 hazard remains'
```

### W0 截图

[默认镜头起游](evidence/w0-bay/01-bay-arrival.png) · [停稳回望](evidence/w0-bay/02-stopped-look-back.png) · [浅潜与上浮操作](evidence/w0-bay/03-shallow-dive.png) · [领鲸换气、队尾上浮](evidence/w0-bay/04-surfacing-with-tail.png) · [进入 W1 待航水域](evidence/w0-bay/05-into-w1.png) · [略过提示直接出湾](evidence/w0-bay/06-skip-direct.png)

## W1 船道穿越 · 2026-11-18

从待航水域 `z=270–382` 开始，默认镜头适度展宽，显示船体受阻水层。船头、尾迹和方向标签共用当前船位的运动方向，两条琥珀虚线标出 `z=408、428` 的巡逻水带。船体轮廓仍来自同一组碰撞点。船前的浅色箭头引向入口，船后的箭头引向换气水域和 C1。[俯视布局](layout.md)

- **水面等船。** 空档提示使用当前模拟 tick 和船体往返极值，检查船体在全队按巡航速度越过水带的预计时段内，是否让出当前纵向水路。横向范围包含现有队形和顺航方向的跟随位置。预判覆盖船端转向，且随玩家移动和船位更新。
- **深潜通过。** 领鲸已深潜、队尾仍在浅层时，标记对应同伴。全队深潜后继续观察队尾，最后一只离开船体扫掠范围加上碰撞半径的边缘后，提示前往船后静水。低呼吸继续优先指向同侧可达静水。
- **换气与 C1。** 船后静水从 `z=459` 开始。全队过船后在静水内收起警示，提示上浮。进入 `z=485` 起的检查点后，HUD 显示全队水面就绪人数，并区分区外、未上浮和跟随位置空间不足。六鲸入区并完成上浮后触发原有 C1 保存。

等船、深潜、低呼吸折返、近航道和安静航道的五份新导出回放与各自基线逐字节一致。[等船](evidence/replays/W1-surface-wait.json.gz) · [深潜](evidence/replays/W1-deep-crossing.json.gz) · [低呼吸折返](evidence/replays/W1-low-air-refill.json.gz)

### W1 反应窗口

几何用例从预警边 `z=357` 算到理论最早船体接触位置 `z=406.3`，以标准巡航 6.8 单位/秒得到 **7.25 秒**。浏览器采用较靠前的 `(0, 372)`，默认视角，等效旅程起始 tick 3310 的船相位。量到前方有清晰的航线预警时开始输入，记录最后无接触与第一个接触样本。两引擎均得到 **5.70–5.93 秒**的模拟时间夹区，包含从静止加速。用预警点到最后无接触点的距离按标准巡航换算，保守值为 **4.88 秒**。实际推进达到 6.66 单位/秒。用户首次看懂警示的时间须另行试玩。 [Chromium 原始样本](evidence/w1-crossing/chromium-reaction.json) · [模拟横屏 WebKit 原始样本](evidence/w1-crossing/mobile-webkit-reaction.json)

同一起点与已显示预警的船相位再做固定步回放。领鲸以巡航速度开始，**维持 3 秒再松手**，沿原方向靠惯性停在 `z≈398.85`，距理论最早接触线尚有 7.45 单位，全队未触船。 [3 秒后松手回放](evidence/w1-crossing/W1-reaction-coast.json.gz)

### W1 验收截图

[默认镜头预警](evidence/w1-crossing/01-default-warning.png) · [水面空档](evidence/w1-crossing/02-surface-opening.png) · [队尾仍在浅层](evidence/w1-crossing/03-tail-in-shallow.png) · [过船换气](evidence/w1-crossing/04-breathe-after-crossing.png) · [C1 等齐](evidence/w1-crossing/05-c1-waiting.png) · [C1 保存](evidence/w1-crossing/06-c1-saved.png) · [低呼吸折返](evidence/w1-crossing/07-low-air-refill.png) · [低画质回望](evidence/w1-crossing/08-look-back-low.png)

### W1 测试结果

- 启用鲸篇的 `npm run check` 完整通过，Vitest 共 **139 项**。最终独立构建在 Chromium、模拟 iPhone 15 横屏 WebKit 各通过 **5 项 W1 Playwright 用例**。此前两引擎各通过 W2 危险回望、W3 分岔和 W4 单次汇合回归。
- 水面与深潜浏览器走法均从无 C1 存档的相同测试起点开始。浏览器夹具只移动出生点，并平移船的起始相位，通关走实际输入和 IndexedDB 保存。已验证刷新能读出 C1。低呼吸用例由船前、5.5% 呼吸的独立快照起步，折回同侧待航静水，六鲸都在水面恢复至少 95% 呼吸。提前上浮与呼吸耗尽时的船体分层阻挡通过固定步复测。
- 设备环境为 MacBook Pro M2 Max、macOS 27.0。静音、低画质和回望已覆盖模拟横屏。真实 iPhone／iPad Safari 的触控、首次看懂提示的时间待测。 [真机试玩单](05-real-device-handoff.md)

```sh
# 终端一
w1_preview_dir=$(mktemp -d /tmp/feather-w1-check.XXXXXX)
VITE_FEATHER_WHALE=1 npm run check -- -- --outDir "$w1_preview_dir"
npm run preview -- --outDir "$w1_preview_dir" --host 127.0.0.1 --port 4378 --strictPort

# 终端二
VITE_FEATHER_WHALE=1 FEATHER_E2E_PORT=4378 npm run test:e2e -- tests/e2e/whale.spec.ts --project=chromium --project=mobile-webkit --workers=1 -g 'W1'
```

## W2 找网口、折返接应 · 2026-11-19

扩大默认镜头的网前覆盖。渔网东端 `x=58` 的两个角使用加大浮标，轮廓与水下网线来自原碰撞多边形。浅色开口标记指向 `x≈98` 的真实东侧缺口。领鲸仍在网前西侧时，航标先指向同一纵向位置的东侧水域，靠近网面时稍微向后留出转弯空间。对准缺口后，航标才向前引导。网外静水从 `z=792` 开始。网线、浮标和水纹由现有程序化网格及材质绘制。[俯视布局](layout.md)

外侧 `x≈124–126` 可直接绕行。接应路线沿 `x≈98` 越过现有触发区，掉队标记指向实际同伴及其水层。HUD 根据距离、当前水层与速度，提示折返、到同层、松开输入停稳并等候进度。原接应规则为 10 单位内、同层且已完成层间过渡、速度不超过 2.2 单位/秒，累计 120 tick 完成接应。接回后淡青圈和标记跟随同伴游回队列，实际归队后恢复分岔航标。

### W2 回放与验收

- 两份新增回放从同一个原始 C1 快照（tick 4803）开始，均在六鲸跟随状态进入 W3。外侧绕行用时 74.88 秒，全程六鲸跟随。折返接应用时 93.45 秒，唯一的离队与接应事件涉及同一只 `whale-5`。两条回放都未触网。[外侧绕行](evidence/w2-net-rescue/W2-C1-to-W3-bypass.json.gz) · [折返接应](evidence/w2-net-rescue/W2-C1-to-W3-rescue.json.gz)
- 固定步验证三层同一网面受阻、东侧三层均可绕、错层和超速清空接应进度、超时后完整恢复 C1。重新导出的近航道、安静航道两条整章回放及原 W2 接应回放与各自基线逐字节一致。
- `VITE_FEATHER_WHALE=1 npm run check` 通过，Vitest 143 项通过。Chromium 和 iPhone 15 横屏模拟 WebKit 各通过 8 项 Playwright 用例，含 W1、W3、W4 的回归。
- 浏览器从网前测试位置起游，实际操作转向东侧、绕过渔网、回望并接回同伴。两条浏览器路线均接入 W3。另复测接应进度与倒计时随暂停冻结、低画质与减少动态模式下回望可读、静音下完成两条路线、超时回 C1。首航真人辨认、iPhone 和 iPad Safari 真机触控待测。[真机试玩单](05-real-device-handoff.md)

```sh
VITE_FEATHER_WHALE=1 npm run check
VITE_FEATHER_WHALE=1 npm run test:e2e -- tests/e2e/whale.spec.ts --project=chromium --project=mobile-webkit --workers=1 -g 'W2|C1 retry|W1 hazard remains|W3 shows both routes|W4 only settles'
```

### W2 截图

[默认镜头转向提示](evidence/w2-net-rescue/01-net-approach.png) · [东侧真实缺口](evidence/w2-net-rescue/02-real-gap.png) · [外侧直接绕行](evidence/w2-net-rescue/03-outer-bypass.png) · [回望掉队同伴](evidence/w2-net-rescue/04-look-back-for-tail.png) · [接应进度](evidence/w2-net-rescue/05-pickup-progress.png) · [同伴游回队列](evidence/w2-net-rescue/06-swimming-back.png) · [进入 W3](evidence/w2-net-rescue/07-into-w3.png) · [低画质回望网口](evidence/w2-net-rescue/08-look-back-low.png)

## W3 浅礁观景 · 2026-11-18

浅礁从 `quiet-mid (-82, 1114)` 向北布置。静水边界为 `x=-142～-44、z=1092～1210`，常用巡航线在 `x≈-82～-90`。默认镜头的水面前视距离约 45 个单位，从进入静水就能看见第一组礁影。三组鱼群沿礁边游动，五片光斑标出航线附近的静水。经过 `quiet-bend (-78, 1218)` 后沿 `+X、+Z` 向汇流航标和东侧 C2 前进。[俯视布局](layout.md)

礁顶低于深潜层，航道、换气和检查点使用原有判定。浅潜驶近时鱼群散开，减速或离开后慢慢聚拢。鱼群和水面光斑随模拟 tick 更新，暂停和后台停止更新。低画质保留全部三群鱼的轮廓，每群从 22 条降为 14 条。减少动态固定光斑与鱼群的背景游弋，并降低散开幅度和速度。

鲸模型沿用已登记的 `WL-CHR-001/v001`，海面沿用鲸篇 3D 材质。礁石复用 36 个低面数岩石实例。鱼群和五片水面光斑由运行时代码生成，以鲸水彩场景稿和浮游生物稿取色。原稿保留在素材库，运行时零新增贴图或模型下载。[素材台账](../../../Assets/docs/asset-ledger.md) · [Web 资产清单](../../../public/assets/manifest.json)

### 航线与检查点复测

- 两条 W0–W4 旅程回放重新通过，导出文件与基线逐字节一致。近航道在 tick 13203 保存 C2，约 251.2 秒完成。安静航道在 tick 15052 保存 C2，约 282.0 秒完成。两路都在 tick 4803 保存 C1，外海均为 6/6 水面汇合。 [近航道](evidence/replays/W0-W4-journey-shipping.json.gz) · [安静航道](evidence/replays/W0-W4-journey-quiet.json.gz)
- 从校验后的 C1 继续，直游穿过静水 18.48 秒。观景回放在静水巡航约 3 秒后浅潜，松开能力键并停稳，六鲸恢复满呼吸后继续通过转弯和汇流，在 tick 15577 保存 C2。两份有效 C2 快照继续后都能在外海 6/6 水面汇合。[主动观景回放](evidence/w3-shallow-reef/W3-quiet-reef-from-C1.json.gz)

### 浏览器与截图

- `VITE_FEATHER_WHALE=1 npm run check` 通过，Vitest 132 项通过。Chromium 和模拟横屏 WebKit 的 14 项 Playwright 用例通过。
- 浏览器观景用例从 W3 入口线前的测试快照起游，实际越线选择安静航道。验证默认镜头、拖镜浅潜、减速后鱼群聚拢、两种上浮输入、静音、低画质回望和减少动态。模拟切后台后检查 tick、鱼群和光斑在暂停中冻结，明确继续后恢复。C2 浏览器用例在 IndexedDB 载入安静航道整章回放产生的 C2 原始快照，从检查点游到 6/6 水面汇合。
- 横屏 WebKit 截图。 [水面初见](evidence/w3-shallow-reef/01-surface.png) · [浅潜时鱼群散开](evidence/w3-shallow-reef/02-shallow-scatter.png) · [停稳后鱼群聚拢](evidence/w3-shallow-reef/03-school-regrouped.png) · [上浮后转弯航标](evidence/w3-shallow-reef/04-bend-after-surfacing.png) · [低画质、减少动态回望](evidence/w3-shallow-reef/05-look-back-low.png)

```sh
VITE_FEATHER_WHALE=1 npm run test:e2e -- tests/e2e/whale.spec.ts --project=chromium --project=mobile-webkit --workers=1 -g 'W3 reef responds|W3 real frame timings|W4 from an original C2 save completes via surface entry|W3 shows both routes|W4 only settles'
```

### W3 帧时

MacBook Pro M2 Max，macOS 27.0。静音、默认构图、领鲸在 `(-86, 1150.53)` 的水面停稳后，用真实浏览器帧间隔采样。两种画质均启用常规动态。视口 852×393 CSS 像素，帧时为 `requestAnimationFrame` 间隔的中位数和 P95。

| 浏览器                       | 画质 | 绘制缓冲区 | 帧数 | 中位 / P95 | 绘制调用 | 三角形 | 原始数据                                                     |
| ---------------------------- | ---- | ---------- | ---: | ---------: | -------: | -----: | ------------------------------------------------------------ |
| Chromium 159 · SwiftShader   | 标准 | 852×393    |  180 | 32 / 55 ms |       35 | 34,388 | [JSON](evidence/w3-shallow-reef/chromium-standard.json)      |
| Chromium 159 · SwiftShader   | 低   | 852×393    |  178 | 32 / 48 ms |       35 | 33,980 | [JSON](evidence/w3-shallow-reef/chromium-low.json)           |
| 横屏 WebKit 27.2 · Apple GPU | 标准 | 1704×786   |  152 | 16 / 17 ms |       35 | 34,388 | [JSON](evidence/w3-shallow-reef/mobile-webkit-standard.json) |
| 横屏 WebKit 27.2 · Apple GPU | 低   | 852×393    |  152 | 16 / 16 ms |       35 | 33,980 | [JSON](evidence/w3-shallow-reef/mobile-webkit-low.json)      |

本次环境没有可用的 iPhone 或 iPad。真机 Safari 的触控手感、反光与鱼群对比度及长时间帧时待测。 [真机试玩单](05-real-device-handoff.md)

## W4 外海汇合 · 2026-11-18

从 C2 航标 `(62, 1359)` 沿水面箭头前往 `(63, 1476)`。默认镜头先展宽构图，主动转镜后仍可看到更宽的水域。从 `z=1461` 起可在浅青亮水里停留换气。汇合入口两段亮标与目标区前沿 `z=1518` 同源。[俯视布局](layout.md)

领鲸入区后，玩家可继续游动、上浮、减速、停稳和回看。提示与人数共用逐鲸就绪判定，优先处理接应或归队，再定位区外同伴，或标出区内同伴的当前水层与上浮方向。标记跟随对应鲸的真实位置，转镜时保留方向提示。若领鲸停在入口边缘时队伍跟随槽位仍在区外，提示先往亮水中央游，为队尾留出空间。

6/6 水面就绪后，模拟冻结，镜头保留最后观察方向并拉开到六鲸同框。导航边框收起，现有尾迹网格化为水纹，沿用短尾奏。减少动态直接采用同框构图及静态水纹。外海新色取自项目已授权的外海水彩稿，并在现有海面着色器中生成。 [素材台账](../../../Assets/docs/asset-ledger.md)

两条 W0–W4 整章回放通过，新导出与前次基线逐字节一致。新回放从近航道的有效 C2（tick 13203）出发，在浅潜状态入区，实际经过 5/6，31.15 秒后以 6/6 水面进入唯一一次汇合。 [浅潜入区回放](evidence/w4-offshore/W4-shallow-entry-from-C2.json.gz)

横屏 WebKit 截图。 [外海亮水与航标](evidence/w4-offshore/01-offshore-approach.png) · [浅潜入区](evidence/w4-offshore/02-shallow-entry.png) · [5/6 回看区外同伴](evidence/w4-offshore/03-look-back-at-tail.png) · [5/6 等待上浮](evidence/w4-offshore/04-waiting-for-ascent.png) · [6/6 同框](evidence/w4-offshore/05-six-whales.png) · [入口停早时的引导](evidence/w4-offshore/06-make-room.png)

### W4 验收与帧时

- 启用鲸篇的 `npm run check` 通过，Vitest 共 135 项。最终独立构建在 Chromium 和模拟横屏 WebKit 各通过 10 项 Playwright 用例。覆盖有效 C2 的两种入区走法、入口停早、回看区外同伴、等待上浮、六鲸取景、低画质、减少动态、静音、演出暂停与继续、重复跳过、刷新已保存结果、过期标签页和 C2 重试。较早一轮的 W3 浅礁与分岔回归在两个浏览器共通过 6 项。
- 入区走法使用两条旅程产生的 C2 原始快照。入口停早、单鲸仍在区外、单鲸还在上浮和性能采样使用各自的独立测试快照。跨标签页用例使用固定起始时刻校验旧航程的结果写入。
- 工作区的片头调整予以保留。最终测试从单独的输出目录和回环端口启动，使浏览器与截图对应同一个鲸篇预览构建。

```sh
# 终端一
w4_preview_dir=$(mktemp -d /tmp/feather-w4-check.XXXXXX)
VITE_FEATHER_WHALE=1 npm run check -- -- --outDir "$w4_preview_dir"
npm run preview -- --outDir "$w4_preview_dir" --host 127.0.0.1 --port 4375 --strictPort

# 终端二
VITE_FEATHER_WHALE=1 FEATHER_E2E_PORT=4375 npm run test:e2e -- tests/e2e/whale.spec.ts --project=chromium --project=mobile-webkit --workers=1 -g 'W4|a stale whale landing|C2 retry'
```

MacBook Pro M2 Max，macOS 27.0。取领鲸停在 `(78, 1482)` 的默认外海构图，静音和正常动态，CSS 视口 852×393。帧时为实际 `requestAnimationFrame` 间隔，表内以毫秒计。两档、两引擎均为 27,668 个三角形。

| 浏览器                       | 画质 | 绘制缓冲区 | 帧数 |  中位 / P95 | 绘制调用 | 原始数据                                                 |
| ---------------------------- | ---- | ---------- | ---: | ----------: | -------: | -------------------------------------------------------- |
| Chromium 159 · SwiftShader   | 标准 | 852×393    |  173 | 16.7 / 33.2 |       30 | [JSON](evidence/w4-offshore/chromium-standard.json)      |
| Chromium 159 · SwiftShader   | 低   | 852×393    |  175 | 16.7 / 16.8 |       30 | [JSON](evidence/w4-offshore/chromium-low.json)           |
| 横屏 WebKit 27.2 · Apple GPU | 标准 | 1704×786   |  180 |     17 / 26 |       30 | [JSON](evidence/w4-offshore/mobile-webkit-standard.json) |
| 横屏 WebKit 27.2 · Apple GPU | 低   | 852×393    |  180 |     16 / 25 |       30 | [JSON](evidence/w4-offshore/mobile-webkit-low.json)      |

本次环境没有可用的 iPhone 或 iPad。真机触控、首次玩家能否辨认亮水与区外同伴、长时间帧时仍待验证。 [真机试玩单](05-real-device-handoff.md)

## W0–W4 3D 水彩升级 · 2026-11-19

**W0 样板与 W3 验证。** 以默认横屏游玩和回望取景复核了 v001 鲸的剪影、满屏亮纹和重复岸礁。W0 先替换鲸形、水体与浅湾布景，再把同一套水体和鲸部署到 W3。复测锐化鲸的头背、胸鳍和尾鳍缺口后，以岸缘亮纹、换气与尾迹提供局部高光。湾后海蚀拱及连续分层岸线在可游区外，水道内的礁台、碎岩与海草在深潜活动层下。W3 复用原鱼群和换气区，确认标准档与低画质下的浅潜散开、聚拢、上浮提示和向 C2 汇流。此后落实 W1 船体和尾迹、W2 三层网面和端浮球、W3 两路色差及 W4 银蓝亮水。

**运行时契约。** 六鲸共用一个蒙皮网格和一张贴图，各自读取位置、航向、速度和浮潜快照，按独立相位生成推进、滑行、转向及浮潜游姿。船的轮廓与局部水线取自同一碰撞多边形，船头和尾迹用原运动相位定向。网线和端浮球取自碰撞边与水层掩码。汇合取景保留最后的镜头方向，并按六鲸的屏幕范围和体形留边调整景别。减少动态保留静态水纹和导航线索。玩法、关卡数据和存档版本沿用 `whale-p2-1` 与 ADR-010。

**资产。** `WL-CHR-001/v002` 在 Blender 5.2.2 从原创 v001 头肩、鳍根、尾柄和尾部网格派生，保留原拓扑、权重和关节。GLB 包含一个蒙皮网格、3,392 三角形和内嵌 512×512 sRGB JPEG，身体原点，`-Z` 前向，`+Y` 向上。推进、滑行、转向及浮潜由 Web 表现层生成。Blender 在中立、尾部抬降、左右弯和浮潜 7 个姿势中检查蒙皮，均无非相邻三角形自交。NURSE、LANE、OPEN 使用项目于 2026-11-08 授权的素材库稿取色和参考构图。海床、岸礁、货船、渔网和航标由原创 Three.js 几何和着色器实现。岩石、海草、浮标和鱼群实例绘制，按航段裁剪岸段与航标批次。 [素材台账](../../../Assets/docs/asset-ledger.md) · [Blender 源与导出清单](../../../Assets/Watercolor/Whale/Blender/WL-CHR-001/v002/asset_manifest.json) · [模型检查](../../../Assets/Watercolor/Whale/Blender/WL-CHR-001/v002/qa.json)

对岸景三角形按可游边界裁切后，区内岸面最高处为 `Y=-7.77`，W0 礁台最高处为 `Y=-7.91`，深潜模型的中心高度为 `Y=-5.90`。

### 同机位对照

横屏 WebKit、852×393 CSS 像素，左为工作前基线，右为升级后的生产预览。使用相同的旅程输入或恢复锚点。W0 三水层锁定领鲸 XZ、航向和镜头偏航，升降沿用游戏镜头。W1 取原关卡的 `(0,372)` 与向西运行的船舶相位。W2 比较东侧网口和绕网后的回望。W4 汇合使用相同的队伍状态和观察方向，右图应用新的队形取景。

| 航段    | 对照与附加取景                                                                                                                                                                                                                                                    |
| ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| W0 海湾 | [水面](evidence/art-upgrade/w0-surface.jpg) · [浅潜](evidence/art-upgrade/w0-shallow.jpg) · [深潜](evidence/art-upgrade/w0-deep.jpg) · [回望海蚀拱](evidence/art-upgrade/w0-look-back.jpg)                                                                        |
| W1 船道 | [默认视角与船头方向](evidence/art-upgrade/w1-default.jpg)                                                                                                                                                                                                         |
| W2 渔网 | [水面东侧缺口](evidence/art-upgrade/w2-surface.jpg) · [浅潜](evidence/art-upgrade/w2-shallow.jpg) · [转镜观察网端](evidence/art-upgrade/w2-orbit.jpg) · [越网后回望队尾](evidence/art-upgrade/w2-look-back.jpg)                                                   |
| W3 两路 | [分岔](evidence/art-upgrade/w3-branch.jpg) · [近航道](evidence/art-upgrade/w3-shipping.jpg) · [安静航道浅礁](evidence/art-upgrade/w3-quiet.jpg) · [低画质浅礁](evidence/art-upgrade/w3-quiet-low.jpg) · [浅潜穿过礁缘原图](evidence/art-upgrade/w3-reef-pass.png) |
| W4 外海 | [外海入口](evidence/art-upgrade/w4-approach.jpg) · [5/6 回看队尾](evidence/art-upgrade/w4-waiting-tail.png) · [6/6 汇合对照](evidence/art-upgrade/w4-gathering.jpg) · [六鲸同框原图](evidence/art-upgrade/w4-six-whales.png)                                      |
| 鲸模型  | [Blender 同机位侧视](evidence/art-upgrade/whale-profile.jpg) · [浮潜变形](evidence/art-upgrade/whale-dive-trim.png)                                                                                                                                               |

### 规则与检查点回放

启用鲸篇后重跑两路整章回放，两份记录与已归档版本逐字节一致。近航道在 tick 4803 保存 C1、13203 保存 C2，安静航道在 tick 4803 保存 C1、15052 保存 C2。两路均进入水面 6/6 汇合。W1 等船和深潜、W2 接应，以及 C1 救援超时和 C2 耗能重试也与归档记录一致。 [近航道](evidence/replays/W0-W4-journey-shipping.json.gz) · [安静航道](evidence/replays/W0-W4-journey-quiet.json.gz) · [等船](evidence/replays/W1-surface-wait.json.gz) · [深潜](evidence/replays/W1-deep-crossing.json.gz) · [W2 接应](evidence/replays/W2-journey-rescue.json.gz) · [C1 重试](evidence/replays/retry-C1-rescue.json.gz) · [C2 重试](evidence/replays/retry-C2-energy.json.gz)

W1 的默认镜头反应窗口由实际模拟 tick、最后一次巡航未接触和首次接触采样夹定，计入从静止进入巡航的时间。前后两次均为 5.70–5.93 秒，按巡航距离折算为 4.88 秒。 [基线原始数据](evidence/art-upgrade/timing/before-mobile-webkit-w1-reaction.json) · [升级原始数据](evidence/art-upgrade/timing/after-mobile-webkit-w1-reaction.json)

### 浏览器与同机位性能

- 当前工作区启用鲸篇的 `VITE_FEATHER_WHALE=1 npm run check` 通过，Vitest 为 159 项。入口与样式的同期改动保留。对照与帧时使用保留基线入口的隔离构建，当前合并构建复测了实际入口和鲸模型加载。
- Chromium 回归覆盖 20 项，含共享相机的斑头雁 S6 交接。W0 原测试在并行时错过了以墙上时钟推算的暂停时刻，改用进入 W0 前的固定时钟，随后在合并构建从新入口串行通过。横屏 WebKit 的鲸篇回归通过 34 项，桌面键鼠用例按配置跳过。合并版本复测 W0 练习、W0 三水层、W1 取景、W2 网口、W3 两档浅礁和 W4 汇合共 7 项。
- 两套构建各通过 8 项独立帧时采样。截图与复现锚点使用 `tests/e2e/whale.spec.ts` 的 WH-A12、浅礁、路线和汇合用例。基线入口与样式用于画面及性能对照。

MacBook Pro M2 Max，macOS 27.0。Chromium 159 使用 SwiftShader，模拟横屏 WebKit 27.2 使用 Mac 的 Apple GPU。CSS 视口 852×393。Chromium 两档与 WebKit 低档渲染缓冲 852×393，WebKit 标准档 1704×786。按相同测试锚点逐个运行，W3 默认镜头停在 `(-86,约1150.53)` 的水面，W4 默认镜头停在 `(78,1482)` 的外海。两档均为静音、常规动态。每组至少 150 个实际浏览器帧间隔，数值为毫秒。绘制调用与三角形来自 Three.js 的同帧统计。

| 航段 | 浏览器                  | 画质 |       中位 / P95，前 → 后 | 绘制调用 |          三角形 | 原始数据                                                                                                                                         |
| ---- | ----------------------- | ---- | ------------------------: | -------: | --------------: | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| W3   | Chromium · SwiftShader  | 标准 | 33.0 / 47.0 → 32.0 / 50.0 |  35 → 36 | 34,388 → 32,352 | [前](evidence/art-upgrade/timing/before-chromium-w3-standard.json) · [后](evidence/art-upgrade/timing/after-chromium-w3-standard.json)           |
| W3   | Chromium · SwiftShader  | 低   | 33.0 / 46.0 → 33.0 / 49.0 |  35 → 36 | 33,980 → 31,944 | [前](evidence/art-upgrade/timing/before-chromium-w3-low.json) · [后](evidence/art-upgrade/timing/after-chromium-w3-low.json)                     |
| W3   | 横屏 WebKit · Apple GPU | 标准 | 16.0 / 17.0 → 16.0 / 17.0 |  35 → 36 | 34,388 → 32,352 | [前](evidence/art-upgrade/timing/before-mobile-webkit-w3-standard.json) · [后](evidence/art-upgrade/timing/after-mobile-webkit-w3-standard.json) |
| W3   | 横屏 WebKit · Apple GPU | 低   | 16.0 / 17.0 → 16.0 / 17.0 |  35 → 36 | 33,980 → 31,944 | [前](evidence/art-upgrade/timing/before-mobile-webkit-w3-low.json) · [后](evidence/art-upgrade/timing/after-mobile-webkit-w3-low.json)           |
| W4   | Chromium · SwiftShader  | 标准 | 16.7 / 33.3 → 16.7 / 16.7 |  30 → 27 | 27,668 → 22,604 | [前](evidence/art-upgrade/timing/before-chromium-w4-standard.json) · [后](evidence/art-upgrade/timing/after-chromium-w4-standard.json)           |
| W4   | Chromium · SwiftShader  | 低   | 16.7 / 33.2 → 16.7 / 33.4 |  30 → 27 | 27,668 → 22,604 | [前](evidence/art-upgrade/timing/before-chromium-w4-low.json) · [后](evidence/art-upgrade/timing/after-chromium-w4-low.json)                     |
| W4   | 横屏 WebKit · Apple GPU | 标准 | 17.0 / 24.0 → 17.0 / 21.0 |  30 → 27 | 27,668 → 22,604 | [前](evidence/art-upgrade/timing/before-mobile-webkit-w4-standard.json) · [后](evidence/art-upgrade/timing/after-mobile-webkit-w4-standard.json) |
| W4   | 横屏 WebKit · Apple GPU | 低   | 17.0 / 23.0 → 17.0 / 21.0 |  30 → 27 | 27,668 → 22,604 | [前](evidence/art-upgrade/timing/before-mobile-webkit-w4-low.json) · [后](evidence/art-upgrade/timing/after-mobile-webkit-w4-low.json)           |

岸段与航标按航段裁剪后，W3 标准档三角形由 34,388 降至 32,352，绘制调用增加 1 次。WebKit 两档的 W3 中位数和 P95 均为 16 / 17 ms，Chromium 软件渲染两个画质档的 W3 P95 高 3 ms。W4 两档均少 3 次绘制调用，WebKit 标准档 P95 由 24 ms 降至 21 ms。

本轮未取得可用的 iPhone 或 iPad。模拟横屏结果覆盖触控、标准与低画质、减少动态、静音和暂停。真机 Safari 的触感、长时间帧时及阳光下能否辨认网口与队尾仍待验证。 [真机试玩单](05-real-device-handoff.md)

## W0 海湾美术样板 · 2026-11-19

- 鲸形 `WL-CHR-001/v003` 从 v002 派生。形态键调整头肩、胸鳍的后掠和尾鳍的展宽及缺口，沿用原 3,392 三角形、骨架、权重和贴图。出湾前平滑恢复基础形。Blender 在半强度与全强度各检查 7 个姿势，均无非相邻三角形自交。运行时 GLB 为 195,640 字节。 [Blender 导出脚本](../../../Assets/Watercolor/Whale/Blender/WL-CHR-001/v003/shape_bay.py) · [模型检查](../../../Assets/Watercolor/Whale/Blender/WL-CHR-001/v003/qa.json)
- 海湾水面使用稀疏暖色反光，浅潜保留海床色晕，深潜减弱远礁和反光。沙坡、岩台及岸壁水下延伸段共享海床着色。两处岬角承接海蚀拱脚，岸缘泡沫从同一岸线剖面取样。可游区内的海床和礁石保持在深潜活动层以下。关卡文件、碰撞、浮潜、航标和镜头沿用 `whale-p2-1`。
- 对照使用生产预览，横屏 WebKit，852 × 393 CSS 像素，标准画质、减少动态。水面、浅潜、深潜使用出生点与默认朝向，回望使用同一次固定拖镜。四组均核对镜头与六鲸快照。 [同机位前后对比](evidence/w0-bay-study/w0-comparison.jpg)
- `VITE_FEATHER_WHALE=1 npm run check` 覆盖 160 项 Vitest 用例及严格类型、资源、关卡、构建检查。横屏 WebKit 通过 8 项专项用例，覆盖 W0 三水层与练习、W1 船、W2 网口、W3 低画质浅礁、W4 汇合及 GLB 加载重试。iPhone 与 iPad 真机待验。

## W1 货船、W2 渔网、W4 外海汇合 · 2026-11-19

- **W1** 加入收尖的前甲板、分层尾舱、窗带、锚具和成组货柜。船体水线按原多边形细分，艏浪与艉流按原模拟 tick 定向，在往返端点渐弱。几何测试核对水线、两向甲板部件和端点切换。水面等船与深潜均保存完整 C1。 [货船对照](evidence/course-art-finish/w1-before-after.jpg)
- **W2** 主缆、编网和配重沿原三层网边布置，缆线在相邻浮具之间随高度下垂。东端两只长浮具仍锚在原角点。几何测试核对网面投影和浮具的东侧外伸。外侧直绕与折返接应均抵达 W3。 [渔网对照](evidence/course-art-finish/w2-before-after.jpg)
- **W4** 亮水沿 C2、上浮及汇合航标延展，演出时压低背景反光。六鲸各有随原航向散开的短水纹，合成一次实例绘制。水纹读取可暂停的演出进度，低画质保留主弧，减少动态固定形状。6/6 移到右上角，为回望后入场的队尾留出视野。 [外海汇合对照](evidence/course-art-finish/w4-before-after.jpg)

### 同机位取证与回归

冻结当前 W0 样板的生产构建作为基线。12 组截图均为横屏 WebKit，852 × 393 CSS 像素。对比中的暂停时钟、舰船相位、镜头、六鲸状态与汇合进度一致。W1 东西行取同一船位的 tick 890 和 3310，深潜取 tick 3600。W2 三层固定在 `(95, 739)`，越过网端后在 `(94, 804)` 回望。W4 从同一个 C2 夹具出发，回望处为 5/6，汇合截图取归一化演出进度约 0.497。 [逐帧诊断](evidence/course-art-finish/matched-views.json)

`VITE_FEATHER_WHALE=1 npm run check` 通过，Vitest 共 162 项。Chromium 与模拟横屏 WebKit 通过 48 项回归，覆盖 W0、船道两路、网口和接应、W3 两路与低画质、C1/C2 重试以及 W4 暂停、跳过和刷新。横屏 WebKit 另通过 9 项对照取证用例。近航道和安静航道整章回放分别与各自基线逐字节一致，两路的 C1 tick 都是 4803，C2 为 13203 和 15052，进入汇合为 15073 和 16922。

W1 的默认镜头反应窗口在两个浏览器均为 5.70–5.93 秒，按巡航距离折算的保守值为 4.88 秒。 [反应窗口原始数据](evidence/course-art-finish/w1-reaction-window.json)

### 同条件帧时

macOS 27.0 arm64，Chromium 159 走 SwiftShader，模拟横屏 WebKit 27.2 走 Apple GPU。视口为 852 × 393 CSS 像素，标准档 WebKit 缓冲为 1704 × 786，其余为 852 × 393。静音、常规动态，单 worker 串行采样。接近场景每档至少 150 帧，W4 汇合按现有演出长度采样。绘制调用和三角面来自同帧渲染器统计。 [前后原始数据与复测](evidence/course-art-finish/render-performance.json)

| 场景    | 绘制调用 |          三角面 | Chromium P95 标准／低（ms） | 横屏 WebKit P95 标准／低（ms） |
| ------- | -------: | --------------: | --------------------------: | -----------------------------: |
| W1 船前 |  49 → 45 | 28,303 → 28,816 |    33.4 → 33.4／33.4 → 33.4 |               26 → 26／25 → 25 |
| W2 网口 |  40 → 40 | 35,036 → 32,420 |    33.4 → 33.4／33.4 → 33.4 |               25 → 26／18 → 25 |
| W4 入场 |  27 → 27 | 22,604 → 22,604 |    33.3 → 33.4／33.3 → 33.3 |               26 → 26／23 → 25 |
| W4 汇合 |  26 → 13 | 22,208 → 21,100 |    33.3 → 33.3／33.4 → 33.4 |               25 → 26／24 → 24 |

W2 横屏 WebKit 低画质初测 P95 为 18 → 25 ms。两轮交替复测为 25 → 25 ms 和 25 → 23 ms，未复现稳定回退。iPhone、iPad Safari 的触控、观感和帧时待验。 [真机试玩单](05-real-device-handoff.md)

## W0–W4 海域空间与水层可读性 · 2026-11-20

- W0 海蚀拱保留为回望地标。后岸水下剖面与两侧沙坡共用接缝顶点，沙坡随湾形展开并在 W1 待航区前沉入海床。水面边缘在可游区外用断续浪带提示范围。海床按世界坐标分块和裁剪，鲸体、海床及礁石按真实表现高度、视距与浮潜进度共用水下衰减。
- W1 深潜时淡出甲板和艉流，保留与碰撞占用同源的船底阴影和受阻层轮廓，预警让出船体投影。混合水层取证使用已深潜的领鲸和仍在浅潜的队尾。W2 在原网角增加立柱，降低网纹对比，将外侧地貌参照压在深潜活动层以下。
- W3 近航道使用成对航标与横浪，安静航道使用低伏礁脊和斜向沙槽。越线前默认镜头同时纳入两个入口，拖镜优先。静水区以连续礁脊取代重复大石块，鱼群的散开与聚拢继续读模拟快照。W4 从 C2 降低海床，放大银蓝反光的尺度，汇合时压低反光以保留六鲸和水纹。
- 几何测试覆盖海床分块接缝、湾口与待航水域的净空、船体相位、网端以及分岔两侧的地貌。两条整章回放、W1 等船和深潜、W2 救援与 C1/C2 重试共七份，与归档模拟回放一致。W1 模拟横屏 WebKit 默认镜头的预警至接触区间为 5.70–5.93 秒，按巡航距离折算约 4.88 秒。
- 启用鲸篇的 `npm run check` 通过，含 179 项 Vitest 测试。模拟横屏 WebKit 27.2 回归 54 项通过，按平台跳过 1 项桌面键盘测试。852 × 393 CSS 像素，Mac Apple GPU，标准画质 P95 样本为 W1 船前 25 毫秒、W2 网口 23 毫秒、W3 浅礁 17 毫秒、W4 进场 26 毫秒及汇合 25 毫秒。iPhone 与 iPad Safari 真机观感、触控和帧时待验。
- Chromium 通过入口、W0 直游和完整教学，以及 6 项场景专项，包含 W0 三层和回望、W1 货船及混合水层、W2 三层绕网、W3 分岔、W4 六鲸同框。其余 Chromium 用例本轮未执行。

## W0–W4 航行与接应改造 · whale-p2-2

- W0 弯后设滑停水域。W1 提示领鲸和队尾分别何时清船。W4 在队形需要空间时同时标记亮水中央和实际队尾，逐鲸上浮有独立水纹。[俯视配置](layout.md)
- W2 从相同 C1 出发，贴网短线 69.42 秒，外侧宽线 74.83 秒，均无接触、无掉队。擦网样例中 `whale-2` 在 tick 8147 脱队，折返后于 tick 9373 开始归队。另一路实际擦网后等待倒计时耗尽，回 C1 恢复完整快照。[短线](evidence/p2-2/W2-C1-to-W3-short.json.gz) · [宽线](evidence/p2-2/W2-C1-to-W3-wide.json.gz) · [折返接应](evidence/p2-2/W2-C1-to-W3-rescue.json.gz) · [超时重试](evidence/p2-2/retry-C1-rescue.json.gz)
- W3 近航道 7 秒受扰、13 秒安静，同一轮廓影响三个水层。等到完整空档的回放全段凝聚满值。错过空档时凝聚下降，能在 C2 前恢复。到 C2 的自动巡航对照中，近航道为 65.22 秒、最低凝聚 69.2%、最大队尾距离 27.28。安静航道为 96.75 秒、凝聚满值、最大队尾距离 23.96。[等空档](evidence/p2-2/W3-near-window-from-C1.json.gz) · [错过空档后恢复](evidence/p2-2/W3-near-late-from-C1.json.gz) · [进湾浅潜和换气](evidence/p2-2/W3-quiet-reef-from-C1.json.gz) · [对照数据](evidence/p2-2/W3-route-comparison.json)
- 两条整章固定步回放分别在约 4 分 11 秒、4 分 43 秒达到 6/6。旧版 C1、C2 的读取保留六鲸、资源、路线和 tick。C2 可在新构建里继续并写入新版汇合结果。[近航道全程](evidence/p2-2/W0-W4-journey-shipping.json.gz) · [安静航道全程](evidence/p2-2/W0-W4-journey-quiet.json.gz) · [浅潜入区](evidence/p2-2/W4-shallow-entry-from-C2.json.gz)

横屏 WebKit 截图。 [海湾出航](evidence/p2-2/W0-out-of-bay.png) · [队尾仍浅潜](evidence/p2-2/W1-tail-in-shallow.png) · [渔网接应](evidence/p2-2/W2-pickup.png) · [W3 选路](evidence/p2-2/W3-branch.png) · [静水等待](evidence/p2-2/W3-noise-active.png) · [可巡航空档](evidence/p2-2/W3-noise-quiet.png) · [浅礁观景](evidence/p2-2/W3-shallow-bay.png) · [全队汇合](evidence/p2-2/W4-gathering.png)

模拟横屏 WebKit 27.2 标准画质在 W3 浅礁的 152 帧样本中，中位帧时为 16 毫秒，P95 为 18 毫秒。 [原始帧时数据](evidence/p2-2/W3-webkit-standard.json)

自动化验证覆盖 74 项鲸篇 Vitest、55 项 Chrome 和 110 项桌面／横屏 WebKit 用例。待航航标的最后调整在两种 WebKit 配置各复测选路和穿越，共 4 项。Chrome 跳过 1 项平台专用用例，两种 WebKit 各跳过 1 项。启用鲸篇后的构建、类型、关卡和资产校验通过。仓库级检查另报告了驯鹿工作区的 lint 及测试问题。

以上时长来自固定步输入回放。首次玩家用时、选路理解和实机双手操作按[真机试玩单](05-real-device-handoff.md)继续测量。

## W0–W4 航行体验升级 · whale-p2-3

- W0 用独立内湾入口和水面箭头呈现滑停练习，同时保留出湾直线。W1 用实际越界位置统计清船人数，在静水换气提示前检查所有同伴。W4 指向亮水中央，按队尾在区外或在上浮分别提示等候。
- W2 新增三层分隔网，留下 33 单位短口及 40 单位外侧宽水道。渔网轮廓、相应立柱和逐鲸碰撞共享几何。引导在领鲸过网后显示实际队尾，并从两个通路选可达接应方向。两网共享同一次连续触网的能量与凝聚代价。
- W3 可选顺流带使用关卡多边形及流向 `(28, 60)`。浅潜及深潜中，实际航向和主动推进均对准阈值才生效。助推配置 1.2 单位/秒，按摇杆推程生效并沿用加速上限；该固定步的游动能耗乘以 0.52。在礁后静水可松手上浮。宽水面、静水观景和近航道也可各自通往 C2。
- 读取 `whale-p2-1`、`whale-p2-2` 的 C1/C2 或到达记录会迁到新修订。旧关卡回放仍按当时的几何解释。

固定步长回放从同一 C1 到 W3，短口用 73.25 秒、宽线用 74.83 秒，两路均无接触。触网样例中 `whale-2` 在 tick 8147 脱队，tick 9750 开始归队。借流样例实际受助约 9 秒，出带换气，到达 C2 后完成 6/6。从出发 tick 折算，借流旅程约 4 分 53 秒。首次玩家时长、取舍理解和 iPhone／iPad Safari 手感按[真机试玩单](05-real-device-handoff.md)记录。

[内湾练习](evidence/p2-3/W0-bay-practice-to-W1.json.gz) · [短口](evidence/p2-3/W2-C1-to-W3-short.json.gz) · [宽线](evidence/p2-3/W2-C1-to-W3-wide.json.gz) · [实触网折返](evidence/p2-3/W2-C1-to-W3-rescue.json.gz) · [借流到 6/6](evidence/p2-3/W3-current-C1-to-W4.json.gz) · [近航道全章](evidence/p2-3/W0-W4-journey-shipping.json.gz) · [宽水面全章](evidence/p2-3/W0-W4-journey-quiet.json.gz)

最终构建通过 239 项 Vitest 测试，以及 11 项横屏 WebKit 定向回归和 1 项桌面 WebKit 键盘测试。严格类型、lint、格式、关卡与资产校验、生产构建通过。横屏回归检查了两种船道穿越、短口与宽线、队尾接应、浅礁观景、双指借流与汇合。音频时钟暂不可用时跳过调度，开航与画面继续运行，回归用例单独注入了不可用时钟验证。

[内湾入口](evidence/p2-3/W0-two-routes.png) · [水面空档](evidence/p2-3/W1-surface-window.png) · [队尾仍浅潜](evidence/p2-3/W1-mixed-depth.png) · [短口清网计数](evidence/p2-3/W2-short-tail.png) · [外侧宽线](evidence/p2-3/W2-outer.png) · [接回同伴](evidence/p2-3/W2-pickup.png) · [顺流入口](evidence/p2-3/W3-current-entry.png) · [浅潜借流](evidence/p2-3/W3-current-active.png) · [外海集合空间](evidence/p2-3/W4-make-room.png)

## W0–W4 航行节奏试调 · whale-p2-4

- 巡航由 6.8 提到 9.2，全推由 9.5 提到 12.4，轻推起点仍为 1.5 单位／秒。巡航松手的理论滑行距离约 7 单位。领鲸加速度为 6.6、减速度为 6、最大转速为 1.15 弧度／秒；同伴游速上限为 15.2，近航道噪声中的跟随上限为 7。真实触屏手感仍需试玩。
- W0 出湾线上可接近并浅潜看银鱼，鱼群会让开较快游过的领鲸，降速后再聚拢。W2 清网后，可进入有 0.38 容量的海藻湾补给，领鲸浮出水面且多数同伴在湾内才消耗库存。W4 外侧顺流可由浅潜或深潜主动触发，最大助推配置为 1.9 单位／秒，入外海静水后可上浮。三处与原主航线并存。
- 固定步长全程回放以相同路线和推程比较，自出发至 6/6 汇合，近航道由 251.22 秒缩到 186.83 秒，安静航道由 282.73 秒缩到 210.23 秒。两个航程均保存 C1、C2。回放用时衡量游速与可通关性，首次玩家的观察和等待时长需实测。
- 横屏 WebKit 默认镜头从船前试验起点测得接触区间 4.40–4.62 秒。按最后无接触位置至起点的距离折算，保守巡航反应窗口为 3.65 秒。水面等船与全队深潜均抵达 C1。 [反应窗口原始数据](evidence/p2-4/W1-reaction-window.json)
- 启用鲸篇的 `npm run check` 通过，包含 246 项 Vitest 测试。模拟横屏 WebKit 的 61 项适用用例均通过，包含浅礁转弯标记的单独复测，另跳过桌面键盘专用测试。桌面 Chromium 通过 9 项定向验证，覆盖键鼠、三个新场景、船道与汇合。iPhone 和 iPad Safari 真机未测。

[W0 银鱼群](evidence/p2-4/W0-silverfish.png) · [W2 海藻湾补给](evidence/p2-4/W2-kelp-shelter.png) · [W4 外海顺流](evidence/p2-4/W4-offshore-current.png)

## W3 两段顺流 · whale-p2-5

第一段流向为 `(22, 50)`，第二段流向为 `(44, 29)`。入第二段前须主动向东转向，西侧有水面宽线。两段之间的礁间静水约 51 × 36 单位，能容纳全队上浮，提示只统计区内已经上浮并归队的成员。满呼吸的连续路线仍需留意出第二段时的上浮时机。

三种走法使用同一个 C1 和相同的 W2 输入，在领鲸抵达 W3 安静航道 `Z=1088` 后分别操作。以下秒数从分流点计到 C2 保存，呼吸余量取这段内六鲸的最小值。三种走法均在 C2 确认六鲸就绪，继续游到 W4 并完成 6/6 汇合。

| 走法         | 至 C2  | 最低呼吸 | 借到两股流 | 静水换气   |
| ------------ | ------ | -------- | ---------- | ---------- |
| 连续借流     | 36.53s | 18.75%   | 是         | 连潜通过   |
| 中途换气集队 | 38.63s | 66.33%   | 是         | 六鲸满呼吸 |
| 水面宽线     | 41.68s | 100%     | —          | 水面巡航   |

[分路实测数据](evidence/p2-5/W3-route-comparison.json) · [连续借流回放](evidence/p2-5/W3-two-currents-continuous-C1-to-W4.json.gz) · [中途换气回放](evidence/p2-5/W3-two-currents-regroup-C1-to-W4.json.gz) · [水面宽线回放](evidence/p2-5/W3-two-currents-surface-C1-to-W4.json.gz)

[第二段顺流](evidence/p2-5/W3-second-current.png) · [静水六鲸就绪](evidence/p2-5/W3-eddy-six-ready.png) · [水面宽线](evidence/p2-5/W3-surface-channel.png)

251 项 Vitest 测试、严格类型检查、lint、格式、关卡与资产校验、生产构建均通过。模拟横屏 WebKit 的 13 项定向回归覆盖三条路线、双指控制、静水满呼吸、W3 近航道、C2 恢复和 W4 汇合。桌面 Chromium 的三条路线也都通过。真机 Safari 的触屏手感待测。

## W2 带队进海藻湾 · whale-p2-6

全队清网后，短切线经 `(72, 831)`、`(53, 848)` 进入湾中，适合提前收速并看着队尾；外侧缓弧从 `(104, 837)` 出发，逐步转向，在海藻湾北侧进入。两线提供水面箭头和对应航标，玩家操舵选线。`net-kelp` 容量为 0.38，HUD 从真实位置统计未离队成员，领鲸在水面且至少四只在内才会补给。自动回能的网外静水收在东侧 `x=115–142`，其余玩家可沿分岔航标直游。

固定步长回放共用同一 C1，穿过同一个短网口，从领鲸到 `z=815`、六鲸均已清网时开始计时。短切使用 0.64 推程，缓弧使用 0.83 推程。两路各松手停留 4 秒观察补给与集队，六鲸入湾后继续游，直到六只鲸都越过 W3 起线 `z=930`。

| 走法     | 领鲸进湾 | 从领鲸进湾到六鲸到齐 | 六鲸进入 W3 |
| -------- | -------- | -------------------- | ----------- |
| 短切进湾 | 4.20s    | 4.42s                | 24.33s      |
| 外侧缓弧 | 13.78s   | 2.73s                | 29.13s      |

[两路实测数据](evidence/p2-6/W2-kelp-route-comparison.json) · [短切回放](evidence/p2-6/W2-kelp-short-C1-to-W3.json.gz) · [缓弧回放](evidence/p2-6/W2-kelp-arc-C1-to-W3.json.gz)

[进湾分路](evidence/p2-6/W2-kelp-choices.png) · [收速等队尾](evidence/p2-6/W2-kelp-waiting-tail.png) · [四鲸就位时补给](evidence/p2-6/W2-kelp-arc-replenishing.png) · [六鲸进湾](evidence/p2-6/W2-kelp-six-in-bay.png)

255 项 Vitest 测试、严格类型检查、lint、格式、关卡与资产校验、生产构建通过。模拟横屏 WebKit 通过 9 项 W2 定向用例，覆盖两种进湾、补给耗尽、网口三水层、绕网及接应。桌面 Chromium 也通过两种进湾。iPhone／iPad 真机触控待测。

## 航行节奏与带队反馈 · whale-p2-7

- **W0 海湾**起点推进 48 个世界单位，内湾缓弯入口距起点约 32 单位。以相同推程直游，领鲸进入银鱼群 14 单位范围的回放从 18.43 秒提前到 7.27 秒，六鲸进入 W1 从 34.70 秒缩到 29.12 秒。可略过教学直游，也可在内湾滑停、浅潜和回望。
- **W1 过船与预告。** 全队进入 C1 并上浮后，立即出现短口和宽线预告，水面箭头接至各自入网路线。船体、预警区、C1 的范围和周期沿用上一版。模拟横屏 WebKit 的定点测试按巡航距离折算有约 3.65 秒反应时间，水面等船和深潜均成功保存 C1。
- **W2 短口**需要提前对准和收速，宽线用缓弧接到网外静水。领鲸到达网口后半段且前方净空时即显示真实未清网的队尾和可继续直游的位置。从同一 C1 到六鲸越过 `z=930`，短口用时 55.90 秒，领鲸行进 462.5 单位。宽线用时 58.32 秒，领鲸行进 501.3 单位。两条回放均无触网或掉队。另有实际擦网、沿可通行水域折返和接回同伴的回放。
- **W3 借流。** 两股流各自沿实际关卡轮廓绘制漂粒，降低画质时降低粒子密度，减少动态时保留静态水纹和方向标记。下潜并同时对齐摇杆输入和实际航向时，推程达到 42% 可获得该流配置的完整助力，仍受原速度上限约束。尾迹依据每只鲸的实时位置、水层和航向显示。第一段后半段同时显示第二段入口和静水入口，允许提前转向或带队换气。

三条 W3 走法从同一 C1 出发，共用 W2 输入，从领鲸抵达安静航道 `z=1088` 开始计时，到全队在 C2 上浮保存结束。最低呼吸取该区间内任一鲸的最低值。

| W3 走法            | 至 C2    | 最低呼吸 | 外海汇合 |
| ------------------ | -------- | -------- | -------- |
| 连续借流           | 35.80 秒 | 22.25%   | 6/6      |
| 静水换气后接第二段 | 37.78 秒 | 68.42%   | 6/6      |
| 水面宽线           | 41.68 秒 | 100%     | 6/6      |

两条整章回放分别在 181.25 秒和 204.65 秒进入 6/6 汇合。旧版 C1、C2 和完成记录沿用快照 Schema 1，可迁移到本版，模拟时相与队伍按保存值恢复。

[海湾银鱼](evidence/p2-7/W0-silverfish.png) · [C1 后预告](evidence/p2-7/W1-route-preview.png) · [W1 反应窗口数据](evidence/p2-7/W1-reaction-window.json) · [W2 清网队尾](evidence/p2-7/W2-before-turn.png) · [W2 宽线静水](evidence/p2-7/W2-wide-rest.png) · [W3 转向与换气提示](evidence/p2-7/W3-two-choices.png) · [W3 顺流尾迹](evidence/p2-7/W3-second-current.png)

[近航道全程](evidence/p2-7/W0-W4-journey-shipping.json.gz) · [安静航道全程](evidence/p2-7/W0-W4-journey-quiet.json.gz) · [连续借流](evidence/p2-7/W3-two-currents-continuous-C1-to-W4.json.gz) · [中途换气](evidence/p2-7/W3-two-currents-regroup-C1-to-W4.json.gz) · [水面宽线](evidence/p2-7/W3-two-currents-surface-C1-to-W4.json.gz)

启用鲸篇的 `npm run check` 通过，含 268 项 Vitest 测试及严格类型、lint、格式、关卡、资产与生产构建。模拟横屏 WebKit 的鲸篇回归 66 项通过，桌面 WebKit 的 8 项定向回归通过，包含桌面键盘专用项。真实 iPhone／iPad Safari 及首次玩家试玩待按[真机试玩单](05-real-device-handoff.md)记录。

## W0 海湾与 W1 船道交接 · whale-p2-8

- W0 调整浅滩、礁坡和湾口浪线，让银鱼群与出湾方向进入行进视野。经过银鱼后可以沿水面航标直游，或浅潜进入 `bay-current`，沿同源流纹轻推。借流初值为助推 1.8 单位／秒、节能 30%、42% 推程达到最大助力、对齐阈值 0.78。出流可在亮水上浮，或在水面等仍在上浮的队尾。领鲸到达湾口后预告湾外货船的实时航向。
- 固定步回放从同一出生点出发，水面线接等船在 tick 2289 保存 C1，借流线接深潜在 tick 2757 保存 C1，均为六鲸完成上浮且无触船。两份整章回放分别在 tick 10875 和 12279 完成 6/6 汇合。 [水面至 C1](evidence/p2-8/W0-surface-to-C1.json.gz) · [借流至 C1](evidence/p2-8/W0-current-to-C1.json.gz) · [近航道](evidence/p2-8/W0-W4-journey-shipping.json.gz) · [安静航道](evidence/p2-8/W0-W4-journey-quiet.json.gz)
- 模拟横屏 WebKit 的 8 项定向验证及桌面 Chrome 的 4 项串行复测通过。W1 定点预警至接触样本为 4.40–4.62 秒，按巡航距离折算的保守值为 3.65 秒。 `whale-p2-7` 的 C1、C2 与完成档由现有兼容链恢复。 [W1 反应窗口](evidence/p2-8/W1-reaction-window.json)

横屏对照为 734 × 343 CSS 像素，同一默认镜头，位置差不超过 0.31 世界单位。基线取本地 p2-7 生产构建，取证时只开启鲸章节入口。

| 航段     | p2-7                                      | p2-8                                              |
| -------- | ----------------------------------------- | ------------------------------------------------- |
| 起游     | [旧版](evidence/p2-8/p2-7-01-spawn.jpg)   | [浅滩与礁坡](evidence/p2-8/p2-8-01-spawn.jpg)     |
| 银鱼     | [旧版](evidence/p2-8/p2-7-02-shoal.jpg)   | [水面与顺流入口](evidence/p2-8/p2-8-02-shoal.jpg) |
| 湾口     | [旧版](evidence/p2-8/p2-7-03-mouth.jpg)   | [亮水与船舶预告](evidence/p2-8/p2-8-03-mouth.jpg) |
| 待航水域 | [旧版](evidence/p2-8/p2-7-04-waiting.jpg) | [W1 船道警告](evidence/p2-8/p2-8-04-waiting.jpg)  |

同一台 Mac 的模拟横屏 WebKit 起游静止样本，标准和低画质均为 17 ms 中位帧时、18 ms P95，绘制调用 26 → 27。借流截图使用静音、低画质与减少动态。真实 iPhone、iPad Safari 和首次玩家试玩待按试玩单登记。 [帧时原始数据](evidence/p2-8/frame-samples.json) · [实际借流画面](evidence/p2-8/W0-bay-current.jpg) · [真机试玩单](05-real-device-handoff.md)

## W0–W4 场景与鲸体精修 · 2026-11-22

- **鲸群。** `WL-CHR-001/v004` 加宽胸鳍和尾鳍，修整头肩、尾柄和尾鳍缺口。领鲸的背斑与同伴的两套鳍缘色阶共享骨架、网格和贴图。Blender 在三档海湾形态键强度合计检查 21 个姿势，未发现非相邻三角形自交。 [模型检查](../../../Assets/Watercolor/Whale/Blender/WL-CHR-001/v004/qa.json)
- **W0 海湾。** 不对称的层状礁脊连到沙坡，小型碎岩按簇落在海床。海蚀拱的拱腹和迎光面有独立明暗。水面分布断续反光，浅潜时光纹贴着礁岸和鲸体，深潜时远处地貌逐渐衰减。
- **W1 船道与 W2 渔网。** 船桥、船窗、货柜和艏艉水纹强化朝向与体量。渔网的垂缆、配重、浮具沿原网面布置，两处网端保留清晰标记。海藻湾用六簇折面叶片和海床礁片标出湾缘，两个进湾口留出宽水面。
- **W3 浅礁。** 弯曲的浅沙槽和礁脊指向安静航道。两处换气水域以局部光斑区分，内侧鱼群聚在同一片礁湾。顺流多边形仍表示区域，同一时间只显示离观察水层最近的一组箭头。
- **W4 汇合。** 银蓝水纹沿既有航标延展，用快照识别刚刚满足汇合条件的鲸并突出其水纹。同一模拟步就绪的鲸可以同时高亮，减少动态保留静态水纹。

### 画面对照与帧时

截图来自同一组模拟横屏 WebKit 27.2 取景用例，视口为 852 × 393 CSS 像素。对照覆盖 W0 三个水层、海蚀拱回望、货船、短网口、低画质海藻湾、浅礁及六鲸汇合。 [W0–W4 前后对比](evidence/scene-refinement/whale-before-after.jpg) · [W0 水层与回望对比](evidence/scene-refinement/whale-bay-depths.jpg)

在同一台 Mac 上以模拟横屏 WebKit 27.2、Apple GPU、标准画质串行采样，绘制缓冲为 1704 × 786。数值为每组实际帧间隔，中位数及 P95 以毫秒计。 [原始样本](evidence/scene-refinement/webkit-frame-samples.json)

| 取景    | 中位数 前 → 后 | P95 前 → 后 | 绘制调用 前 → 后 |
| ------- | -------------- | ----------- | ---------------- |
| W1 船前 | 17 → 17        | 21 → 25     | 47 → 47          |
| W2 网口 | 16 → 17        | 21 → 24     | 62 → 63          |
| W3 浅礁 | 16 → 16        | 20 → 19     | 59 → 55          |
| W4 入场 | 17 → 17        | 21 → 24     | 31 → 31          |
| W4 汇合 | 17 → 17        | 20 → 21     | 14 → 14          |

W1 默认镜头的预警至实测接触为 4.40–4.62 秒，按巡航距离折算约 3.65 秒。W1 船体、W2 网面与 W3 顺流几何检查通过。iPhone 与 iPad 真机观感、长时间帧时和触控仍待实测。 [W1 预警原始数据](evidence/scene-refinement/w1-reaction-window.json)

### 回归结果

290 项 Vitest、资产和关卡校验、严格类型检查、lint、格式及鲸篇生产构建通过。模拟横屏 WebKit 通过 57 项功能用例和 5 项帧时用例，按平台跳过桌面键鼠用例。桌面 Chrome 串行通过 10 项定向用例。原工作区的 `public/levels/whale 2.json` 和 `src/simulation/whale-world 2.ts` 分别会阻断关卡校验和类型检查，完整检查在排除这两个副本的隔离拷贝中运行。

## 历史原型证据

旧漫游的 [近航道](evidence/replays/W0-W4-roam-shipping.json.gz)、[安静航道](evidence/replays/W0-W4-roam-quiet.json.gz) 和 [自动归队](evidence/replays/W2-roam-rescue.json.gz) 回放仅供历史查阅。下列浏览器截图与计数来自原型批次。

在 macOS 27.0 arm64 使用 Chromium、桌面 WebKit 及横屏 iPhone 15 模拟 WebKit。浏览器专项覆盖双指职责、镜像和放大按钮、点按下潜、转屏暂停、船网提示、保存一次汇合及加载重试。独立场景截图使用 W1～W4 的固定状态。W1 1280×720 样本有 53 个绘制调用及约 3.1 万三角形，W4 同分辨率样本有 26 个调用及约 2.8 万三角形。

[W0 海湾默认视角](evidence/w0-default.jpg) · [W0 镜像触控](evidence/w0-mirror.jpg) · [W1 船道默认视角](evidence/w1-default.jpg) · [W1 低画质回望](evidence/w1-orbit.jpg) · [W2 全深渔网](evidence/w2-default.jpg) · [W2 低画质回望](evidence/w2-orbit.jpg) · [W3 两条航道](evidence/w3-branch.jpg) · [W4 水面汇合](evidence/w4-gathering.jpg)

### 自动化结果

- 当前 `npm run check` 全部通过，共 129 项 Vitest 用例。
- 鲸篇集成的 28 项包含逐 tick 浮潜、30／60／120 FPS 重放、三层扫掠、低呼吸补救、W3 航道量测与边界重选，以及两类失败回档。
- 启用鲸篇的预览构建在 Chromium、桌面 WebKit 和横屏 WebKit 共通过 42 项 Playwright 用例，3 项按平台跳过。更新分航段的性能采样后，三种配置均通过 W4 专项，确认汇合期间模拟 tick 保持冻结且画面仍提供帧时、绘制调用和三角形诊断数据。
- 三种浏览器配置以固定步做 W0 A/B 对照。持续左推后拖镜，A 的领鲸随镜头偏航约 0.72 弧度，B 保持初始航向。两种映射在同一输入样本都滑行约 6.01 单位停稳，复位未改变领鲸位置和航向。身体操作疲劳与主观恢复时间待真机试航。[Chromium](evidence/w0-mapping-chromium.json) · [桌面 WebKit](evidence/w0-mapping-desktop-webkit.json) · [横屏 WebKit](evidence/w0-mapping-mobile-webkit.json)
- 鲸篇专门复测 C1 救援超时与 C2 能量耗尽的重试入口，核对重试瞬间完整快照、满能量和默认镜头。两个标签页共享 IndexedDB 时，旧航程抵达不能覆盖另一标签页的较新记录。不兼容的存档显示明确的新航程入口。
- 默认生产构建完整重跑 `npm run test:e2e -- --workers=3`，139 项通过、58 项跳过。跳过项包含未启用鲸篇入口的 45 项鲸用例及 13 项平台用例。已固定原 Chromium S4 截图用例的测试时钟，完整重跑通过。

WH-Q01～Q04 的实机部分仍需真实 iPhone 和 iPad Safari 横屏。首次玩家试航、A/B 手感选择、真实设备性能与海面观景节奏见[真机试玩单](05-real-device-handoff.md)。视图截图与回放用的时间值来自浏览器仿真或固定步，供复核操作与规则。
