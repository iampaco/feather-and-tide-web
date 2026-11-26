import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
import { whaleGuidance } from "../../src/app/whale-guidance";
import type { WhaleActor } from "../../src/core/game";
import { contains, sweptCircle } from "../../src/levels/geometry";
import { isWhaleNet } from "../../src/levels/whale-geometry";
import { WHALE } from "../../src/simulation/whale-motion";
import { validateLevel } from "../../src/levels/schema";
import { initialWhaleState } from "../../src/simulation/whale-world";

const source = JSON.parse(readFileSync("public/levels/whale.json", "utf8"));
const level = validateLevel(source, "whale fixture", "whale");
const initial = initialWhaleState(level, "journey");
const view = {
  dragged: false,
  reset: false,
  moved: false,
  stopped: false,
  submerged: false,
  recovered: false,
  toggle: false,
  desktop: true,
};
const move = (actor: WhaleActor, x: number, z: number): WhaleActor => ({
  ...actor,
  pos: { x, z },
});
const w1 = initial.actors.map((actor, i) => move(actor, 0, 381 - 3 * i));

test("W0 teaches unfinished actions even after an early dive and can be skipped", () => {
  const earlyDive = {
    ...view,
    submerged: true,
    recovered: true,
    moveKey: "IJKL",
  };
  expect(whaleGuidance(initial, level, true, earlyDive).notice).toContain(
    "IJKL",
  );
  expect(
    whaleGuidance(initial, level, true, { ...earlyDive, moved: true }).notice,
  ).toContain("滑行");
  const almostDone = {
    ...earlyDive,
    moved: true,
    stopped: true,
    dragged: true,
  };
  expect(
    whaleGuidance(initial, level, true, { ...almostDone, resetKey: "F" })
      .notice,
  ).toBe("按 F 复位镜头");
  expect(
    whaleGuidance(initial, level, true, { ...almostDone, reset: true })
      .tutorial,
  ).toBe(false);
  expect(whaleGuidance(initial, level, false, view).notice).toBe("");
  expect(whaleGuidance(initial, level, false, view).markers).toMatchObject([
    { id: "bay-exit", label: "出湾航标" },
  ]);
  expect(whaleGuidance(initial, level, true, view).markers).toMatchObject([
    { id: "bay-bend-entry", label: "海蚀拱内湾 · 练习滑停" },
    { id: "bay-exit", label: "出湾航标" },
  ]);
  expect(
    whaleGuidance(initial, level, true, {
      ...almostDone,
      reset: true,
      submerged: false,
      recovered: false,
      toggle: true,
      desktop: false,
    }).notice,
  ).toBe("点按 下潜键 试试浅潜");
});

test("W0 shows an early dive, the actual ascending companion and the breath check", () => {
  const leader = initial.actors[0];
  const tail = initial.actors.at(-1);
  if (!leader || !tail) throw new Error("Missing test pod");
  const submerged = { ...view, submerged: true, toggle: true, desktop: false };
  const shallow = {
    ...initial,
    actors: [
      { ...leader, dive: { ...leader.dive, layer: "shallow", depth: 1 } },
      ...initial.actors.slice(1),
    ],
  } as const;
  expect(whaleGuidance(shallow, level, true, submerged).notice).toBe(
    "再点按 下潜键 上浮",
  );
  const waiting = {
    ...initial,
    actors: [
      { ...leader, dive: { ...leader.dive, breath: 0.98 } },
      ...initial.actors.slice(1, -1),
      {
        ...tail,
        dive: { ...tail.dive, layer: "shallow", direction: "up", depth: 0.4 },
      },
    ],
  } as const;
  const atSurface = whaleGuidance(waiting, level, true, submerged);
  expect(atSurface.notice).toBe("领鲸已浮出水面");
  expect(atSurface.depthCue).toBe("正在换气");
  expect(atSurface.markers).toContainEqual({
    id: tail.id,
    kind: "gathering",
    pos: tail.pos,
    depth: 0.4,
    label: "队尾 · 正在上浮",
  });
  const breathing = {
    ...waiting,
    actors: [...waiting.actors.slice(0, -1), tail],
  };
  expect(whaleGuidance(breathing, level, true, submerged).detail).toContain(
    "呼吸条回满",
  );
  const ready = {
    ...submerged,
    moved: true,
    stopped: true,
    dragged: true,
    reset: true,
    recovered: true,
  };
  expect(whaleGuidance(initial, level, true, ready).notice).toBe("可以出湾了");
});

test("W0 previews optional flow and the real ship direction after skipping the lesson", () => {
  const at = (x: number, z: number, tick: number, occupied: string[] = []) =>
    whaleGuidance(
      {
        ...initial,
        tick,
        occupied,
        actors: initial.actors.map((actor, index) =>
          move(actor, x, z - index * 3),
        ),
      },
      level,
      false,
      view,
    );
  const fork = at(0, 126, 500);
  expect(fork.markers).toEqual(
    expect.arrayContaining([
      expect.objectContaining({ id: "bay-surface-turn" }),
      expect.objectContaining({ id: "current-entry", pos: { x: 21, z: 145 } }),
    ]),
  );
  expect(at(21, 166, 750).notice).toBe("沿礁借流");
  expect(at(21, 166, 750, ["bay-current"]).notice).toBe("正在借流");
  const east = at(0, 218, 1200);
  const west = at(0, 218, 3310);
  expect(east.danger).toBe("");
  expect(west.danger).toBe("");
  expect(east.markers).toContainEqual(
    expect.objectContaining({
      id: "cargo-ship",
      label: "湾外货船 · 向东",
      kind: "hazard",
    }),
  );
  expect(west.markers).toContainEqual(
    expect.objectContaining({
      id: "cargo-ship",
      label: "湾外货船 · 向西",
      kind: "hazard",
    }),
  );
});

test("W0 bright water identifies the actual submerged tail after skipping teaching", () => {
  const actors = initial.actors.map((actor, index) =>
    move(actor, 14, 218 - index * 3),
  );
  const tail = actors.at(-1);
  if (!tail) throw new Error("Missing test pod");
  const cue = whaleGuidance(
    {
      ...initial,
      actors: [
        ...actors.slice(0, -1),
        {
          ...tail,
          dive: { ...tail.dive, layer: "shallow", direction: "up", depth: 0.4 },
        },
      ],
    },
    level,
    false,
    view,
  );
  expect(cue.notice).toBe("湾口亮水");
  expect(cue.markers).toContainEqual({
    id: tail.id,
    label: "队尾 · 正在上浮",
    pos: tail.pos,
    depth: 0.4,
    kind: "gathering",
  });
});

test("shows the effective layer during forced ascent and explains the toggle lock", () => {
  const leader = initial.actors[0];
  if (!leader) throw new Error("Missing test whale");
  const state = {
    ...initial,
    actors: [
      {
        ...leader,
        dive: {
          ...leader.dive,
          layer: "deep",
          direction: "up",
          forced: true,
          depth: 1.7,
          breath: 0,
        },
      },
      ...initial.actors.slice(1),
    ],
  } as const;
  const ascent = whaleGuidance(state, level, false, view);
  expect(ascent.depthLabel).toBe("深潜");
  expect(ascent.depthCue).toContain("呼吸耗尽");
  const locked = {
    ...initial,
    actors: [
      { ...leader, dive: { ...leader.dive, needsRelease: true, breath: 0.12 } },
      ...initial.actors.slice(1),
    ],
  };
  expect(
    whaleGuidance(locked, level, false, { ...view, toggle: true }).depthCue,
  ).toBe("关闭下潜，换气后再开启");
});

test("keeps ship layer warning and moving marker available", () => {
  const first = whaleGuidance(
    { ...initial, actors: w1, segmentId: "W1", tick: 500 },
    level,
    false,
    view,
  );
  const later = whaleGuidance(
    { ...initial, actors: w1, segmentId: "W1", tick: 600 },
    level,
    false,
    view,
  );
  expect(first.danger).toMatch(/水面／浅潜受阻/);
  expect(first.markers.find(({ id }) => id === "cargo-ship")?.pos.x).not.toBe(
    later.markers.find(({ id }) => id === "cargo-ship")?.pos.x,
  );
});

test("W1 announces the occupied layers from the waiting water before the warning edge", () => {
  const actors = initial.actors.map((actor, i) => move(actor, 100, 277 - i));
  const guidance = whaleGuidance(
    { ...initial, actors, segmentId: "W1" },
    level,
    false,
    view,
  );
  expect(guidance.danger).toContain("水面／浅潜受阻");
  expect(guidance.warningDetail).toContain("减速让船先过");
  expect(guidance.markers.some(({ id }) => id === "ship-wait")).toBe(true);
});

test("W1 previews both net approaches once the pod has saved at C1", () => {
  const crossing = {
    ...initial,
    actors: initial.actors.map((actor, i) => move(actor, 0, 518 - 4 * i)),
    segmentId: "W1",
    occupied: ["crossing-rest", "C1"],
  } as const;
  const waiting = whaleGuidance(crossing, level, false, view);
  expect(waiting.notice).toBe("检查点 1");
  expect(waiting.markers.map(({ id }) => id)).not.toContain(
    "net-preview-short",
  );

  const preview = whaleGuidance(
    { ...crossing, triggered: ["C1"] },
    level,
    false,
    view,
  );
  expect(preview.notice).toBe("前方渔网 · 两条路线可绕行");
  expect(preview.markers.map(({ id }) => id)).toEqual([
    "net-preview-short",
    "net-preview-wide",
  ]);
});

test.each([
  [389, "waiting-water", false],
  [410, "waiting-water", true],
  [427, "crossing-rest", true],
  [444, "crossing-rest", true],
] as const)(
  "W1 guides a low-breath pod at z=%s toward %s across different ship phases",
  (z, zoneId, podInPassage) => {
    const actors = initial.actors.map((actor, index) => ({
      ...move(actor, 35, z - 3 * index),
      dive: { ...actor.dive, layer: "deep", depth: 2, breath: 0.12 } as const,
    }));
    const zone = level.zones.find(({ id }) => id === zoneId);
    if (!zone) throw new Error("Missing test water");
    for (const tick of [500, 3000, 5000]) {
      const guidance = whaleGuidance(
        { ...initial, actors, segmentId: "W1", tick },
        level,
        false,
        view,
      );
      const mark = guidance.markers.find(({ id }) => id === "whale-refill");
      if (!mark) throw new Error("Missing refill marker");
      expect(contains(zone.points, mark.pos)).toBe(true);
      expect(mark.pos.x).toBe(35);
      expect(guidance.markers.some(({ kind }) => kind === "route")).toBe(false);
      expect(guidance.detail.includes("游离船道")).toBe(podInPassage);
    }
  },
);

test("W1 tells a deep lead whale to wait for a shallow tail before advancing", () => {
  const actors = w1.map((actor, index) => ({
    ...actor,
    dive: {
      ...actor.dive,
      layer: index === 5 ? "shallow" : "deep",
      depth: index === 5 ? 1 : 2,
    } as const,
  }));
  const guidance = whaleGuidance(
    { ...initial, actors, segmentId: "W1" },
    level,
    false,
    view,
  );
  expect(guidance.warningDetail).toContain("队尾仍在浅潜");
  expect(guidance.markers).toContainEqual({
    id: "whale-5",
    label: "队尾 · 浅潜",
    kind: "gathering",
    pos: actors[5]?.pos,
    depth: 1,
  });
});

test("W1 shows a surface opening only if the ship stays clear of the pod's crossing", () => {
  const stage = (x: number, tick: number) =>
    whaleGuidance(
      {
        ...initial,
        segmentId: "W1",
        tick,
        actors: w1.map((actor) => move(actor, x + actor.pos.x, actor.pos.z)),
      },
      level,
      false,
      view,
    );
  expect(stage(0, 3310).warningDetail).toContain("减速让船先过");
  expect(stage(0, 4050).warningDetail).toContain("前方有水面空档");
  expect(stage(0, 950).warningDetail).toContain("前方有水面空档");
  expect(
    stage(0, 4050).markers.find(({ id }) => id === "cargo-ship")?.label,
  ).toBe("货船 · 向西");
  expect(
    stage(0, 950).markers.find(({ id }) => id === "cargo-ship")?.label,
  ).toBe("货船 · 向东");
  expect(stage(75, 2000).warningDetail).toContain("减速让船先过");
});

test("W1 keeps the deep route cue until even the trailing whale leaves the band", () => {
  const stage = (tailZ: number) =>
    whaleGuidance(
      {
        ...initial,
        segmentId: "W1",
        occupied: ["ship-approach"],
        actors: w1.map((actor, i) => ({
          ...move(actor, 0, i === 5 ? tailZ : 458 - 4 * i),
          dive: { ...actor.dive, layer: "deep", depth: 2 } as const,
        })),
      },
      level,
      false,
      view,
    );
  expect(stage(402).warningDetail).toContain("保持深潜");
  expect(stage(428).warningDetail).toContain("保持深潜");
  expect(stage(431).warningDetail).toContain("全队已过船道");
});

test("W1 only suggests deep departure when the last whale has enough breath for the crossing", () => {
  const stage = (tailBreath: number) =>
    whaleGuidance(
      {
        ...initial,
        segmentId: "W1",
        actors: w1.map((actor, i) => ({
          ...actor,
          dive: {
            ...actor.dive,
            layer: "deep",
            depth: 2,
            breath: i === 5 ? tailBreath : 1,
          },
        })),
      },
      level,
      false,
      view,
    );
  expect(stage(0.36).warningDetail).toContain("先在船道外集队换气");
  expect(stage(0.8).warningDetail).toContain("可向前起游");
});

test("W1 counts actual clearances even if the leader reaches static water early", () => {
  const actors = w1.map((actor, i) => move(actor, 0, i === 2 ? 330 : 460 - i));
  const guidance = whaleGuidance(
    { ...initial, actors, segmentId: "W1", occupied: ["crossing-rest"] },
    level,
    false,
    view,
  );
  expect(guidance.warningDetail).toContain("已清船 5/6");
  expect(guidance.notice).not.toBe("船后静水");
  expect(guidance.markers).toContainEqual(
    expect.objectContaining({
      id: "whale-2",
      label: "队尾 · 尚未清船",
    }),
  );
});

test("C1 explains that the entire pod has to surface before saving", () => {
  const actors = initial.actors.map((actor, i) => ({
    ...move(actor, 0, 515 - i),
    dive:
      i === 5
        ? { ...actor.dive, layer: "shallow" as const, depth: 1 }
        : actor.dive,
  }));
  const guidance = whaleGuidance(
    { ...initial, actors, segmentId: "W1" },
    level,
    false,
    view,
  );
  expect(guidance.notice).toBe("检查点 1");
  expect(guidance.detail).toBe("水面就绪 5/6 · 保持在水面，等全队上浮后保存");
  expect(guidance.markers).toContainEqual({
    id: "whale-5",
    label: "同伴 · 浅潜",
    kind: "gathering",
    pos: actors[5]?.pos,
    depth: 1,
  });
});
test("marks both real W3 crossing gates before the branch", () => {
  const actors = initial.actors.map((actor, i) => move(actor, 0, 1012 - 3 * i));
  const guidance = whaleGuidance(
    { ...initial, actors, segmentId: "W3" },
    level,
    false,
    view,
  );
  expect(guidance.markers.map(({ pos }) => pos.z)).toEqual([1040, 1040]);
  expect(guidance.detail).toContain("噪声会拉开队伍");
});

test("W3 reports the actual route and cohesion, and shows both gates again on return", () => {
  const entered = {
    ...initial,
    actors: initial.actors.map((actor) => move(actor, 56, 1100)),
    segmentId: "W3",
    route: "shipping",
    occupied: ["shipping-noise"],
    cohesion: 0.91,
  } as const;
  const shipping = whaleGuidance(entered, level, false, view);
  expect(shipping.notice).toBe("噪声影响各水层");
  expect(shipping.detail).toContain("等队尾收拢");
  expect(shipping.routeCohesion).toBe(0.91);
  const returned = whaleGuidance(
    {
      ...entered,
      actors: entered.actors.map((actor) => move(actor, 20, 1000)),
      occupied: ["junction-rest"],
    },
    level,
    false,
    view,
  );
  expect(returned.notice).toContain("可重新越线选路");
  expect(returned.markers.map(({ id }) => id)).toEqual([
    "shipping-entry",
    "quiet-entry",
  ]);
});

test("C2 remains the navigation target when entering W4 before saving", () => {
  const guidance = whaleGuidance(
    {
      ...initial,
      actors: initial.actors.map((actor) => move(actor, -20, 1330)),
      segmentId: "W4",
      route: "quiet",
      routeLocked: true,
    },
    level,
    false,
    view,
  );
  expect(guidance.markers.map(({ id }) => id)).toEqual(["second-checkpoint"]);
});

test("W2 reports the current rescue step, depth, timer and actual progress", () => {
  const leader = initial.actors[0];
  const tail = initial.actors.at(-1);
  if (!leader || !tail) throw new Error("Missing test whales");
  const lost: WhaleActor = {
    ...move(tail, 95, 828),
    status: "strayed",
    rescueTicks: 1800,
    rescueProgress: 30,
  };
  const stage = (actor: WhaleActor) =>
    whaleGuidance(
      {
        ...initial,
        actors: [actor, ...initial.actors.slice(1, -1), lost],
        segmentId: "W2",
      },
      level,
      false,
      view,
    );
  expect(stage(move(leader, 95, 844)).detail).toContain("减速折返");
  const near = move(leader, 95, 830);
  expect(
    stage({ ...near, dive: { ...leader.dive, layer: "shallow", depth: 1 } })
      .detail,
  ).toContain("同层");
  expect(stage({ ...near, speed: 4 }).detail).toBe(
    "松开方向键停稳，等接应开始",
  );
  const ready = stage(near);
  expect(ready.detail).toBe("保持同层低速，等接应进度完成");
  expect(ready.rescue).toEqual({ ticks: 1800, progress: 0.25 });
  expect(ready.markers).toContainEqual(
    expect.objectContaining({ id: "whale-rescue", pos: lost.pos, depth: 0 }),
  );
});

test("W2 returns a clear first recovery leg when the divider separates two whales", () => {
  const actors = initial.actors.map((actor, i) =>
    i === 4
      ? {
          ...move(actor, 124, 761),
          status: "strayed" as const,
          rescueTicks: 1800,
        }
      : move(actor, 75, 761 - 3 * i),
  );
  const leader = actors[0];
  if (!leader) throw new Error("Missing leader");
  const guide = whaleGuidance(
    { ...initial, actors, segmentId: "W2" },
    level,
    false,
    view,
  );
  const detour = guide.markers.find(({ id }) => id === "rescue-net-detour");
  expect(detour).toBeDefined();
  if (!detour) throw new Error("Missing rescue detour");
  expect(detour.pos.z < 748 || detour.pos.z > 774).toBe(true);
  expect(
    level.zones
      .filter(isWhaleNet)
      .every(
        ({ points }) =>
          !sweptCircle(points, leader.pos, detour.pos, WHALE.hitRadius),
      ),
  ).toBe(true);
});

test("W2 shows safe approaches to both paths and tracks the actual whale still on the far side", () => {
  const stage = (x: number, z: number) =>
    whaleGuidance(
      {
        ...initial,
        segmentId: "W2",
        triggered: ["C1"],
        actors: initial.actors.map((actor, i) => move(actor, x, z - 3 * i)),
      },
      level,
      false,
      view,
    );
  const fork = stage(38, 650);
  expect(fork.notice).toBe("选择绕网路线");
  expect(fork.markers.map(({ id }) => id)).toEqual([
    "net-short-entry",
    "net-wide-entry",
  ]);
  const early = stage(20, 716);
  expect(early.warningDetail).toContain("先对准再缓游");
  expect(early.markers).toContainEqual(
    expect.objectContaining({ id: "net-gap", pos: { x: 75, z: 716 } }),
  );
  expect(early.markers.map(({ id }) => id)).toContain("net-wide");
  expect(stage(20, 746).markers[0]?.pos.z).toBeLessThan(745);
  const aligned = stage(75, 740);
  expect(aligned.notice).toBe("选择绕网路线");
  expect(aligned.markers[0]?.id).toBe("net-gap");
  const beforeTurn = stage(75, 764);
  expect(beforeTurn.notice).toBe("已清网 0/6");
  expect(beforeTurn.detail).toBe("先直游或缓行，等队尾清网再转向");
  expect(beforeTurn.rescue).toBeNull();
  expect(beforeTurn.markers).toEqual([
    expect.objectContaining({ id: "whale-5", pos: { x: 75, z: 749 } }),
    expect.objectContaining({ id: "net-runout-cue", pos: { x: 75, z: 807 } }),
  ]);
  expect(stage(96, 764).markers.some(({ id }) => id === "net-runout-cue")).toBe(
    false,
  );
  const clearing = stage(124, 787);
  expect(clearing.notice).toBe("已清网 4/6");
  expect(clearing.markers).toEqual([
    expect.objectContaining({ id: "whale-5", pos: { x: 124, z: 772 } }),
    expect.objectContaining({ id: "net-runout-cue", pos: { x: 124, z: 807 } }),
  ]);
  expect(
    stage(124, 825).markers.some(({ id }) => id === "net-runout-cue"),
  ).toBe(false);
});

test("W2 tracks the rejoining whale until it is back and restores the route toward W3", () => {
  const stage = (status: "rejoining" | "following") =>
    whaleGuidance(
      {
        ...initial,
        segmentId: "W2",
        triggered: ["C1"],
        actors: initial.actors.map((actor, i) => ({
          ...move(actor, 98, 846 - 3 * i),
          status: i === 5 ? status : "following",
        })),
      },
      level,
      false,
      view,
    );
  const returning = stage("rejoining");
  expect(returning.notice).toBe("同伴正在归队");
  expect(returning.rescue).toBeNull();
  expect(returning.markers).toContainEqual(
    expect.objectContaining({
      id: "whale-5",
      kind: "gathering",
      label: "同伴 · 正在归队",
    }),
  );
  const back = stage("following");
  expect(back.notice).toBe("海藻湾");
  expect(back.detail).toContain("也可直去分岔");
  expect(back.markers.map(({ id }) => id)).toEqual([
    "kelp-short-bend",
    "kelp-arc-bend",
  ]);
});

test("W2 reports actual bay occupancy and the shared supply condition", () => {
  const stage = (
    count: number,
    options: { energy?: number; supply?: number; submerged?: boolean } = {},
  ) => {
    const { energy = 0.6, supply = 0.3, submerged = false } = options;
    return whaleGuidance(
      {
        ...initial,
        segmentId: "W2",
        energy,
        supply: { ...initial.supply, "net-kelp": supply },
        actors: initial.actors.map((actor, i) => ({
          ...move(actor, i < count ? 39 : 72, 875),
          dive:
            i === 0 && submerged
              ? { ...actor.dive, layer: "shallow", depth: 1 }
              : actor.dive,
        })),
      },
      level,
      false,
      view,
    );
  };
  const waiting = stage(3);
  expect(waiting.detail).toBe("进湾 3/6 · 缓游等队尾，至少 4 只进湾才补给");
  expect(waiting.markers).toContainEqual(
    expect.objectContaining({ id: "whale-5", label: "队尾 · 尚未进湾" }),
  );
  expect(stage(4).detail).toBe("进湾 4/6 · 正在补给");
  expect(stage(4, { submerged: true }).detail).toContain("上浮后可补给");
  expect(stage(6, { energy: 1 }).detail).toBe("进湾 6/6 · 能量已满");
  expect(stage(6, { supply: 0 }).detail).toBe("进湾 6/6 · 补给已用完");
});

test("keeps a submerged tail out of W4 arrival", () => {
  const actors = initial.actors.map((actor, i) => {
    const row = move(actor, 80, 1560 - 3 * i);
    return i === 5
      ? ({ ...row, dive: { ...row.dive, layer: "shallow", depth: 1 } } as const)
      : row;
  });
  const guidance = whaleGuidance(
    { ...initial, actors, segmentId: "W4" },
    level,
    false,
    view,
  );
  expect(guidance.arrival).toEqual({
    visible: true,
    caption: "等待同伴上浮",
    count: "5/6",
    detail: "在水面等候，可转镜观察同伴",
  });
  expect(guidance.markers).toEqual([
    {
      id: "whale-5",
      kind: "gathering",
      label: "同伴 · 浅潜",
      pos: actors[5]?.pos,
      depth: 1,
    },
  ]);
});

test("W4 prioritizes rescue, then regrouping and spatial arrival", () => {
  const actors = initial.actors.map((actor, index) =>
    move(actor, 80, index === 5 ? 1513 : 1560 - 3 * index),
  );
  const state = { ...initial, actors, segmentId: "W4" } as const;
  expect(whaleGuidance(state, level, false, view).arrival).toMatchObject({
    caption: "等待同伴进入汇合区",
    count: "5/6",
  });
  const tail = actors.at(-1);
  if (!tail) throw new Error("Missing test whale");
  const ascending = {
    ...tail,
    dive: { ...tail.dive, direction: "up", layer: "shallow", depth: 0.8 },
  } as const;
  const outside = whaleGuidance(
    { ...state, actors: [...actors.slice(0, -1), ascending] },
    level,
    false,
    view,
  );
  expect(outside.arrival.caption).toBe("等待同伴进入汇合区");
  expect(outside.arrival.detail).toBe("已停稳 · 可转镜看队尾入区");
  expect(outside.markers).toContainEqual({
    id: tail.id,
    kind: "gathering",
    label: "同伴 · 仍在区外",
    pos: tail.pos,
    depth: 0.8,
  });
  const inside = whaleGuidance(
    { ...state, actors: [...actors.slice(0, -1), move(ascending, 80, 1535)] },
    level,
    false,
    view,
  );
  expect(inside.arrival.caption).toBe("等待同伴上浮");
  expect(inside.markers[0]?.label).toBe("同伴 · 正在上浮");
  for (const [status, caption] of [
    ["rejoining", "等待同伴归队"],
    ["strayed", "仍有同伴待接应"],
  ] as const) {
    const staged = {
      ...state,
      actors: actors.map((actor, index) =>
        index === 5
          ? {
              ...actor,
              status,
              rescueTicks: status === "strayed" ? 600 : null,
              dive: { ...actor.dive, layer: "deep" as const, depth: 2 },
            }
          : actor,
      ),
    };
    const cues = whaleGuidance(staged, level, false, view);
    expect(cues.arrival).toMatchObject({
      caption,
      count: "5/6",
    });
    expect(cues.markers.some(({ kind }) => kind === "gathering")).toBe(false);
  }
});

test("W3 shows the upcoming turn and counts only surfaced pod members inside the eddy", () => {
  const stage = { ...initial, segmentId: "W3", route: "quiet" } as const;
  const riding = whaleGuidance(
    {
      ...stage,
      occupied: ["reef-current"],
      actors: initial.actors.map((actor, i) => move(actor, -78, 1168 - i * 3)),
    },
    level,
    false,
    view,
  );
  expect(riding.notice).toBe("正在借流 · 第一段顺流");
  expect(riding.markers).toEqual(
    expect.arrayContaining([
      expect.objectContaining({ id: "current-eddy-entry", kind: "supply" }),
      expect.objectContaining({ id: "reef-current-east-entry", kind: "route" }),
    ]),
  );
  expect(riding.detail).toContain("上浮等队尾");
  const rested = initial.actors.map((actor, i) =>
    move(actor, -68, 1205 - i * 4),
  );
  const arriving = rested.map((actor, i) =>
    i === 5
      ? ({
          ...actor,
          dive: { ...actor.dive, layer: "shallow", depth: 1, breath: 0.17 },
        } as const)
      : actor,
  );
  const waiting = whaleGuidance(
    { ...stage, actors: arriving },
    level,
    false,
    view,
  );
  expect(waiting.notice).toBe("礁间静水");
  expect(waiting.detail).toContain("水面就绪 5/6");
  expect(waiting.markers).toContainEqual(
    expect.objectContaining({ id: "whale-5", label: "队尾 · 尚未上浮" }),
  );
  expect(
    whaleGuidance({ ...stage, actors: rested }, level, false, view).detail,
  ).toContain("水面就绪 6/6");
});

test("W4 previews both breakwater routes and keeps the offshore current on the wide side", () => {
  const state = {
    ...initial,
    segmentId: "W4",
    triggered: ["C1", "C2"],
    route: "quiet",
    routeLocked: true,
  } as const;
  const guidanceAt = (z: number, x = 68, occupied: string[] = []) =>
    whaleGuidance(
      {
        ...state,
        occupied,
        actors: initial.actors.map((actor) => move(actor, x, z)),
      },
      level,
      false,
      view,
    );
  const fromC2 = guidanceAt(1343, 68, ["C2"]);
  expect(fromC2.notice).toBe("驶向外海");
  expect(fromC2.markers.map(({ id }) => id)).toEqual(["surface-here"]);
  const approach = guidanceAt(1392);
  expect(approach.notice).toBe("防波堤横流");
  expect(approach.markers.map(({ id }) => id)).toEqual([
    "breakwater-cross",
    "breakwater-wide",
  ]);
  const wide = guidanceAt(1392, 97);
  expect(wide.notice).toBe("外海顺流带");
  expect(wide.markers.map(({ id }) => id)).toEqual([
    "current-entry",
    "surface-here",
  ]);
  const crossing = guidanceAt(1431);
  expect(crossing.notice).toBe("正在穿越横流");
  expect(crossing.markers.map(({ id }) => id)).toEqual(["breakwater-clear"]);
  const quiet = guidanceAt(1480, 68, ["offshore-rest"]);
  expect(quiet.notice).toBe("观鲸船减速区 · 水面 6/6");
  expect(quiet.detail).toContain("滑停等队尾");
  expect(quiet.markers.map(({ id }) => id)).toEqual(["watching-coast"]);
  expect(guidanceAt(1514).markers.map(({ id }) => id)).toEqual([
    "offshore-marker",
  ]);
});

test("W4 reports actual surfaced whales at the watching reach without triggering gathering", () => {
  const actors = initial.actors.map((actor, index) =>
    move(actor, 97, index === 5 ? 1458 : 1487),
  );
  const guidance = whaleGuidance(
    { ...initial, actors, segmentId: "W4", triggered: ["C1", "C2"] },
    level,
    false,
    view,
  );
  expect(guidance.notice).toBe("观鲸船减速区 · 水面 5/6");
  expect(guidance.markers.at(-1)).toMatchObject({
    id: actors[5]?.id,
    pos: { x: 97, z: 1458 },
  });
  expect(guidance.arrival.visible).toBe(false);
});

test("only the near W3 route previews the two dredging passages", () => {
  const state = {
    ...initial,
    actors: initial.actors.map((actor) => move(actor, 65, 1158)),
    segmentId: "W3",
    route: "shipping",
    triggered: ["C1", "ship-gate"],
  } as const;
  const shipping = whaleGuidance(state, level, false, view);
  expect(shipping.notice).toBe("港口疏浚区");
  expect(shipping.markers.map(({ id }) => id)).toEqual([
    "shipping-supply",
    "dredge-surface-entry",
    "dredge-clear-entry",
  ]);
  const quiet = whaleGuidance({ ...state, route: "quiet" }, level, false, view);
  expect(quiet.markers.every(({ id }) => !id.startsWith("dredge-"))).toBe(true);
});

test("W4 asks for more room if the pod's resting slots still cross the entrance", () => {
  const guide = whaleGuidance(
    {
      ...initial,
      actors: initial.actors.map((actor, i) => move(actor, 80, 1520 - i * 3)),
      segmentId: "W4",
    },
    level,
    false,
    view,
  );
  expect(guide.arrival).toMatchObject({
    caption: "等待同伴进入汇合区",
    count: "1/6",
    detail: "向亮水中央再游，给同伴留出空间，再松手滑停",
  });
  expect(guide.markers[0]?.label).toBe("同伴 · 仍在区外");
});
