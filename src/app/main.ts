import { copy, isEnglish, levelLabel, levelTitle } from "../i18n/language";
import { reindeerGatherStatus } from "../simulation/reindeer-care";
import {
  reindeerDustGuidance,
  reindeerLandingCompanion,
  reindeerPassageGuidance,
  reindeerTeammateGuidance,
  reindeerWinterBend,
  reindeerWinterTail,
} from "./reindeer-guidance";
import { FixedClock, STEP_SEC } from "../core/clock";
import type {
  CheckpointSnapshot,
  GameEvent,
  GameMode,
  ReindeerState,
  Route,
  Species,
  WhaleState,
} from "../core/game";
import { distance, type Vec2 } from "../core/math";
import { GameRuntime } from "../core/runtime";
import { readCheckpoint, readRunRecord, SaveStore } from "../core/save";
import { soundtrack } from "../audio/media";
import { MusicDirector } from "../audio/music";
import {
  DEFAULT_SETTINGS,
  InputManager,
  type InputSettings,
} from "../input/input";
import { keyLabel, movementLabel, readBindings } from "../input/keyboard";
import { contains } from "../levels/geometry";
import { loadLevel } from "../levels/load";
import {
  tailwindCourseMarks,
  tailwindPractice,
  tailwindPracticeId,
} from "../levels/tailwind-practice";
import type {
  AnyLevelSchema,
  LevelSchema,
  ReindeerLevel,
  WhaleLevel,
} from "../levels/schema";
import { gooseLandingWait, gooseRescue } from "../rendering/goose-companions";
import type { ReindeerScene } from "../rendering/reindeer-scene";
import {
  onRoad,
  insideCulvert,
  roadVehicle,
  vehicleDirection,
} from "../levels/reindeer-ground";
import { hazardPoints } from "../levels/moving-hazard";
import { REINDEER } from "../simulation/reindeer-tuning";
import type { WhaleScene } from "../rendering/whale-scene";
import {
  FlightScene,
  loadFlightAssets,
  type FlightAssets,
} from "../rendering/scene";
import { GOOSE, rescueApproach } from "../simulation/goose";
import { goalStatus, leaderOf } from "../simulation/world";
import { surfaced } from "../simulation/world-rules";
import { setupDesktopSettings } from "./desktop-settings";
import { setupLanguagePicker } from "./language-picker";
import {
  gooseCrosswindApproach,
  gooseCrosswindPickup,
  gooseHazardCue,
  gooseLandingApproach,
  gooseRouteCue,
  gooseSupplyCue,
  gooseTailwindCue,
  gooseWindfarmOptions,
  supplyAvailable,
  type CrosswindPickup,
} from "./flight-guidance";
import { GooseMarkerLayout, type GooseMarkerKind } from "./goose-marker-layout";
import { gooseStamina, screenDirection } from "./goose-hud";
import { gooseGustCue, isGooseGustLandmark } from "./goose-gust-guidance";
import {
  freshGooseTeaching,
  gooseTeaching,
  gooseTurnLessonEnd,
  gooseTurnLessonStart,
} from "./goose-teaching";
import { whaleGuidance } from "./whale-guidance";
import { WHALE } from "../simulation/whale-motion";
import "./ui-tokens.css";
import "./style.css";
import "./flight-hud.css";

function element<T extends HTMLElement>(id: string): T {
  const node = document.getElementById(id);
  if (!node) throw new Error(`Missing #${id}`);
  return node as T;
}

const canvas = document.querySelector("canvas");
if (!canvas) throw new Error("Missing canvas");

const game = element("game");
const menu = element("menu");
const titleMenu = element("title-menu");
const speciesMenu = element("species-menu");
const speciesChoices = element("species-choices");
const menuActions = element("menu-actions");
const enterGame = element<HTMLButtonElement>("enter-game");
const speciesBack = element<HTMLButtonElement>("species-back");
const gooseEntry = element<HTMLButtonElement>("goose-entry");
const gooseContinue = element<HTMLButtonElement>("goose-continue");
const gooseAction = element("goose-action");
const menuMessage = element("menu-message");
const titleMessage = element("title-message");
const speciesMessage = element("species-message");
const bootStatus = element("boot-status");
const retryLoad = element<HTMLButtonElement>("retry-load");
const soundtrackDialog = element<HTMLDialogElement>("soundtrack");
const soundtrackTrack = element<HTMLSelectElement>("soundtrack-track");
const soundtrackPlayer = element<HTMLAudioElement>("soundtrack-player");
const soundtrackStatus = element("soundtrack-status");
const hud = element("hud");
const panel = element<HTMLDialogElement>("panel");
const settingsDialog = element<HTMLDialogElement>("settings");
const sensitivityValue = element<HTMLOutputElement>("sensitivity-value");
const panelActions = element("panel-actions");
const panelPlace = element("panel-place");
const panelSummary = element("panel-summary");
const panelNote = element("panel-note");
const hazardCue = element("hazard-cue");
const hazardNotice = element("hazard-notice");
const warningDetail = element("warning-detail");
const flightCue = element("flight-cue");
const notice = element("notice");
const detail = element("detail");
const rescueClock = element("rescue-clock");
const rescueSeconds = element("rescue-seconds");
const energy = element<HTMLProgressElement>("energy");
const energyStatus = element("energy-status");
const energyPercent = element("energy-percent");
const energyLabel = element("energy-label");
const energyCondition = element("energy-condition");
const ability = element<HTMLButtonElement>("formation");
const formationLabel = element("formation-label");
const formationStatus = element("formation-status");
const markerLayer = element("marker-layer");
const flightInformation = element("flight-information");
const segmentName = element("segment");
const arrivalStatus = element("arrival-status");
const arrivalCaption = element("arrival-caption");
const arrivedCount = element("arrived");
const gooseArrivalDetail = element("goose-arrival-detail");
const gooseCrosswindDistance = element("goose-crosswind-distance");
const gooseHazardAnnouncement = element("goose-hazard-announcement");
const gooseFlightAnnouncement = element("goose-flight-announcement");
const resetButton = element("camera-reset");
const pauseButton = element("pause-flight");
const dismiss = element("dismiss-tips");
const skipLanding = element("skip-landing");
const stick = element("stick");
const gestureHint = element("gesture-hint");
const gestureCopy = element("gesture-copy");
const whaleStatus = element("whale-status");
const worldMarkers = new GooseMarkerLayout(markerLayer, [
  energyStatus,
  whaleStatus,
  hazardCue,
  flightCue,
  pauseButton,
  resetButton,
  ability,
  dismiss,
  skipLanding,
  stick,
  gestureHint,
]);
const whaleDepth = element("whale-depth");
const whaleDepthCue = element("whale-depth-cue");
const whaleBreath = element<HTMLProgressElement>("whale-breath");
const whaleBreathValue = element("whale-breath-value");
const whaleRescueMeter = element("whale-rescue-meter");
const whaleRescueProgress = element<HTMLProgressElement>(
  "whale-rescue-progress",
);
const whaleCohesionMeter = element("whale-cohesion-meter");
const whaleCohesion = element<HTMLProgressElement>("whale-cohesion");
const whaleCohesionValue = element("whale-cohesion-value");
const whaleSaveDetail = element("whale-save-detail");

new ResizeObserver(([entry]) => {
  if (entry)
    markerLayer.style.setProperty(
      "--cue-height",
      `${entry.contentRect.height}px`,
    );
}).observe(flightInformation);

function abilityName(species: Species): string {
  switch (species) {
    case "goose":
      return copy("结阵", "Formation");
    case "whale":
      return copy("下潜", "Dive");
    case "reindeer":
      return copy("等候", "Wait");
  }
}
const saves = new SaveStore();
const music = new MusicDirector();
const clock = new FixedClock();
const settingsKey = "feather-tide-settings-v1";
const coarsePointer = matchMedia("(pointer: coarse)");
const touchPortrait = matchMedia(
  "(orientation: portrait) and (pointer: coarse)",
);
const landmarkRange = 82;
const segmentRevealSeconds = 2.2;
const segmentFadeSeconds = 0.6;
const gestureRevealSeconds = 5;
const routeConfirmSeconds = 4;
const openingMarks = ["s0-waterway", "s0-turn", "s0-mark"];
const informativeReeds = new Set([
  "s1-mark",
  "wetland-mark",
  "tailwind-bend",
  "rescue-bay",
  "bay-reeds",
]);

function loadSettings(): InputSettings {
  const defaults = {
    ...DEFAULT_SETTINGS,
    reduced: matchMedia("(prefers-reduced-motion: reduce)").matches,
  };
  try {
    const source = JSON.parse(
      localStorage.getItem(settingsKey) ?? "{}",
    ) as Partial<InputSettings>;
    return {
      mirror:
        typeof source.mirror === "boolean" ? source.mirror : defaults.mirror,
      large: typeof source.large === "boolean" ? source.large : defaults.large,
      toggle:
        typeof source.toggle === "boolean" ? source.toggle : defaults.toggle,
      mapping: source.mapping === "B" ? "B" : "A",
      sensitivity:
        typeof source.sensitivity === "number" &&
        source.sensitivity >= 0.4 &&
        source.sensitivity <= 1.8
          ? source.sensitivity
          : defaults.sensitivity,
      vertical:
        typeof source.vertical === "boolean"
          ? source.vertical
          : defaults.vertical,
      wideMouseOrbit: source.wideMouseOrbit === true,
      reduced:
        typeof source.reduced === "boolean" ? source.reduced : defaults.reduced,
      low: typeof source.low === "boolean" ? source.low : defaults.low,
      music: typeof source.music === "boolean" ? source.music : defaults.music,
      bindings: readBindings(source.bindings),
    };
  } catch {
    return defaults;
  }
}

let settings = loadSettings();
let scene: FlightScene | WhaleScene | ReindeerScene | undefined;
let flightScene: FlightScene | undefined;
let whaleLevel: WhaleLevel | undefined;
let reindeerLevel: ReindeerLevel | undefined;
let selectedSpecies: Species = "goose";
let goose: FlightAssets | undefined;
let migration: LevelSchema | undefined;
let runtime: GameRuntime | undefined;
let contextLost = false;
let busy = false;
let retryChapterLoad: Exclude<Species, "goose"> | undefined;
let tips = true;
let cameraDragDistance = 0;
let gooseHorizontalDrag = 0;
let gooseTeachingProgress = freshGooseTeaching;
let shownGesture: "takeoff" | "orbit" | undefined;
let gestureEnteredTick = 0;
let gooseRouteTick = -Infinity;
let crosswindPickup: CrosswindPickup | undefined;
let seenReset = false;
let seenGlide = false;
let whaleSubmerged = false;
let whaleRecovered = false;
let reindeerCalled = false;
let movedForTutorial = false;
const WHALE_TUTORIAL_DRAG = 20;
let shownSegment: string | undefined;
let segmentEnteredTick = 0;
let menuSaveRefresh = 0;
let presentationSeconds = 0;
let landingPaused = false;
let reindeerLandingId: string | undefined;
let lastFrame: number | undefined;
let saveMessage = "";
let checkpointTick = -1;
let activeRun: string | undefined;
let landingSave: "pending" | "saved" | "failed" | "superseded" | undefined;
const labels = new Map<string, HTMLElement>();
const query = new URLSearchParams(location.search);
const diagnostics = query.has("diagnostics");
let titleReadyMs: number | undefined;
let reindeerSelectedAt: number | undefined;
let reindeerStartup:
  | {
      readonly from: "selection" | "start";
      readonly at: number;
      readonly checkpoint: string | null;
    }
  | undefined;
const frameDurations: number[] = [];
let lastReport = 0;
let performanceWindow = "";

function setText(node: HTMLElement, text: string): void {
  if (node.textContent !== text) node.textContent = text;
}

let bootMessage = () => copy("正在打开晨雾湿地…", "Opening the dawn wetlands…");

function showBootMessage(message: () => string): void {
  bootMessage = message;
  setText(bootStatus, message());
}

function showText(node: HTMLElement, text: string): void {
  setText(node, text);
  node.hidden = !text;
}

function applySettings(): void {
  game.classList.toggle("mirrored", settings.mirror);
  game.classList.toggle("large", settings.large);
  game.classList.toggle("reduced-motion", settings.reduced);
  for (const input of settingsDialog.querySelectorAll<HTMLInputElement>(
    "input",
  )) {
    if (input.name === "sensitivity")
      input.value = settings.sensitivity.toString();
    else input.checked = Boolean(settings[input.name as keyof InputSettings]);
  }
  const mapping = settingsDialog.querySelector("select");
  if (mapping) mapping.value = settings.mapping;
  sensitivityValue.value = `${settings.sensitivity.toFixed(1)}×`;
  refreshDesktopSettings();
}

const input = new InputManager(
  game,
  stick,
  () => settings,
  () =>
    Boolean(
      !busy &&
      canRunFlight() &&
      !hud.hidden &&
      !panel.open &&
      !settingsDialog.open &&
      runtime?.current.phase === "playing",
    ),
  () => scene?.camera.basis() ?? { right: { x: -1, z: 0 }, up: { x: 0, z: 1 } },
  (x, y, pointerType) => {
    const vertical = settings.vertical ? y : 0;
    if (!x && !vertical) return;
    cameraDragDistance += Math.hypot(x, vertical);
    if (selectedSpecies === "goose") gooseHorizontalDrag += Math.abs(x);
    scene?.camera.drag(x, vertical, settings, pointerType);
  },
  () => {
    if (settingsDialog.open || hud.hidden) return;
    if (runtime?.current.phase === "paused" && !contextLost) {
      if (panel.dataset.kind === "controls") showPaused();
      else resume();
    } else pause();
  },
  recenterCamera,
);

const refreshDesktopSettings = setupDesktopSettings(
  settingsDialog,
  () => settings.bindings,
  (bindings) => saveSettings({ ...settings, bindings }),
  () => abilityName(selectedSpecies),
);

function recenterCamera(): void {
  if (runtime?.current.phase !== "playing") return;
  scene?.camera.reset();
  if (
    runtime.current.species !== "whale" ||
    cameraDragDistance >= WHALE_TUTORIAL_DRAG
  )
    seenReset = true;
}

function saveSettings(next: InputSettings): void {
  if (
    next.vertical !== settings.vertical ||
    next.wideMouseOrbit !== settings.wideMouseOrbit
  )
    scene?.camera.reset(true);
  settings = next;
  input.clear();
  applySettings();
  try {
    localStorage.setItem(settingsKey, JSON.stringify(settings));
  } catch {
    /* In-memory settings still apply. */
  }
}

function unlockAudio(species: Species = selectedSpecies): void {
  void music.unlock(settings.music, species).catch(() => {});
}

function selectSoundtrack(play: boolean): void {
  const source = soundtrack[soundtrackTrack.value as keyof typeof soundtrack];
  soundtrackStatus.hidden = true;
  soundtrackPlayer.src = source;
  if (!play) return;
  const url = soundtrackPlayer.src;
  void soundtrackPlayer.play().catch((error: unknown) => {
    if (
      soundtrackDialog.open &&
      soundtrackPlayer.src === url &&
      !(
        error instanceof DOMException &&
        (error.name === "AbortError" || error.name === "NotAllowedError")
      )
    )
      soundtrackStatus.hidden = false;
  });
}

function showPanel(
  title: string,
  body: string,
  actions: { label: string; run: () => void; disabled?: boolean }[],
  presentation: {
    kind?: "pause" | "controls" | "failure" | "arrival";
    place?: string;
    summary?: string;
    note?: string;
  } = {},
): void {
  const kind = presentation.kind ?? "menu";
  const heading = element("panel-title");
  const focusedAction =
    panel.dataset.kind === kind && panelActions.contains(document.activeElement)
      ? document.activeElement?.textContent
      : undefined;
  panel.dataset.kind = kind;
  setText(heading, title);
  setText(element("panel-text"), body);
  showText(panelPlace, presentation.place ?? "");
  showText(panelSummary, presentation.summary ?? "");
  setText(panelNote, presentation.note ?? "");
  panelActions.replaceChildren();
  actions.forEach(({ label, run, disabled = false }, i) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.disabled = disabled;
    if (i === 0) button.classList.add("primary");
    button.addEventListener("click", run);
    panelActions.append(button);
  });
  if (!panel.open) panel.showModal();
  const available = [
    ...panelActions.querySelectorAll<HTMLButtonElement>(
      "button:not(:disabled)",
    ),
  ];
  const previous = available.find(
    (button) => button.textContent === focusedAction,
  );
  // Completing an animation or a save should not put the exit under a held key.
  (previous ?? (kind === "arrival" ? heading : available[0]))?.focus({
    preventScroll: true,
  });
}

function canRunFlight(): boolean {
  return !contextLost && !document.hidden && !touchPortrait.matches;
}

function remainingSeconds(ticks: number): number {
  return Math.ceil(ticks * STEP_SEC);
}

function usesTouchFlight(): boolean {
  return (
    (input.movementSource ?? (coarsePointer.matches ? "touch" : "keyboard")) ===
    "touch"
  );
}

function showFlightControls(): void {
  const { bindings, mirror, toggle } = settings;
  const touch = usesTouchFlight();
  const formationKey = touch
    ? copy("结阵键", "Formation")
    : keyLabel(bindings.formation);
  const formation = toggle
    ? isEnglish()
      ? `Tap ${formationKey} to form up. Tap again to break formation.`
      : `点按 ${formationKey} 结阵，再按一次解阵。`
    : isEnglish()
      ? `Hold ${formationKey} to form up. Release to break formation.`
      : `按住 ${formationKey} 结阵，松开解阵。`;
  const controls = touch
    ? [
        isEnglish()
          ? `Hold and drag on the ${mirror ? "right" : "left"}. Push gently to slow down or to the outer edge to boost.`
          : `在${mirror ? copy("右", "right") : copy("左", "left")}侧按住并拖动。轻推缓行，推到外圈加速。`,
        isEnglish()
          ? `Drag the open area on the ${mirror ? "left" : "right"} to look around. Tap the top ${mirror ? "left" : "right"} to reset the camera.`
          : `拖动${mirror ? copy("左", "left") : copy("右", "right")}侧空白处查看队伍，点${mirror ? copy("左", "left") : copy("右", "right")}上角复位。`,
      ]
    : [
        isEnglish()
          ? `Fly with ${movementLabel(bindings)} or the arrow keys. Hold ${keyLabel(bindings.slow)} to slow down or ${keyLabel(bindings.boost)} to boost.`
          : `用 ${movementLabel(bindings)} 或方向键飞行。飞行时按住 ${keyLabel(bindings.slow)} 缓行，按住 ${keyLabel(bindings.boost)} 加速。`,
        isEnglish()
          ? `Hold either mouse button and drag to look around. Press ${keyLabel(bindings.recenter)} to reset the camera.`
          : `按住鼠标左键或右键拖动视角，按 ${keyLabel(bindings.recenter)} 复位。`,
      ];
  showPanel(
    copy("飞行操作", "Flight controls"),
    [
      ...controls,
      isEnglish()
        ? `Boosting uses more stamina. At ${Math.round(GOOSE.boostCutoff * 100)}%, your top speed drops to cruising speed.`
        : `加速更费体力。体力降到 ${Math.round(GOOSE.boostCutoff * 100)}% 时，最高只能巡航。`,
      touch
        ? copy(
            "松开摇杆后先滑翔，再缓慢盘旋。",
            "Release the stick to glide, then circle slowly.",
          )
        : copy(
            "松开移动键后先滑翔，再缓慢盘旋。",
            "Release the movement keys to glide, then circle slowly.",
          ),
      formation,
    ].join("\n"),
    [
      { label: copy("返回暂停菜单", "Back to pause menu"), run: showPaused },
      ...(tips
        ? [
            {
              label: copy("跳过飞行教学", "Skip flight tutorial"),
              run: () => {
                tips = false;
                showFlightControls();
              },
            },
          ]
        : []),
    ],
    { kind: "controls" },
  );
}

function showPaused(): void {
  const state = runtime?.current;
  const segment = runtime?.level.segments.find(
    ({ id }) => id === state?.segmentId,
  );
  const gooseRescues =
    state?.species === "goose" ? gooseRescue(state) : undefined;
  const rescueTicks = gooseRescues
    ? gooseRescues.target?.rescueTicks
    : state?.actors.find(({ status }) => status === "strayed")?.rescueTicks;
  const whale = state?.species === "whale";
  const reindeer = state?.species === "reindeer";
  const activity = reindeer
    ? copy("旅程", "journey")
    : whale
      ? copy("航行", "swim")
      : copy("飞行", "flight");
  const group = reindeer
    ? copy("鹿群", "The herd")
    : whale
      ? copy("鲸群", "The pod")
      : copy("雁群", "The flock");
  const exit = { label: copy("返回标题", "Back to title"), run: returnToMenu };
  const actions = [
    {
      label: isEnglish() ? `Resume ${activity}` : `继续${activity}`,
      run: resume,
      disabled: touchPortrait.matches,
    },
    { label: copy("设置", "Settings"), run: () => settingsDialog.showModal() },
    ...(runtime?.level.id === tailwindPracticeId
      ? [
          {
            label: copy("从起点重飞", "Restart flight"),
            run: retry,
            disabled: touchPortrait.matches,
          },
        ]
      : []),
    ...(whale || reindeer
      ? []
      : [
          {
            label: copy("飞行操作", "Flight controls"),
            run: showFlightControls,
          },
        ]),
    exit,
  ];
  showPanel(
    contextLost
      ? copy("图形连接已中断", "Graphics connection lost")
      : isEnglish()
        ? `${activity} paused`
        : `${activity}暂停`,
    contextLost
      ? isEnglish()
        ? `You can resume your ${activity} when graphics recover, or reload the page.`
        : `图形恢复后可以继续${activity}。也可以重新加载页面。`
      : touchPortrait.matches
        ? isEnglish()
          ? `Rotate your screen to landscape to resume your ${activity}. ${group} will wait here.`
          : `请横置屏幕，再继续${activity}。${group}会在这里等你。`
        : isEnglish()
          ? `${group} will wait here.`
          : `${group}在这里等你。`,
    contextLost
      ? [
          { label: copy("重新加载", "Reload"), run: () => location.reload() },
          exit,
        ]
      : actions,
    {
      kind: "pause",
      place: segment && levelTitle(segment),
      summary:
        contextLost || !state
          ? undefined
          : rescueTicks != null
            ? gooseRescues && gooseRescues.count > 1
              ? isEnglish()
                ? `Awaiting rescue: ${gooseRescues.count} · Earliest timeout: ${remainingSeconds(rescueTicks)}s`
                : `${gooseRescues.count} 只待接应 · 最短剩余 ${remainingSeconds(rescueTicks)} 秒`
              : isEnglish()
                ? `Rescue time left: ${remainingSeconds(rescueTicks)}s`
                : `接应剩余 ${remainingSeconds(rescueTicks)} 秒`
            : touchPortrait.matches
              ? undefined
              : `${whale ? copy("能量", "Energy") : copy("体力", "Stamina")} ${Math.round(state.energy * 100)}%`,
    },
  );
}

function showLandingPaused(): void {
  const whale = runtime?.current.species === "whale";
  const action = whale ? copy("汇合", "reunion") : copy("落脚", "arrival");
  showPanel(
    isEnglish() ? `${action} paused` : `${action}暂停`,
    touchPortrait.matches
      ? isEnglish()
        ? `Rotate your screen to landscape to resume the ${action}.`
        : `请横置屏幕，再继续${action}。`
      : whale
        ? copy("鲸群已抵达。", "The pod has arrived.")
        : runtime?.current.species === "reindeer"
          ? copy("鹿群已抵达。", "The herd has arrived.")
          : copy("雁群已抵达。", "The flock has arrived."),
    [
      {
        label: isEnglish() ? `Resume ${action}` : `继续${action}`,
        run: resume,
        disabled: touchPortrait.matches,
      },
      {
        label: isEnglish() ? `Skip ${action} scene` : `跳过${action}演出`,
        run: finishLanding,
      },
    ].filter((_, i) => !contextLost || i === 1),
    { kind: "pause" },
  );
}

function refreshPausePanel(): void {
  if (hud.hidden) return;
  if (runtime?.current.phase === "paused") showPaused();
  else if (runtime?.current.phase === "landing" && landingPaused)
    showLandingPaused();
}

function pause(): void {
  input.clear();
  clock.reset();
  lastFrame = undefined;
  music.pause();
  soundtrackPlayer.pause();
  if (hud.hidden) return;
  if (runtime?.current.phase === "landing") {
    landingPaused = true;
    showLandingPaused();
    return;
  }
  if (runtime?.current.phase !== "playing") return;
  runtime.dispatch({ type: "pause" });
  showPaused();
}

function resume(): void {
  if (!runtime || !canRunFlight()) return;
  input.clear();
  clock.reset();
  lastFrame = undefined;
  runtime.dispatch({ type: "resume" });
  landingPaused = false;
  panel.close();
  // Returning focus to the play surface keeps Space available for Formation.
  game.focus({ preventScroll: true });
  unlockAudio();
}

function retry(): void {
  if (!runtime || contextLost) return;
  if (!runtime.dispatch({ type: "retry" }).length) return;
  if (diagnostics) game.dataset.retry = JSON.stringify(runtime.current);
  music.reset();
  input.clear();
  clock.reset();
  lastFrame = undefined;
  scene?.resetFlightView();
  shownSegment = undefined;
  gooseRouteTick = runtime.current.route ? runtime.current.tick : -Infinity;
  crosswindPickup = undefined;
  if (runtime.level.id === tailwindPracticeId)
    gooseTeachingProgress = freshGooseTeaching;
  panel.close();
  game.focus({ preventScroll: true });
  if (canRunFlight()) unlockAudio();
  else pause();
}

function showMenuScreen(screen: "title" | "species"): void {
  const picking = screen === "species";
  titleMenu.hidden = picking;
  speciesMenu.hidden = !picking;
  (picking ? speciesMessage : titleMessage).append(menuMessage);
  if (picking) {
    speciesMenu.scrollTop = 0;
    (gooseContinue.hidden ? gooseEntry : gooseContinue).focus({
      preventScroll: true,
    });
    void refreshMenuSaves();
  } else {
    retryChapterLoad = undefined;
    retryLoad.hidden = true;
    if (!contextLost) bootStatus.hidden = true;
    enterGame.focus({ preventScroll: true });
  }
}

function setMenuBusy(value: boolean): void {
  busy = value;
  speciesBack.disabled = value;
  speciesChoices.setAttribute("aria-busy", String(value));
}

function returnToMenu(): void {
  reindeerStartup = undefined;
  reindeerSelectedAt = undefined;
  input.clear();
  music.pause();
  music.reset();
  clock.reset();
  lastFrame = undefined;
  panel.close();
  settingsDialog.close();
  hud.hidden = true;
  menu.hidden = false;
  activeRun = undefined;
  if (migration && goose && flightScene) {
    if (scene && !(scene instanceof FlightScene)) scene.dispose();
    selectedSpecies = "goose";
    scene = flightScene;
    runtime = new GameRuntime(migration, "journey");
    scene.setLevel(migration, goose, settings.low);
    updateChapterMenu();
  }
  showMenuScreen("title");
}

function start(
  level: AnyLevelSchema,
  mode: GameMode,
  snapshot?: CheckpointSnapshot,
  existingRun?: string,
): void {
  if (!scene || !goose) return;
  if (
    level.species !== (scene instanceof FlightScene ? "goose" : scene.species)
  )
    return;
  if (diagnostics && level.species === "reindeer") {
    delete game.dataset.reindeerStartup;
    reindeerStartup = {
      from: reindeerSelectedAt === undefined ? "start" : "selection",
      at: reindeerSelectedAt ?? performance.now(),
      checkpoint: snapshot?.id ?? null,
    };
    reindeerSelectedAt = undefined;
  }
  landingPaused = false;
  music.reset();
  landingSave = undefined;
  runtime = new GameRuntime(level, mode, snapshot);
  if (diagnostics) delete game.dataset.retry;
  activeRun = undefined;
  if (level.id === "migration" || level.species !== "goose") {
    const runId =
      existingRun ??
      Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) =>
        byte.toString(16).padStart(2, "0"),
      ).join("");
    activeRun = runId;
    if (!existingRun) {
      const base = {
        version: 1 as const,
        runId,
        levelRevision: level.levelRevision,
      };
      void saves
        .begin(
          mode,
          snapshot
            ? { ...base, kind: "checkpoint", checkpoint: snapshot }
            : { ...base, kind: "started" },
          level,
        )
        .catch(() => {
          if (activeRun === runId)
            saveMessage = copy(
              "无法初始化存档，本次可继续旅程。",
              "The save could not be created. You can still play this journey.",
            );
        });
    }
  }
  if (level.species === "goose" && scene instanceof FlightScene)
    scene.setLevel(level, goose, settings.low);
  else scene.resetFlightView();
  hud.dataset.species = level.species;
  const whale = level.species === "whale";
  whaleStatus.hidden = !whale;
  const reindeer = level.species === "reindeer";
  for (const live of [hazardNotice, notice, arrivalStatus, energyCondition])
    live.setAttribute("aria-live", whale || reindeer ? "polite" : "off");
  setText(gooseHazardAnnouncement, "");
  setText(gooseFlightAnnouncement, "");
  showText(gooseArrivalDetail, "");
  showText(gooseCrosswindDistance, "");
  crosswindPickup = undefined;
  rescueClock.setAttribute(
    "aria-label",
    copy("剩余接应时间", "Rescue time remaining"),
  );
  hud.setAttribute(
    "aria-label",
    reindeer
      ? copy("驯鹿旅程界面", "Reindeer journey HUD")
      : whale
        ? copy("鲸航行界面", "Whale journey HUD")
        : copy("飞行界面", "Flight HUD"),
  );
  ability.setAttribute("aria-label", abilityName(level.species));
  setText(formationLabel, abilityName(level.species));
  ability.removeAttribute("aria-disabled");
  whaleRescueMeter.hidden = true;
  whaleCohesionMeter.hidden = true;
  setText(whaleSaveDetail, "");
  setText(
    skipLanding,
    whale
      ? copy("跳过汇合演出", "Skip reunion scene")
      : copy("跳过落脚演出", "Skip arrival scene"),
  );
  setText(
    dismiss,
    whale || reindeer
      ? copy("略过提示", "Skip hints")
      : copy("跳过飞行教学", "Skip flight tutorial"),
  );
  if (whale || reindeer) hud.insertBefore(dismiss, stick);
  else flightInformation.append(dismiss);
  gestureHint.hidden = whale || reindeer;
  gestureHint.removeAttribute("data-active");
  shownGesture = undefined;
  clock.reset();
  lastFrame = undefined;
  checkpointTick = snapshot?.state.tick ?? -1;
  tips = !snapshot;
  cameraDragDistance = 0;
  gooseHorizontalDrag = 0;
  gooseTeachingProgress = freshGooseTeaching;
  gooseRouteTick = runtime.current.route ? runtime.current.tick : -Infinity;
  seenReset = false;
  seenGlide = false;
  whaleSubmerged = false;
  whaleRecovered = false;
  reindeerCalled = false;
  reindeerLandingId = undefined;
  movedForTutorial = false;
  shownSegment = undefined;
  menu.hidden = true;
  hud.hidden = false;
  panel.close();
  input.clear();
  game.focus({ preventScroll: true });
  if (canRunFlight()) unlockAudio();
  else pause();
}

async function readMenuSave(level: AnyLevelSchema, mode: GameMode) {
  const previous = await saves.read(mode, level);
  const record = readRunRecord(previous, level, mode);
  const snapshot =
    record?.kind === "checkpoint"
      ? record.checkpoint
      : level.species === "goose"
        ? readCheckpoint(previous, level, mode)
        : undefined;
  return {
    record,
    snapshot,
    invalid: previous !== undefined && !record && !snapshot,
    outdatedReindeer:
      level.species === "reindeer" &&
      previous !== null &&
      typeof previous === "object" &&
      "levelRevision" in previous &&
      previous.levelRevision !== level.levelRevision,
  };
}

async function refreshMenuSaves(): Promise<void> {
  const level = migration;
  if (!level) return;
  const refresh = ++menuSaveRefresh;
  const saved = await readMenuSave(level, "journey").catch(() => undefined);
  if (refresh !== menuSaveRefresh || menu.hidden || speciesMenu.hidden) return;
  const hadContinue = !gooseContinue.hidden;
  const focus = document.activeElement;
  gooseContinue.hidden = !saved?.snapshot;
  if (hadContinue && gooseContinue.hidden && focus === gooseContinue)
    gooseEntry.focus({ preventScroll: true });
  if (!hadContinue && !gooseContinue.hidden && focus === gooseEntry)
    gooseContinue.focus({ preventScroll: true });
  setText(
    gooseAction,
    saved?.snapshot
      ? copy("重新起飞", "Restart flight")
      : saved?.record?.kind === "arrived"
        ? copy("查看上次落脚", "View last arrival")
        : !saved || saved.invalid
          ? copy("检查旅程存档", "Check journey save")
          : copy("开始旅程", "Start journey"),
  );
}

function updateChapterMenu(): void {
  setText(
    element("toggle-caption"),
    isEnglish()
      ? `Tap to toggle ${abilityName(selectedSpecies)}`
      : `点按切换${abilityName(selectedSpecies)}`,
  );
  refreshDesktopSettings();
}

async function selectChapter(species: Species): Promise<void> {
  if (
    busy ||
    contextLost ||
    menu.hidden ||
    !flightScene ||
    !migration ||
    !goose
  )
    return;
  retryChapterLoad = undefined;
  retryLoad.hidden = true;
  if (species === selectedSpecies) {
    bootStatus.hidden = true;
    return;
  }
  if (species === "goose") {
    if (scene && !(scene instanceof FlightScene)) scene.dispose();
    selectedSpecies = "goose";
    scene = flightScene;
    runtime = new GameRuntime(migration, "journey");
    scene.setLevel(migration, goose, settings.low);
    bootStatus.hidden = true;
  } else {
    if (diagnostics && species === "reindeer") {
      delete game.dataset.reindeerStartup;
      reindeerSelectedAt = performance.now();
    }
    setMenuBusy(true);
    bootStatus.hidden = false;
    const chapter = () =>
      species === "reindeer"
        ? copy("苔原过路", "Tundra Crossing")
        : copy("安静航道", "Quiet Passage");
    showBootMessage(() =>
      isEnglish() ? `Loading ${chapter()}…` : `正在载入${chapter()}…`,
    );
    try {
      const previous = scene;
      if (species === "reindeer") {
        const { ReindeerScene, loadReindeerAssets } =
          await import("../rendering/reindeer-scene");
        const [level, assets] = await Promise.all([
          loadLevel("reindeer"),
          loadReindeerAssets(query.get("reindeerGraybox") === "1"),
        ]);
        scene = new ReindeerScene(flightScene.renderer, level, assets);
        reindeerLevel = level;
        runtime = new GameRuntime(level, "journey");
      } else {
        const { WhaleScene, loadWhaleAssets } =
          await import("../rendering/whale-scene");
        const [level, assets] = await Promise.all([
          loadLevel("whale"),
          loadWhaleAssets(query.get("whaleGraybox") === "1"),
        ]);
        scene = new WhaleScene(
          flightScene.renderer.domElement,
          level,
          assets,
          flightScene.renderer,
        );
        whaleLevel = level;
        runtime = new GameRuntime(level, "journey");
      }
      if (previous && !(previous instanceof FlightScene)) previous.dispose();
      selectedSpecies = species;
      bootStatus.hidden = true;
    } catch (error) {
      retryChapterLoad = species;
      retryLoad.hidden = false;
      console.error(error);
      showBootMessage(() =>
        isEnglish()
          ? `Could not load ${chapter()}. Try again.`
          : `${chapter()}加载失败，请重试。`,
      );
    } finally {
      setMenuBusy(false);
    }
  }
  input.clear();
  updateChapterMenu();
  void refreshMenuSaves();
}

function showPractice(): void {
  showPanel(
    copy("练习飞行", "Flight practice"),
    copy(
      "在湿地练转向，或走一趟短航线。",
      "Practice turning over the wetlands or fly a short course.",
    ),
    [
      {
        label: copy("飞行实验场", "Flight playground"),
        run: () => {
          if (canRunFlight()) unlockAudio();
          void choose("playground");
        },
      },
      {
        label: copy("顺风转弯试飞", "Tailwind Turn Practice"),
        run: () => void choose(tailwindPracticeId),
      },
      {
        label: copy("规则试飞", "Flight drills"),
        run: () => void choose("rules"),
      },
      { label: copy("返回", "Back"), run: () => panel.close() },
    ],
  );
}

async function choose(choice: string, continuing = false): Promise<void> {
  if (!migration || busy || contextLost) return;
  setMenuBusy(true);
  saveMessage = "";
  try {
    if (choice === "playground") {
      showBootMessage(() =>
        copy("正在载入飞行实验场…", "Loading the flight playground…"),
      );
      bootStatus.hidden = false;
      start(await loadLevel("playground"), "journey");
      bootStatus.hidden = true;
      return;
    }
    if (choice === tailwindPracticeId) {
      start(tailwindPractice(migration), "journey");
      return;
    }
    if (choice === "rules") {
      bootStatus.hidden = false;
      showBootMessage(() =>
        copy("正在载入规则试飞…", "Loading flight drills…"),
      );
      const level = await loadLevel("rules");
      bootStatus.hidden = true;
      showPanel(
        copy("规则试飞", "Flight drills"),
        copy(
          "在短航线练习补给、接应、绕飞和全队落脚。",
          "Fly a short course to practice refueling, rescuing companions, skirting hazards, and landing together.",
        ),
        [
          {
            label: copy("旅程试飞", "Start practice journey"),
            run: () => start(level, "journey"),
          },
          { label: copy("返回", "Back"), run: showPractice },
        ],
      );
      return;
    }
    if (choice !== "journey") return;
    const level = {
      goose: migration,
      whale: whaleLevel,
      reindeer: reindeerLevel,
    }[selectedSpecies];
    if (!level) return;
    const whale = level.species === "whale";
    const deer = level.species === "reindeer";
    const saved = await readMenuSave(level, choice).catch(() => undefined);
    if (!saved) {
      showPanel(
        copy("暂时无法读取存档", "Save unavailable"),
        copy(
          "可以返回重试，或明确开始一段新旅程。",
          "Go back and try again, or start a new journey.",
        ),
        [
          { label: copy("返回", "Back"), run: () => panel.close() },
          {
            label: copy("开始新航程", "Start a new journey"),
            run: () => start(level, choice),
          },
        ],
      );
      return;
    }
    const { record, snapshot, invalid, outdatedReindeer } = saved;
    // Time at a save-choice dialog is spent by the player, outside loading.
    if (deer && (snapshot || record?.kind === "arrived" || invalid))
      reindeerSelectedAt = undefined;
    if (continuing) {
      if (snapshot) start(level, choice, snapshot, record?.runId);
      else {
        showPanel(
          copy("暂时无法继续", "Unable to continue"),
          isEnglish()
            ? `There’s no save available for ${levelTitle(level)}.`
            : `这次没有可用的${levelTitle(level)}存档。`,
          [
            { label: copy("返回", "Back"), run: () => panel.close() },
            {
              label: copy("开始新航程", "Start a new journey"),
              run: () => start(level, choice),
            },
          ],
        );
        void refreshMenuSaves();
      }
      return;
    }
    if (snapshot) {
      showPanel(
        deer
          ? copy("继续苔原过路", "Continue Tundra Crossing")
          : whale
            ? copy("继续安静航道", "Continue Quiet Passage")
            : copy("回到芦苇洲", "Return to Reedbank"),
        isEnglish()
          ? `Continue from checkpoint ${snapshot.id} or start a new migration.`
          : `可以从检查点 ${snapshot.id} 继续，也可以开始一趟新的迁徙。`,
        [
          {
            label: copy("从检查点继续", "Continue from checkpoint"),
            run: () => start(level, choice, snapshot, record?.runId),
          },
          {
            label: deer
              ? copy("重新出发", "Start over")
              : whale
                ? copy("重新起游", "Restart swim")
                : copy("重新起飞", "Restart flight"),
            run: () => start(level, choice),
          },
          { label: copy("返回", "Back"), run: () => panel.close() },
        ],
      );
    } else if (record?.kind === "arrived") {
      showPanel(
        deer
          ? copy("上次旅程已落脚", "Last journey complete")
          : whale
            ? copy("上次航程已汇合", "Last swim complete")
            : copy("上次飞行已落脚", "Last flight complete"),
        arrivalText(record.route, level.species),
        [
          {
            label: copy("开始新航程", "Start a new journey"),
            run: () => start(level, choice),
          },
          { label: copy("返回", "Back"), run: () => panel.close() },
        ],
      );
    } else if (invalid) {
      showPanel(
        deer
          ? outdatedReindeer
            ? copy("苔原路线已更新", "Tundra route updated")
            : copy("驯鹿旅程存档无法继续", "Reindeer journey save unavailable")
          : whale
            ? copy("鲸航程存档无法继续", "Whale journey save unavailable")
            : copy("雁旅程存档无法继续", "Goose journey save unavailable"),
        deer
          ? outdatedReindeer
            ? copy(
                "本版调整了围栏与矿区路线，旧检查点不能直接继续。可重新从冬林出发，返回会保留原存档。",
                "The fence and mining routes have changed. Start again from the winter woods, or go back to keep your old save.",
              )
            : copy(
                "存档已损坏，可从冬林开始新旅程。",
                "The save is damaged. You can start a new journey from the winter woods.",
              )
          : isEnglish()
            ? `This save is damaged or belongs to a different level version. You can start again from ${whale ? "the bay" : "the dawn wetlands"}.`
            : `存档已损坏或使用其他关卡版本。可从${whale ? copy("海湾", "the bay") : copy("晨雾湿地", "the dawn wetlands")}开始新航程。`,
        [
          { label: copy("返回", "Back"), run: () => panel.close() },
          {
            label: copy("开始新航程", "Start a new journey"),
            run: () => start(level, choice),
          },
        ],
      );
    } else {
      start(level, choice);
    }
  } catch (error) {
    panel.close();
    console.error(error);
    showBootMessage(() =>
      copy("加载失败，请重试。", "Loading failed. Try again."),
    );
    bootStatus.hidden = false;
  } finally {
    setMenuBusy(false);
  }
}

function events(list: readonly GameEvent[]): void {
  if (!runtime || list.length === 0) return;
  const { previous, current, level } = runtime;
  for (const event of list) {
    if (
      event.type === "strayed" &&
      previous.species === "goose" &&
      current.species === "goose" &&
      level.species === "goose"
    )
      crosswindPickup =
        gooseCrosswindPickup(previous, current, level, event.id) ??
        crosswindPickup;
    if (event.type === "rejoined" && crosswindPickup?.actorId === event.id)
      crosswindPickup = undefined;
    if (event.type === "route" && runtime.current.species === "goose")
      gooseRouteTick = runtime.current.tick;
    if (event.type === "checkpoint") {
      checkpointTick = runtime.current.tick;
      const checkpoint = runtime.checkpoint;
      const runId = activeRun;
      if (checkpoint.id === event.id && runId) {
        saveMessage = isEnglish()
          ? `Saving checkpoint ${event.id}…`
          : `正在保存检查点 ${event.id}…`;
        void saves
          .replace(
            checkpoint.state.mode,
            {
              version: 1,
              runId,
              levelRevision: checkpoint.state.levelRevision,
              kind: "checkpoint",
              checkpoint,
            },
            runtime.level,
          )
          .then((written) => {
            if (activeRun === runId && checkpointTick === checkpoint.state.tick)
              saveMessage = written
                ? isEnglish()
                  ? `Checkpoint ${event.id} saved`
                  : `检查点 ${event.id} 已保存`
                : copy(
                    "检查点未写入，本次可从内存重试。",
                    "Could not save the checkpoint. You can retry from it during this session.",
                  );
          })
          .catch(() => {
            if (activeRun === runId && checkpointTick === checkpoint.state.tick)
              saveMessage = copy(
                "存档写入失败，本次仍可从检查点重试",
                "Could not write the save. You can still retry from the checkpoint.",
              );
          });
      }
    }
    if (event.type === "phase" && event.phase === "failed") {
      input.clear();
      const rescue = runtime.current.failure === "rescue";
      const whale = runtime.current.species === "whale";
      const deer = runtime.current.species === "reindeer";
      const checkpointId = runtime.checkpoint.id;
      showPanel(
        rescue
          ? copy("再接应一次", "Try the rescue again")
          : whale || deer
            ? copy("停一停，歇一歇", "Stop and rest")
            : copy("飞一段，歇一歇", "Take a moment to rest"),
        rescue
          ? deer
            ? copy(
                "回到上一处休息地，再带上队尾。",
                "Return to the last resting spot and bring the group back together.",
              )
            : whale
              ? copy(
                  "一位同伴还在安全水域等候。",
                  "A companion is still waiting in safe water.",
                )
              : copy(
                  "一位同伴还在河湾等候。",
                  "A companion is still waiting in the river bend.",
                )
          : isEnglish()
            ? `Retry to restore ${whale ? "Energy" : "Stamina"} and set out together again.`
            : `重试会恢复${whale ? copy("能量", "Energy") : copy("体力", "Stamina")}，全队再一起出发。`,
        [
          {
            label:
              runtime.level.id === tailwindPracticeId
                ? copy("从起点重飞", "Restart flight")
                : checkpointId === "start"
                  ? deer
                    ? copy("从冬林重试", "Retry from the winter woods")
                    : whale
                      ? copy("从海湾重试", "Retry from the bay")
                      : copy("从湿地重试", "Retry from the wetlands")
                  : isEnglish()
                    ? `Retry from checkpoint ${checkpointId}`
                    : `从检查点 ${checkpointId} 重试`,
            run: retry,
          },
          { label: copy("返回标题", "Back to title"), run: returnToMenu },
        ],
        {
          kind: "failure",
          summary: rescue
            ? copy("接应时间已到", "Rescue time ran out")
            : whale
              ? copy("能量耗尽", "Energy depleted")
              : copy("体力耗尽", "Stamina depleted"),
          place:
            checkpointId === "start"
              ? deer
                ? copy("冬林出发", "Winter Woods")
                : whale
                  ? copy("海湾起游", "Leaving the Bay")
                  : copy("起飞湿地", "Takeoff Wetlands")
              : deer
                ? isEnglish()
                  ? `Tundra Crossing · Checkpoint ${checkpointId}`
                  : `苔原过路 · 检查点 ${checkpointId}`
                : whale
                  ? isEnglish()
                    ? `Quiet Passage · Checkpoint ${checkpointId}`
                    : `安静航道 · 检查点 ${checkpointId}`
                  : copy("芦苇洲 · 检查点 A", "Reedbank · Checkpoint A"),
        },
      );
    }
    if (event.type === "phase" && event.phase === "landing") {
      input.clear();
      presentationSeconds = 0;
      const { previous, current, level } = runtime ?? {};
      if (previous?.species === "reindeer" && current?.species === "reindeer")
        reindeerLandingId = reindeerLandingCompanion(
          previous,
          current,
          level?.zones.find(({ kind }) => kind === "goal"),
        )?.id;
      persistLanding();
    }
    if (event.type === "completed") showArrival();
  }
}

function persistLanding(): void {
  const flight = runtime;
  const runId = activeRun;
  if (!flight || !runId || landingSave === "pending") return;
  const { tick, route, mode, levelRevision } = flight.current;
  landingSave = "pending";
  if (flight.current.phase === "completed") showArrival();
  function finished(status: typeof landingSave): void {
    if (runtime !== flight || activeRun !== runId) return;
    landingSave = status;
    if (flight?.current.phase === "completed") showArrival();
  }
  void saves
    .replace(
      mode,
      {
        version: 1,
        runId,
        levelRevision,
        kind: "arrived",
        route,
        tick,
      },
      flight.level,
    )
    .then(
      (written) => finished(written ? "saved" : "superseded"),
      () => finished("failed"),
    );
}

function showArrival(): void {
  if (!runtime) return;
  const goalZone = runtime.level.zones.find(({ kind }) => kind === "goal");
  const goal = goalStatus(runtime.current, goalZone);
  if (runtime.level.id === tailwindPracticeId) {
    const { level, current } = runtime;
    showPanel(
      copy("全队完成试飞", "The whole flock finished practice"),
      copy(
        "可以换一条航线，比较过弯与落脚时的体力。",
        "Try the other route and compare your stamina after the turn and at landing.",
      ),
      [
        {
          label: copy("从起点重飞", "Restart flight"),
          run: () => start(level, "journey"),
        },
        { label: copy("返回标题", "Back to title"), run: returnToMenu },
      ],
      {
        kind: "arrival",
        place: levelTitle(level),
        summary: isEnglish()
          ? `${goal.arrived} of ${goal.expected} geese landed · ${Math.round(current.energy * 100)}% stamina`
          : `${goal.arrived} / ${goal.expected} 只雁落脚 · 体力 ${Math.round(current.energy * 100)}%`,
      },
    );
    return;
  }
  const whale = runtime.current.species === "whale";
  const action = whale ? copy("汇合", "reunion") : copy("落脚", "arrival");
  const note =
    landingSave === "pending"
      ? isEnglish()
        ? `Saving the ${action}…`
        : `正在保存${action}结果…`
      : landingSave === "failed"
        ? isEnglish()
          ? `Could not save the ${action}. You can try again.`
          : `${action}结果保存失败，可以重试。`
        : landingSave === "superseded"
          ? copy(
              "存档已被更新，本次结果未写入。",
              "A newer save is already in place. This result was not saved.",
            )
          : "";
  const actions = [
    { label: copy("返回标题", "Back to title"), run: returnToMenu },
  ];
  if (landingSave === "failed")
    actions.unshift({
      label: copy("重试保存结果", "Try saving again"),
      run: persistLanding,
    });
  const label = routeLabel(runtime.current.route);
  showPanel(
    copy("一起抵达", "We Arrived Together"),
    label ? (isEnglish() ? `Via ${label}` : `经${label}`) : "",
    actions,
    {
      kind: "arrival",
      place: goalZone && levelLabel(goalZone),
      summary: isEnglish()
        ? `${goal.arrived} of ${goal.expected} ${runtime.current.species === "reindeer" ? "reindeer settled" : whale ? "whales reunited" : "geese landed"}`
        : `${goal.arrived} / ${goal.expected} 只${runtime.current.species === "reindeer" ? copy("鹿落脚", "reindeer settled") : whale ? copy("鲸汇合", "whales reunited") : copy("雁落脚", "geese landed")}`,
      note,
    },
  );
}

function routeLabel(route: Route | null): string {
  return route
    ? {
        lake: copy("长湖路", "the Long Lake Route"),
        mountain: copy("短山口", "the Mountain Pass"),
        shipping: copy("近程船道", "the Short Channel"),
        quiet: copy("安静航道", "Quiet Passage"),
        dust: copy("尘雾边缘", "the Dust Edge"),
        greenbelt: copy("恢复植被带", "the Restored Greenbelt"),
      }[route]
    : "";
}

function arrivalText(route: Route | null, species: Species): string {
  const label = routeLabel(route);
  const result =
    species === "reindeer"
      ? copy(
          "九只鹿已在春季苔原落脚。",
          "All nine reindeer have settled on the spring tundra.",
        )
      : species === "whale"
        ? copy("六只鲸已在外海汇合。", "All six whales have reunited offshore.")
        : copy(
            "十二只斑头雁已在芦苇湿地落脚。",
            "All twelve bar-headed geese have landed in the reed wetlands.",
          );
  if (!label) return result;
  return isEnglish()
    ? `${result} The route took you through ${label}.`
    : `${result}这次经过${label}。`;
}

function finishLanding(): void {
  if (runtime) events(runtime.dispatch({ type: "finishLanding" }));
}

function drawMarker(
  id: string,
  label: string,
  position: Vec2,
  used: Set<string>,
  kind: GooseMarkerKind = "landmark",
  allowEdge = true,
  depth?: number,
  primary = false,
): void {
  const point =
    scene instanceof FlightScene
      ? scene.project(position)
      : scene?.species === "whale"
        ? scene.project(position, depth)
        : scene?.project(
            position,
            kind === "hazard",
            kind === "gathering" || kind === "rescue",
          );
  if (!point || (point.edge && !allowEdge)) return;
  let node = labels.get(id);
  if (!node) {
    node = document.createElement("span");
    node.className = "world-label";
    labels.set(id, node);
    markerLayer.append(node);
  }
  used.add(id);
  setText(node, kind === "pin" ? "" : label);
  node.hidden = false;
  node.classList.toggle("edge", point.edge);
  node.classList.toggle("pin", kind === "pin");
  if (node.dataset.kind !== kind) node.dataset.kind = kind;
  const whale =
    scene && !(scene instanceof FlightScene) && scene.species === "whale";
  if (scene instanceof FlightScene || whale) {
    worldMarkers.add(node, point, kind, primary || (whale && kind === "route"));
    return;
  }
  delete node.dataset.markerPlacement;
  node.style.setProperty("--marker-x", `${point.x}%`);
  node.style.setProperty("--marker-y", `${point.y}%`);
  node.style.setProperty("--arrow", `${point.angle}deg`);
}

function showHud(): void {
  if (!runtime || hud.hidden) return;
  const state = runtime.current;
  const { level } = runtime;
  if (state.species === "whale" && level.species === "whale") {
    showWhaleHud(state, level);
    return;
  }
  if (state.species === "reindeer" && level.species === "reindeer") {
    showReindeerHud(state, level);
    return;
  }
  if (state.species !== "goose" || level.species !== "goose") return;
  const leader = leaderOf(state);
  const goalZone = level.zones.find((zone) => zone.kind === "goal");
  const goal = goalStatus(state, goalZone);
  const warnings = level.zones.filter(
    (zone) => zone.kind === "warning" && state.occupied.includes(zone.id),
  );
  const routeWarning = warnings.find(
    ({ id }) => id !== "wind-warning" && id !== "gallery-warning",
  );
  const galleryWarning = warnings.find(({ id }) => id === "gallery-warning");
  const windWarning = warnings.find(({ id }) => id === "wind-warning");
  const galleryClear = level.landmarks.find(({ id }) => id === "gallery-clear");
  const galleryAhead =
    galleryWarning &&
    (state.segmentId === "S5" || Math.cos(leader.heading) < 0);
  const { target: rescue, count: rescueCount } = gooseRescue(state);
  const rejoining = state.actors.some(({ status }) => status === "rejoining");
  const crosswind = gooseCrosswindApproach(state, level);
  const landingApproach = gooseLandingApproach(state, level, goalZone);
  const shear = level.zones.find(
    (zone) =>
      zone.kind === "interference" &&
      zone.wind &&
      state.occupied.includes(zone.id),
  );
  const supply = level.zones.filter((zone) => zone.kind === "supply");
  const baySupply = supply.find(({ id }) => id === "reserve-supply");
  const lakeAvailable = supplyAvailable(
    state,
    supply.find(({ id }) => id === "lake-supply"),
  );
  const currentSegment = level.segments.find(
    (item) => item.id === state.segmentId,
  );
  const playing = state.phase === "playing";
  const landing = state.phase === "landing";
  const flightControls = playing || state.phase === "paused";
  const waiting = playing && goal.leaderArrived && !goal.canLand;
  const used = new Set<string>();
  markerLayer.dataset.camera = scene?.camera.mode ?? "Follow";
  if (shownSegment !== state.segmentId) {
    shownSegment = state.segmentId;
    segmentEnteredTick = state.tick;
  }
  energy.value = state.energy;
  const flightInput = input.sample();
  const held = flightInput.ability;
  const formation = !state.airborne
    ? "idle"
    : held
      ? state.formation >= 1
        ? "formed"
        : "forming"
      : state.formation > 0
        ? "releasing"
        : "idle";
  const formationText =
    formation === "formed"
      ? copy("已成阵", "In formation")
      : formation === "forming"
        ? copy("成阵中", "Forming up")
        : formation === "releasing"
          ? copy("解阵中", "Breaking formation")
          : copy("结阵", "Formation");
  if (ability.dataset.state !== formation) ability.dataset.state = formation;
  const pressed = String(held);
  if (ability.getAttribute("aria-pressed") !== pressed)
    ability.setAttribute("aria-pressed", pressed);
  ability.style.setProperty("--formation", String(state.formation));
  setText(formationLabel, formationText);
  setText(formationStatus, formation === "idle" ? "" : formationText);
  skipLanding.hidden = !landing;
  pauseButton.hidden = !flightControls && !landing;
  resetButton.hidden = !flightControls;
  ability.hidden = !flightControls;
  arrivalStatus.hidden = !waiting && !landing;
  setText(
    arrivalCaption,
    waiting
      ? copy("等待同伴", "Waiting for companions")
      : landing
        ? copy("全队降落", "Flock landing")
        : "",
  );
  setText(
    arrivedCount,
    waiting || landing ? `${goal.arrived}/${goal.expected}` : "",
  );

  const approach = rescue && rescueApproach(leader, rescue);
  const rescueAction =
    approach === "distance"
      ? copy("沿标记飞入接应圈。", "Follow the marker into the rescue circle.")
      : approach === "speed"
        ? usesTouchFlight()
          ? copy(
              "轻推摇杆减速，留在接应圈内。",
              "Ease back on the stick and stay inside the rescue circle.",
            )
          : isEnglish()
            ? `Hold ${keyLabel(settings.bindings.slow)} to slow down. Stay inside the rescue circle.`
            : `按住 ${keyLabel(settings.bindings.slow)} 减速，留在接应圈内。`
        : copy(
            "保持缓行，留在接应圈内。",
            "Stay slow and within the rescue circle.",
          );
  const landingWait =
    waiting && !rescue ? gooseLandingWait(state, goalZone) : undefined;
  showText(gooseArrivalDetail, landingWait?.action ?? "");
  const warning = gooseHazardCue(state, level);
  const danger = warning?.title ?? "";
  const threat = warning?.threat;
  const ridgeRecovery = warning?.ridgeRecovery;
  const windfarm = gooseWindfarmOptions(state, level, threat);
  const gust = gooseGustCue(state, level);
  const supplyCue = gooseSupplyCue(
    state,
    level,
    landmarkRange,
    Boolean(windWarning),
  );
  const routeCue =
    !state.route ||
    (state.tick - gooseRouteTick) * STEP_SEC < routeConfirmSeconds
      ? gooseRouteCue(state, level)
      : undefined;
  const lesson = gooseTeaching(gooseTeachingProgress, {
    enabled: tips,
    state,
    level,
    leaderZ: leader.pos.z,
    touch: usesTouchFlight(),
    settings,
    abilityHeld: held,
    cameraDragDistance: gooseHorizontalDrag,
    seenReset,
    inWind: Boolean(shear),
  });
  gooseTeachingProgress = lesson.progress;
  const tailwind = gooseTailwindCue(state, level);

  let message = "";
  let footer = "";
  let tailDistance = "";
  const pickupDistance =
    crosswindPickup && rescue?.id === crosswindPickup.actorId
      ? isEnglish()
        ? `When separated, the companion was about ${Math.round(crosswindPickup.distanceToCircle)} units from the rescue circle.`
        : `掉队时直线距接应圈约 ${Math.round(crosswindPickup.distanceToCircle)} 单位`
      : "";
  let tutorial = false;
  if (!playing) {
    // The landing cue displays the group count without the flight controls.
  } else if (rescue) {
    message =
      rescueCount > 1
        ? isEnglish()
          ? `Awaiting rescue: ${rescueCount}`
          : `${rescueCount} 只待接应`
        : copy("接应同伴", "Rescue companion");
    footer =
      approach === "ready"
        ? isEnglish()
          ? `Stay slow · Rescue ${Math.floor((rescue.rescueProgress / GOOSE.pickupTicks) * 100)}%`
          : `保持缓行 · 接应进度 ${Math.floor((rescue.rescueProgress / GOOSE.pickupTicks) * 100)}%`
        : rescueAction;
  } else if (waiting) {
    // The arrival count and reason share a single readout.
  } else if (rejoining) {
    message = copy("同伴正在跟上", "A companion is catching up");
    footer = copy(
      "保持缓行，让雁群重新靠拢。",
      "Stay slow and let the flock close up.",
    );
  } else if (!danger && landingApproach && state.energy > GOOSE.lowEnergy) {
    message = landingApproach.title;
    footer = landingApproach.detail;
  } else if (tailwind && !danger && state.energy > GOOSE.lowEnergy) {
    message = tailwind.title;
    footer = tailwind.detail;
  } else if (
    supplyCue.title &&
    (supplyCue.id !== "resting" || (!routeCue && !crosswind))
  ) {
    message = supplyCue.title;
    footer = supplyCue.detail;
    if (supplyCue.target) {
      const { mark, zone } = supplyCue.target;
      drawMarker(
        mark.id,
        levelLabel(zone),
        mark.pos,
        used,
        "supply",
        true,
        undefined,
        true,
      );
    }
  } else if (danger) {
    // Critical instructions take the upper cue without duplicating route or tutorial text.
  } else if (crosswind) {
    message = crosswind.title;
    footer = crosswind.detail;
    if (crosswind.tail)
      tailDistance = isEnglish()
        ? `The last goose is about ${Math.round(distance(leader.pos, crosswind.tail.pos))} units behind.`
        : `队尾间距约 ${Math.round(distance(leader.pos, crosswind.tail.pos))} 单位`;
  } else if (routeCue) {
    message = routeCue.title;
    footer = routeCue.detail;
  } else if (level.id !== "migration" && routeWarning && !shear) {
    message = levelLabel(routeWarning);
  } else if (windfarm.cue) {
    message = windfarm.cue.title;
    footer = windfarm.cue.detail;
  } else if (gust) {
    message = gust.title;
    footer = gust.detail;
    const { id, label, pos } = gust.target;
    drawMarker(id, label, pos, used, "route", true, undefined, true);
  } else if (
    state.segmentId === "S5" &&
    !state.occupied.includes("gallery-lee") &&
    (state.tick - segmentEnteredTick) * STEP_SEC < 4
  ) {
    message =
      state.formation > 0.94
        ? copy(
            "迎风飞行 · V 字结阵省力",
            "Headwind · V formation saves stamina",
          )
        : copy(
            "迎风飞行 · 直段可结阵省力",
            "Headwind · Form up on straight stretches to save stamina",
          );
  } else if (
    saveMessage &&
    (checkpointTick < 0 ? state.tick < 360 : state.tick - checkpointTick < 420)
  ) {
    message = saveMessage;
  } else if (lesson.cue) {
    message = lesson.cue.title;
    footer = lesson.cue.detail;
    tutorial = true;
  }

  if (playing && rescue)
    drawMarker(
      "rescue",
      copy("待接应同伴", "Companion awaiting rescue"),
      rescue.pos,
      used,
      "rescue",
    );
  if (landingWait?.target)
    drawMarker(
      "landing-companion",
      copy("未抵达同伴", "Companion still on the way"),
      landingWait.target.pos,
      used,
      "gathering",
    );
  const nearbyTail = crosswind?.tail ?? (!danger && landingApproach?.tail);
  if (playing && nearbyTail && !rescue)
    drawMarker(
      "approach-tail",
      copy("队尾", "Last companion"),
      nearbyTail.pos,
      used,
      "gathering",
    );
  if (playing) {
    if (windfarm.direct) {
      const { mark, label } = windfarm.direct;
      drawMarker(
        mark.id,
        label,
        mark.pos,
        used,
        "route",
        true,
        undefined,
        threat === "sweep",
      );
    }
    if (windfarm.bay && !used.has(windfarm.bay.mark.id)) {
      const { mark, label } = windfarm.bay;
      drawMarker(
        mark.id,
        label,
        mark.pos,
        used,
        "supply",
        !rescue || state.energy <= GOOSE.lowEnergy,
      );
    }
    const galleryMarks = level.landmarks.filter(({ id }) =>
      id.startsWith("gallery-"),
    );
    if (
      galleryAhead ||
      (galleryClear &&
        state.segmentId === "S6" &&
        leader.pos.z < galleryClear.pos.z)
    ) {
      const inlet = galleryMarks.find(({ id }) => id === "gallery-inlet");
      const bend = galleryMarks.find(({ id }) => id === "gallery-bend");
      const exit = galleryMarks.find(({ id }) => id === "gallery-exit");
      const wide = galleryMarks.find(({ id }) => id === "gallery-waterway");
      const wideExit = galleryMarks.find(
        ({ id }) => id === "gallery-waterway-exit",
      );
      const wideTarget =
        wide && leader.pos.z > wide.pos.z - 4 ? wideExit : wide;
      const returning =
        state.segmentId === "S6" && Math.cos(leader.heading) < 0;
      const committed =
        inlet &&
        leader.pos.x < inlet.pos.x + 22 &&
        leader.pos.z > inlet.pos.z - 9;
      const turning = bend && leader.pos.z >= bend.pos.z - 2;
      const outlet = exit && leader.pos.x >= exit.pos.x - 7;
      const targets = returning
        ? [wide]
        : committed || (turning && leader.pos.x < -20)
          ? [outlet ? galleryClear : turning ? exit : bend]
          : [
              leader.pos.z < (inlet?.pos.z ?? 0) ? inlet : undefined,
              wideTarget,
            ];
      for (const mark of targets) {
        if (mark && !used.has(mark.id))
          drawMarker(
            mark.id,
            levelLabel(mark),
            mark.pos,
            used,
            "route",
            !rescue || threat === "glass",
          );
      }
    }
    const openingWaypoint =
      state.segmentId === "S0"
        ? openingMarks
            .map((id) => level.landmarks.find((mark) => mark.id === id))
            .find(
              (mark) =>
                mark &&
                (mark.id === "s0-mark" ||
                  (leader.pos.z < mark.pos.z + 4 &&
                    distance(leader.pos, mark.pos) > 8)),
            )
        : undefined;
    const tailwindWaypoint =
      state.segmentId === "S1" && !tailwind?.glider
        ? leader.pos.z < 132
          ? "tailwind-entry"
          : leader.pos.z < gooseTurnLessonEnd
            ? "tailwind-bend"
            : leader.pos.z < 182
              ? "tailwind-next"
              : undefined
        : undefined;
    const seeNextTailwind =
      state.segmentId === "S1" &&
      !tailwind?.glider &&
      leader.pos.z >= gooseTurnLessonStart &&
      leader.pos.z < 190;
    for (const landmark of level.landmarks) {
      if (
        !used.has(landmark.id) &&
        !landmark.id.startsWith("gallery-") &&
        !isGooseGustLandmark(landmark.id) &&
        (!waiting || landmark.id !== "goal-mark") &&
        landmark.id !== "wind-east-exit" &&
        (!openingMarks.includes(landmark.id) ||
          landmark.id === openingWaypoint?.id) &&
        (!tailwind?.glider ||
          !["pass-mark", "lake-mark"].includes(landmark.id)) &&
        (!tailwindCourseMarks.includes(landmark.id) ||
          landmark.id === tailwindWaypoint ||
          (seeNextTailwind &&
            (landmark.id === "tailwind-next" ||
              landmark.id === "tailwind-wide"))) &&
        (!["outer-mark", "wind-exit", "reserve-entry"].includes(landmark.id) ||
          (level.id !== "migration" && !windWarning)) &&
        (landmark.kind === "beacon" ||
          (landmark.kind === "reed" && informativeReeds.has(landmark.id))) &&
        distance(leader.pos, landmark.pos) <= landmarkRange
      ) {
        const depleted = supply.some(
          (zone) =>
            zone.label === landmark.label &&
            (state.supply[zone.id] ?? 0) === 0 &&
            contains(zone.points, landmark.pos),
        );
        const forkRoute =
          landmark.id === "pass-mark" || landmark.id === "lake-mark";
        const routeWaypoint =
          forkRoute ||
          landmark.id === openingWaypoint?.id ||
          landmark.id === tailwindWaypoint ||
          (seeNextTailwind &&
            (landmark.id === "tailwind-next" ||
              landmark.id === "tailwind-wide")) ||
          landmark.id === "goal-mark";
        const bayMarker = landmark.id === "reserve-entry" && baySupply;
        let label = levelLabel(landmark);
        if (level.id === "migration" && state.segmentId === "S2") {
          if (landmark.id === "pass-mark")
            label = copy(
              "短山口 · 风向分水岭",
              "Mountain Pass · Wind toward the ridge",
            );
          if (landmark.id === "lake-mark")
            label = lakeAvailable
              ? copy(
                  "长湖路 · 沿岸补给",
                  "Long Lake Route · Refuel along the shore",
                )
              : copy("长湖路 · 风势较稳", "Long Lake Route · Calmer winds");
          if (ridgeRecovery && landmark.id === "pass-mark")
            label = copy("绕向短山口", "Detour via the Mountain Pass");
          if (ridgeRecovery && landmark.id === "lake-mark")
            label = copy("绕向长湖路", "Detour via the Long Lake Route");
        }
        drawMarker(
          landmark.id,
          depleted
            ? isEnglish()
              ? `${label} · Depleted`
              : `${label} · 已用尽`
            : label,
          landmark.pos,
          used,
          landmark.id === openingWaypoint?.id && tutorial && !state.airborne
            ? "pin"
            : routeWaypoint
              ? "route"
              : depleted || bayMarker
                ? "supply"
                : "landmark",
          !depleted &&
            ((forkRoute && threat === "ridge") ||
              ((routeWaypoint || landmark.kind === "beacon") &&
                !rescue &&
                !danger)),
          undefined,
          Boolean(ridgeRecovery && forkRoute && !rescue),
        );
      }
    }
  }
  for (const [id, label] of labels) label.hidden = !used.has(id);
  const timeInSegment = (state.tick - segmentEnteredTick) * STEP_SEC;
  const showSegment =
    playing &&
    !danger &&
    !rescue &&
    !waiting &&
    timeInSegment < segmentRevealSeconds;
  setText(segmentName, levelTitle(currentSegment ?? level));
  segmentName.hidden = !showSegment;
  if (showSegment) {
    const opacity = Math.min(
      1,
      (segmentRevealSeconds - timeInSegment) / segmentFadeSeconds,
    );
    flightCue.style.setProperty("--place-opacity", opacity.toFixed(3));
  }
  dismiss.hidden = !tutorial;
  const gesture = tutorial && usesTouchFlight() ? lesson.cue?.id : undefined;
  if (gesture === "takeoff" || gesture === "orbit") {
    if (shownGesture !== gesture) {
      shownGesture = gesture;
      gestureEnteredTick = state.tick;
      gestureHint.dataset.actionSide = gesture === "orbit" ? "observe" : "move";
      setText(
        gestureCopy,
        gesture === "orbit"
          ? copy("拖动观察", "Drag to look")
          : copy("按住拖动", "Hold and drag"),
      );
    }
  }
  gestureHint.toggleAttribute(
    "data-active",
    gesture !== undefined &&
      gesture === shownGesture &&
      (state.tick - gestureEnteredTick) * STEP_SEC < gestureRevealSeconds,
  );
  rescueClock.hidden = !playing || !rescue;
  const rescueTimeLabel =
    rescueCount > 1
      ? copy("最短剩余接应时间", "Earliest rescue timeout")
      : copy("剩余接应时间", "Rescue time remaining");
  if (rescueClock.getAttribute("aria-label") !== rescueTimeLabel)
    rescueClock.setAttribute("aria-label", rescueTimeLabel);
  const seconds = rescue ? remainingSeconds(rescue.rescueTicks) : undefined;
  setText(rescueSeconds, seconds === undefined ? "" : String(seconds));
  energyStatus.hidden = !flightControls;
  setText(energyLabel, copy("体力", "Stamina"));
  const stamina = gooseStamina(state.energy, supplyCue.recovering);
  const boosting =
    playing &&
    state.energy > GOOSE.boostCutoff &&
    state.ridgeRecovery !== "blocked" &&
    leader.speed > GOOSE.cruise &&
    Math.hypot(flightInput.move.x, flightInput.move.z) >= GOOSE.boostInput;
  energyStatus.dataset.level = stamina.level;
  setText(
    energyCondition,
    stamina.text || (boosting ? copy("加速中", "Boosting") : ""),
  );
  setText(energyPercent, `${Math.round(state.energy * 100)}%`);
  setText(notice, message);
  setText(detail, footer);
  showText(
    gooseCrosswindDistance,
    playing ? pickupDistance || tailDistance : "",
  );
  flightCue.dataset.kind = landing
    ? "landing"
    : playing && rescue
      ? "rescue"
      : tutorial
        ? "tutorial"
        : showSegment && !message
          ? "place"
          : "status";
  flightCue.hidden = !message && !showSegment && !waiting && !landing;
  const hazardDetail =
    ridgeRecovery && !rescue
      ? `${usesTouchFlight() ? copy("轻推摇杆", "Push the stick gently") : isEnglish() ? `Hold ${keyLabel(settings.bindings.slow)} to slow down` : `按住 ${keyLabel(settings.bindings.slow)} 缓行`}${copy("，", ". ")}${warning.detail}`
      : rescue || message || waiting
        ? ""
        : (warning?.detail ?? "");
  setText(hazardNotice, danger);
  setText(warningDetail, hazardDetail);
  hazardCue.hidden = !danger;

  const basis = scene?.camera.basis();
  const targetDirection = (target: Vec2): string =>
    basis ? screenDirection(leader.pos, target, basis) : "";
  const cue = [message, rescue ? rescueAction : footer];
  if (rescue)
    cue.push(
      isEnglish()
        ? `Companion awaiting rescue ${targetDirection(rescue.pos)}`
        : `待接应同伴${targetDirection(rescue.pos)}`,
    );
  if (pickupDistance) cue.push(pickupDistance);
  if (landingWait)
    cue.push(copy("等待同伴", "Waiting for companions"), landingWait.action);
  if (playing && seconds !== undefined && seconds <= 10)
    cue.push(
      seconds <= 5
        ? copy("剩余接应时间在 5 秒以内", "Under 5 seconds left to rescue")
        : copy("剩余接应时间在 10 秒以内", "Under 10 seconds left to rescue"),
    );
  if (playing && stamina.text)
    cue.unshift(
      isEnglish() ? `Stamina ${stamina.text}` : `体力${stamina.text}`,
    );
  else if (boosting) cue.push(copy("正在加速", "Boosting"));
  // Announce actions and thresholds, not the changing rescue percent or timer.
  setText(
    gooseFlightAnnouncement,
    landing
      ? isEnglish()
        ? `All ${goal.arrived} geese have arrived. Landing now.`
        : `${goal.arrived} 只雁全部抵达，开始降落。`
      : playing
        ? cue
            .filter(Boolean)
            .map((text) => text.replace(/[.。]$/, ""))
            .join(copy("。", ". "))
        : "",
  );
  const routeDirection =
    threat === "sweep" && windfarm.direct
      ? isEnglish()
        ? `Outer channel ${targetDirection(windfarm.direct.mark.pos)}`
        : `外围航道${targetDirection(windfarm.direct.mark.pos)}`
      : threat === "ridge" && !state.route
        ? isEnglish()
          ? `The Mountain Pass has stronger crosswinds. The Long Lake Route has calmer winds${lakeAvailable ? " and supplies along the shore" : ""}`
          : `短山口侧风较强。长湖路较稳${lakeAvailable ? copy("，沿岸可补给", " and supplies along the shore") : ""}`
        : "";
  setText(
    gooseHazardAnnouncement,
    [danger, routeDirection, hazardDetail]
      .filter(Boolean)
      .join(copy("。", ". ")),
  );
  worldMarkers.render(
    scene instanceof FlightScene ? scene.project(leader.pos) : undefined,
  );
}

function showWhaleHud(state: WhaleState, level: WhaleLevel): void {
  const leader = leaderOf(state);
  const playing = state.phase === "playing";
  const landing = state.phase === "landing";
  const controls = playing || state.phase === "paused";
  const command = input.sample();
  if (playing && state.segmentId !== "W0") tips = false;
  if (playing && tips) {
    if (leader.speed > 0.5) movedForTutorial = true;
    if (
      movedForTutorial &&
      leader.speed < 0.15 &&
      command.move.x === 0 &&
      command.move.z === 0
    )
      seenGlide = true;
    if (leader.dive.layer !== "surface") whaleSubmerged = true;
    if (
      whaleSubmerged &&
      !whaleRecovered &&
      state.actors.every((actor) => surfaced(actor) && actor.dive.breath === 1)
    )
      whaleRecovered = true;
  }
  const guidance = whaleGuidance(state, level, tips, {
    dragged: cameraDragDistance >= WHALE_TUTORIAL_DRAG,
    reset: seenReset,
    moved: movedForTutorial,
    stopped: seenGlide,
    submerged: whaleSubmerged,
    recovered: whaleRecovered,
    toggle: settings.toggle,
    desktop: !coarsePointer.matches,
    moveKey: movementLabel(settings.bindings),
    diveKey: keyLabel(settings.bindings.formation),
    resetKey: keyLabel(settings.bindings.recenter),
  });
  setText(whaleDepth, guidance.depthLabel);
  setText(whaleDepthCue, guidance.depthCue);
  whaleBreath.value = guidance.breath;
  setText(whaleBreathValue, `${Math.round(guidance.breath * 100)}%`);
  whaleStatus.dataset.level =
    guidance.breath <= WHALE.lowBreath ? "low" : "normal";
  const pressed = String(command.ability);
  if (ability.getAttribute("aria-pressed") !== pressed)
    ability.setAttribute("aria-pressed", pressed);
  ability.dataset.state =
    leader.dive.direction === "up"
      ? "releasing"
      : leader.dive.direction === "down"
        ? "forming"
        : leader.dive.layer !== "surface"
          ? "formed"
          : "idle";
  ability.style.setProperty("--formation", String(guidance.transition));
  setText(formationLabel, copy("下潜", "Dive"));
  setText(formationStatus, "");
  skipLanding.hidden = !landing;
  pauseButton.hidden = !controls && !landing;
  resetButton.hidden = !controls;
  ability.hidden = !controls;
  dismiss.hidden = !guidance.tutorial;
  arrivalStatus.hidden = !guidance.arrival.visible;
  setText(arrivalCaption, guidance.arrival.caption);
  setText(arrivedCount, guidance.arrival.count);
  energyStatus.hidden = !playing;
  setText(energyLabel, copy("能量", "Energy"));
  setText(energyCondition, "");
  energyStatus.dataset.level =
    state.energy <= WHALE.boostCutoff
      ? "critical"
      : state.energy <= WHALE.lowEnergy
        ? "low"
        : "normal";
  energy.value = state.energy;
  setText(energyPercent, `${Math.round(state.energy * 100)}%`);
  rescueClock.hidden = guidance.rescue === null;
  setText(
    rescueSeconds,
    guidance.rescue ? String(remainingSeconds(guidance.rescue.ticks)) : "",
  );
  whaleRescueMeter.hidden = guidance.rescue === null;
  if (guidance.rescue) whaleRescueProgress.value = guidance.rescue.progress;
  whaleCohesionMeter.hidden = guidance.routeCohesion === null;
  if (guidance.routeCohesion !== null) {
    whaleCohesion.value = guidance.routeCohesion;
    setText(whaleCohesionValue, `${Math.round(guidance.routeCohesion * 100)}%`);
  }
  if (shownSegment !== state.segmentId) {
    shownSegment = state.segmentId;
    segmentEnteredTick = state.tick;
  }
  setText(
    segmentName,
    levelTitle(
      level.segments.find(({ id }) => id === state.segmentId) ?? level,
    ),
  );
  segmentName.hidden =
    !playing ||
    !!guidance.danger ||
    (state.segmentId === "W3" && !!guidance.notice) ||
    (state.tick - segmentEnteredTick) * STEP_SEC >= segmentRevealSeconds;
  flightCue.dataset.kind = landing
    ? "landing"
    : guidance.rescue
      ? "rescue"
      : guidance.tutorial
        ? "tutorial"
        : "status";
  setText(notice, guidance.notice);
  const checkpointMessage =
    playing && state.tick - checkpointTick < 60 * 4 && checkpointTick >= 0
      ? saveMessage
      : "";
  setText(detail, guidance.detail);
  setText(whaleSaveDetail, checkpointMessage);
  flightCue.hidden =
    (!playing && !landing) ||
    (segmentName.hidden &&
      !guidance.notice &&
      !guidance.detail &&
      !checkpointMessage &&
      !guidance.arrival.visible);
  hazardCue.hidden = !guidance.danger;
  setText(hazardNotice, guidance.danger);
  setText(warningDetail, guidance.warningDetail);
  const ship = guidance.markers.find(({ id }) => id === "cargo-ship");
  if (
    ship &&
    scene &&
    !(scene instanceof FlightScene) &&
    scene.species === "whale"
  ) {
    // Leave the moving hull visible. Keep the card steady as the bow crosses center.
    const { x } = scene.project(ship.pos);
    const previous = hazardCue.dataset.shipSide;
    const side = x < 43 ? "right" : x > 57 ? "left" : (previous ?? "left");
    if (side !== previous) hazardCue.dataset.shipSide = side;
  } else if (hazardCue.dataset.shipSide !== undefined) {
    delete hazardCue.dataset.shipSide;
  }
  const whaleScene =
    scene && !(scene instanceof FlightScene) && scene.species === "whale"
      ? scene
      : undefined;
  const shortGap =
    state.segmentId === "W2" &&
    level.landmarks.find(({ id }) => id === "net-gap");
  const opening =
    shortGap && Math.abs(shortGap.pos.z - leader.pos.z) < 65
      ? whaleScene?.project(shortGap.pos, leader.dive.depth)
      : undefined;
  if (opening) {
    const side =
      opening.x < 46
        ? "right"
        : opening.x > 54
          ? "left"
          : (hud.dataset.netSide ?? "left");
    if (hud.dataset.netSide !== side) hud.dataset.netSide = side;
  } else if (hud.dataset.netSide) {
    delete hud.dataset.netSide;
  }
  markerLayer.dataset.camera = scene?.camera.mode ?? "Follow";
  const used = new Set<string>();
  for (const marker of guidance.markers) {
    drawMarker(
      marker.id,
      levelLabel(marker),
      marker.pos,
      used,
      marker.kind,
      marker.allowEdge,
      marker.depth,
    );
  }
  for (const [id, label] of labels) label.hidden = !used.has(id);
  worldMarkers.render(
    whaleScene?.project(leader.pos, leader.dive.depth),
    opening,
  );
}

function showReindeerHud(state: ReindeerState, level: ReindeerLevel): void {
  const leader = leaderOf(state);
  const playing = state.phase === "playing";
  const landing = state.phase === "landing";
  const controls = playing || state.phase === "paused";
  const lane = onRoad(level.road, leader.pos);
  const underpass = insideCulvert(level.road, leader.pos);
  const warned =
    playing && state.occupied.includes("vehicle-warning") && !underpass;
  const goalZone = level.zones.find(({ kind }) => kind === "goal");
  const goal = goalStatus(state, goalZone);
  const teammate = playing
    ? reindeerTeammateGuidance(
        state,
        level,
        goal.leaderArrived ? goalZone : undefined,
      )
    : undefined;
  const rescue = teammate?.kind === "rescue" ? teammate.actor : undefined;
  const waiting = state.waitTicks > 0;
  const planted = leader.speed === 0;
  const gather = reindeerGatherStatus(state, level);
  const passage =
    playing && !lane ? reindeerPassageGuidance(state, level) : undefined;
  const dust = playing ? reindeerDustGuidance(state, level) : undefined;
  const shoulder =
    warned &&
    leader.pos.z < level.road.culvert.near &&
    state.occupied.includes("near-shoulder");
  const overlook = playing && state.occupied.includes("thaw-overlook");
  const gatherNotice = !planted
    ? copy("领鹿正在停步", "The lead reindeer is slowing to a stop")
    : gather.ready
      ? dust
        ? copy("全队已靠拢", "The herd is together")
        : copy("全队已靠拢，可以出发", "The herd is together and ready to go")
      : isEnglish()
        ? `Gathering companions: ${gather.gathered} of ${gather.total}`
        : `同伴正在靠拢 ${gather.gathered} / ${gather.total}`;
  const gatherHint = gather.blockedIds.length
    ? copy(
        "有同伴被地形隔开，沿通路回到它的一侧。",
        "Terrain separates a companion. Follow the trail back to their side.",
      )
    : gather.outOfRangeIds.length
      ? copy(
          "有同伴超出呼唤范围，沿小径回去接近它。",
          "A companion is out of calling range. Follow the trail back toward them.",
        )
      : "";
  if (playing && state.segmentId !== "R0") tips = false;
  const tutorial = playing && tips && state.segmentId === "R0";
  if (tutorial && waiting && gather.ready) reindeerCalled = true;
  const winterTail = tutorial ? reindeerWinterTail(state, level) : undefined;
  const winterBend = tutorial && reindeerWinterBend(state, level);
  const abilityKey = keyLabel(settings.bindings.formation);
  const resetKey = keyLabel(settings.bindings.recenter);
  const walkInstruction = coarsePointer.matches
    ? isEnglish()
      ? `Push the stick on the ${settings.mirror ? "right" : "left"} and follow the hoofprints.`
      : `推${settings.mirror ? copy("右", "right") : copy("左", "left")}侧摇杆，沿蹄印走。`
    : isEnglish()
      ? `Use ${movementLabel(settings.bindings)} to follow the hoofprints.`
      : `用 ${movementLabel(settings.bindings)} 沿蹄印走。`;
  const callInstruction = coarsePointer.matches
    ? settings.toggle
      ? copy(
          "点按「等候」，让队友靠拢。",
          "Tap Wait to call the herd together.",
        )
      : copy(
          "按住「等候」，让队友靠拢。",
          "Hold Wait to call the herd together.",
        )
    : isEnglish()
      ? `${settings.toggle ? "Tap" : "Hold"} ${abilityKey} to call the herd together.`
      : `${settings.toggle ? copy("点按", "Tap") : copy("按住", "Hold")} ${abilityKey}，让队友靠拢。`;
  const lesson = winterTail
    ? isEnglish()
      ? `The herd is spread out. Release to stop. ${callInstruction}`
      : `队尾拉开了。可松手停步，也可${callInstruction}`
    : winterBend
      ? copy(
          "沿两侧蹄迹绕过雪堆，转弯后收速。",
          "Follow either set of hoofprints around the snowdrift, then ease off.",
        )
      : !reindeerCalled
        ? walkInstruction
        : cameraDragDistance < 12
          ? isEnglish()
            ? `Drag on the ${settings.mirror ? "left" : "right"} to look back at the herd.`
            : `在${settings.mirror ? copy("左", "left") : copy("右", "right")}侧拖动镜头，看看队尾。`
          : !seenReset
            ? coarsePointer.matches
              ? copy(
                  "点「复位」，重新看向小径。",
                  "Tap Reset Camera to face the trail again.",
                )
              : isEnglish()
                ? `Press ${resetKey} to face the trail again.`
                : `按 ${resetKey}，重新看向小径。`
            : copy("沿林间小径出发。", "Set out along the woodland trail.");
  const checkpointMessage =
    playing && checkpointTick >= 0 && state.tick - checkpointTick < 240
      ? saveMessage
      : "";
  const importantTeammate =
    teammate && (teammate.kind !== "on-way" || goal.leaderArrived);
  const localNotice =
    checkpointMessage ||
    (passage?.notice ??
      dust?.notice ??
      (shoulder
        ? copy("路肩集队点", "Roadside Gathering Point")
        : overlook
          ? copy("融雪观景坡", "Snowmelt Overlook")
          : ""));
  const localDetail =
    passage?.detail ??
    dust?.detail ??
    (shoulder
      ? copy(
          "可在路肩呼唤队尾，或沿蹄迹直接下坡。",
          "Call the herd from the shoulder, or follow the hoofprints downhill.",
        )
      : overlook
        ? copy(
            "可停步回望鹿群，也可沿融雪小径去落脚。",
            "Stop and look back at the herd, or follow the snowmelt trail to the finish.",
          )
        : "");
  const cue = importantTeammate
    ? teammate.notice
    : landing
      ? ""
      : underpass
        ? copy("动物通道", "Wildlife Crossing")
        : waiting
          ? gatherNotice
          : tutorial
            ? lesson
            : localNotice || teammate?.notice || "";
  const hint = importantTeammate
    ? [teammate.detail, passage?.notice].filter(Boolean).join(" · ")
    : underpass
      ? [passage?.notice, localDetail].filter(Boolean).join(" · ")
      : waiting
        ? [
            gatherHint,
            passage?.notice ?? dust?.notice,
            passage?.detail ?? dust?.detail,
          ]
            .filter(Boolean)
            .join(" · ")
        : localDetail ||
          teammate?.detail ||
          (state.energy <= REINDEER.lowEnergy && playing
            ? copy(
                "体力偏低，留意补给与休息地。",
                "Low stamina. Watch for supplies and rest areas.",
              )
            : "");
  ability.setAttribute("aria-disabled", String(lane));
  ability.setAttribute("aria-pressed", String(state.waitTicks > 0));
  ability.dataset.state =
    waiting && gather.ready ? "formed" : state.waitTicks ? "forming" : "idle";
  ability.style.setProperty(
    "--formation",
    String(state.waitTicks / REINDEER.waitTicks),
  );
  setText(
    formationStatus,
    lane
      ? copy("先离开车道", "Leave the road first")
      : waiting
        ? planted
          ? isEnglish()
            ? `Gathered: ${gather.gathered} of ${gather.total}`
            : `已靠拢 ${gather.gathered} / ${gather.total}`
          : copy("正在停步", "Stopping")
        : "",
  );
  setText(formationLabel, copy("等候", "Wait"));
  energyStatus.hidden = !playing;
  energyStatus.dataset.level =
    state.energy <= REINDEER.criticalEnergy
      ? "critical"
      : state.energy <= REINDEER.lowEnergy
        ? "low"
        : "normal";
  energy.value = state.energy;
  setText(energyLabel, copy("体力", "Stamina"));
  setText(energyPercent, `${Math.round(state.energy * 100)}%`);
  showText(
    energyCondition,
    playing && state.energy <= REINDEER.lowEnergy
      ? copy("寻找补给", "Find supplies")
      : "",
  );
  showText(
    hazardNotice,
    playing && lane
      ? copy("先离开车道", "Leave the road first")
      : warned
        ? leader.pos.z > level.road.far
          ? copy(
              "后方车道有车流 · 可在远侧路肩等候",
              "Traffic behind you · Wait on the far shoulder",
            )
          : copy(
              "车道有车流 · 沿路肩找动物通道",
              "Traffic on the road · Find the wildlife crossing along the shoulder",
            )
        : "",
  );
  setText(
    warningDetail,
    playing && lane
      ? copy(
          "用摇杆走向路肩，那里可以等候。",
          "Use the stick to reach the shoulder, where you can wait.",
        )
      : "",
  );
  hazardCue.hidden = !warned && !(playing && lane);
  rescueClock.hidden = !rescue || !playing;
  setText(
    rescueSeconds,
    rescue ? String(remainingSeconds(rescue.rescueTicks ?? 0)) : "",
  );
  arrivalStatus.hidden = !goal.leaderArrived && !landing;
  flightCue.dataset.teammate = teammate?.kind ?? "";
  setText(
    arrivalCaption,
    goal.canLand
      ? copy("全队落脚", "Herd settling in")
      : copy("等待同伴", "Waiting for companions"),
  );
  setText(arrivedCount, `${goal.arrived} / ${goal.expected}`);
  skipLanding.hidden = !landing;
  pauseButton.hidden = !controls && !landing;
  resetButton.hidden = !controls;
  ability.hidden = !controls;
  dismiss.hidden = !tutorial;
  if (shownSegment !== state.segmentId) {
    shownSegment = state.segmentId;
    segmentEnteredTick = state.tick;
  }
  const title = levelTitle(
    level.segments.find(({ id }) => id === state.segmentId) ?? level,
  );
  setText(segmentName, title);
  segmentName.hidden =
    !playing ||
    warned ||
    (state.tick - segmentEnteredTick) * STEP_SEC >= segmentRevealSeconds;
  setText(notice, playing ? cue : "");
  setText(detail, playing ? hint : "");
  flightCue.dataset.kind = landing
    ? "landing"
    : rescue
      ? "rescue"
      : tutorial
        ? "tutorial"
        : "status";
  flightCue.hidden =
    (!playing && !landing) ||
    (segmentName.hidden && !cue && !hint && arrivalStatus.hidden);
  markerLayer.dataset.camera = scene?.camera.mode ?? "Follow";

  const used = new Set<string>();
  if (landing && reindeerLandingId) {
    const companion = state.actors.find(({ id }) => id === reindeerLandingId);
    if (companion)
      drawMarker(
        companion.id,
        copy("最后一位同伴已归队", "The last companion has rejoined"),
        companion.pos,
        used,
        "gathering",
      );
  }
  if (playing) {
    const careId = gather.blockedIds[0] ?? gather.outOfRangeIds[0];
    const careActor = state.actors.find(({ id }) => id === careId);
    if (waiting && !teammate && careActor)
      drawMarker(
        careActor.id,
        gather.blockedIds.includes(careActor.id)
          ? copy("被地形隔开", "Separated by terrain")
          : copy("超出呼唤范围", "Out of calling range"),
        careActor.pos,
        used,
        "gathering",
      );
    if (dust?.next)
      drawMarker(
        dust.next.id,
        levelLabel(dust.next),
        dust.next.pos,
        used,
        "route",
      );
    if (passage?.runout)
      drawMarker(
        "fence-runout",
        copy(
          "沿直蹄迹到这里再转",
          "Follow the straight hoofprints here, then turn",
        ),
        passage.runout,
        used,
        "route",
      );
    const roadMiddle = (level.road.near + level.road.far) / 2;
    const nearSide = leader.pos.z <= roadMiddle;
    const roadGuide = warned
      ? nearSide
        ? "culvert-sign"
        : "culvert-exit"
      : undefined;
    for (const marker of level.landmarks) {
      const choice =
        (winterBend &&
          (marker.id === "winter-trail" || marker.id === "winter-right")) ||
        (passage?.choices &&
          (marker.id === "wide-sign" || marker.id === "short-fence-sign")) ||
        (dust?.fork &&
          (marker.id === "dust-sign" || marker.id === "green-sign"));
      if (
        marker.id === dust?.next?.id ||
        (passage?.runout &&
          (marker.id === "short-fence-exit" ||
            marker.id === "short-fence-sign" ||
            marker.id === "narrow-sign" ||
            marker.id === "wide-sign")) ||
        (!choice &&
          (distance(leader.pos, marker.pos) > 39 ||
            (marker.pos.z < leader.pos.z - 6 && marker.id !== roadGuide)))
      )
        continue;
      const kind = ["supply-sign", "green-return"].includes(marker.id)
        ? "supply"
        : "route";
      const essential =
        choice ||
        marker.id === roadGuide ||
        (shoulder && marker.id === "shoulder-sign") ||
        (underpass && marker.id === "culvert-exit") ||
        (marker.id === "supply-sign" && state.energy <= REINDEER.lowEnergy);
      const text =
        marker.id === "culvert-exit" && roadGuide === marker.id
          ? copy("动物通道 · 远侧入口", "Wildlife Crossing · Far Entrance")
          : levelLabel(marker);
      drawMarker(marker.id, text, marker.pos, used, kind, essential);
    }
    if (warned) {
      const roadPosition = {
        x: leader.pos.x,
        z: nearSide ? level.road.near : level.road.far,
      };
      drawMarker(
        "road-edge",
        copy("车道边缘", "Road edge"),
        roadPosition,
        used,
        "hazard",
      );
      const vehicle = roadVehicle(level);
      const points = hazardPoints(vehicle, state.tick);
      const direction = vehicleDirection(vehicle, state.tick);
      const leadingX =
        direction > 0
          ? Math.max(...points.map(({ x }) => x))
          : Math.min(...points.map(({ x }) => x));
      const z =
        (Math.min(...points.map((point) => point.z)) +
          Math.max(...points.map((point) => point.z))) /
        2;
      if ((leader.pos.x - leadingX) * direction > 0)
        drawMarker(
          "approaching-car",
          copy("来车", "Oncoming vehicle"),
          { x: leadingX, z },
          used,
          "hazard",
        );
    }
    const tail = importantTeammate
      ? teammate
      : (passage?.tail ??
        dust?.tail ??
        (winterTail
          ? { actor: winterTail, label: copy("队尾", "Last companion") }
          : teammate));
    if (tail)
      drawMarker(
        tail.actor.id,
        tail.label,
        tail.actor.pos,
        used,
        tail.actor === rescue ? "rescue" : "gathering",
      );
    if (teammate?.opening)
      drawMarker(
        "blocked-row-opening",
        copy("这排围栏的宽口", "Wide gap in this fence"),
        teammate.opening,
        used,
        "route",
      );
  }
  for (const [id, label] of labels) label.hidden = !used.has(id);
}

function frame(time: number): void {
  const frameDelta = lastFrame === undefined ? 0 : (time - lastFrame) / 1000;
  const delta = Math.min(0.1, frameDelta);
  lastFrame = time;
  if (runtime && scene && !contextLost && !document.hidden) {
    const flightView = !hud.hidden && !touchPortrait.matches;
    const active = flightView && runtime.current.phase === "playing";
    const alpha = clock.frame(time, active, () => {
      if (!runtime) return false;
      runtime.dispatch({ type: "input", input: input.sample() });
      events(runtime.step());
      if (runtime.current.species === "reindeer" && runtime.current.waitBlocked)
        input.clearAbilityToggle();
      return runtime.current.phase === "playing";
    });
    if (flightView && runtime.current.phase === "landing" && !landingPaused) {
      presentationSeconds += delta;
      if (presentationSeconds >= 3.6) finishLanding();
    }
    const landing =
      runtime.current.phase === "landing"
        ? Math.min(1, presentationSeconds / 3.35)
        : runtime.current.phase === "completed"
          ? 1
          : 0;
    const { previous, current } = runtime;
    if (
      scene &&
      !(scene instanceof FlightScene) &&
      scene.species === "whale" &&
      previous.species === "whale" &&
      current.species === "whale"
    ) {
      const practiced =
        movedForTutorial &&
        seenGlide &&
        cameraDragDistance >= WHALE_TUTORIAL_DRAG &&
        seenReset &&
        whaleRecovered;
      scene.render(
        previous,
        current,
        alpha,
        delta,
        settings,
        landing,
        tips && !practiced,
      );
    }
    if (
      scene instanceof FlightScene &&
      previous.species === "goose" &&
      current.species === "goose"
    )
      scene.render(previous, current, alpha, delta, settings, landing);
    if (
      !(scene instanceof FlightScene) &&
      scene.species === "reindeer" &&
      previous.species === "reindeer" &&
      current.species === "reindeer"
    )
      scene.render(
        previous,
        current,
        alpha,
        landingPaused ? 0 : delta,
        settings,
        landing,
        reindeerLandingId,
      );
    if (flightView && !landingPaused)
      music.render(
        runtime.current,
        settings.music,
        runtime.level,
        current.species === "reindeer" && current.phase === "landing"
          ? { progress: landing, companion: reindeerLandingId }
          : undefined,
      );
    showHud();
    if (diagnostics) {
      const state = runtime.current;
      const leader = leaderOf(state);
      if (active && state.species === "reindeer" && reindeerStartup) {
        game.dataset.reindeerStartup = JSON.stringify({
          revision: state.levelRevision,
          from: reindeerStartup.from,
          checkpoint: reindeerStartup.checkpoint,
          titleReadyMs,
          firstPlayableFrameMs: Math.max(
            0,
            performance.now() - reindeerStartup.at,
          ),
        });
        reindeerStartup = undefined;
      }
      const rescue =
        state.species === "goose"
          ? gooseRescue(state).target
          : state.actors.find((actor) => actor.status === "strayed");
      game.dataset.flight = JSON.stringify({
        revision: state.levelRevision,
        species: state.species,
        tick: state.tick,
        phase: state.phase,
        mode: state.mode,
        segment: state.segmentId,
        route: state.route,
        failure: state.failure,
        x: leader.pos.x,
        z: leader.pos.z,
        heading: leader.heading,
        energy: state.energy,
        speed: leader.speed,
        occupied: state.occupied,
        ...(state.species === "goose"
          ? {
              formation: state.formation,
              ridgeRecovery: state.ridgeRecovery,
              encounters: state.encounters,
            }
          : state.species === "whale"
            ? {
                dive: leaderOf(state).dive,
                actors: state.actors,
                checkpoint: runtime.checkpoint.id,
                framedWhales:
                  state.phase === "landing" &&
                  !(scene instanceof FlightScene) &&
                  scene.species === "whale"
                    ? scene.framedWhales()
                    : undefined,
                landingProgress:
                  state.phase === "landing" ? landing : undefined,
              }
            : {
                actors: state.actors,
                checkpoint: runtime.checkpoint.id,
                waitTicks: state.waitTicks,
                waitBlocked: state.waitBlocked,
                alarmTicks: state.alarmTicks,
                cohesion: state.cohesion,
                landingCompanion:
                  state.phase === "landing" ? reindeerLandingId : undefined,
                landingProgress:
                  state.phase === "landing" ? landing : undefined,
              }),
        rescue: rescue && {
          ...rescue.pos,
          id: rescue.id,
          ticks: rescue.rescueTicks,
          progress: rescue.rescueProgress,
        },
        basis: scene.camera.basis(),
        camera: scene.camera.viewAngles(),
        scenery: scene.sceneryReport(),
        reef:
          !(scene instanceof FlightScene) && scene.species === "whale"
            ? scene.reefReport()
            : undefined,
      });
      const measuring =
        active || (flightView && state.phase === "landing" && !landingPaused);
      const sampleKey = measuring
        ? `${state.species}/${state.segmentId}/${state.phase}/${settings.low}`
        : "";
      if (performanceWindow !== sampleKey) {
        performanceWindow = sampleKey;
        frameDurations.length = 0;
        lastReport = time;
        delete game.dataset.performance;
      }
      if (measuring && frameDelta > 0) {
        frameDurations.push(frameDelta * 1000);
        if (frameDurations.length > 180) frameDurations.shift();
        if (time - lastReport >= 600 && frameDurations.length >= 30) {
          const durations = [...frameDurations].sort((a, b) => a - b);
          const { calls, triangles } = scene.renderer.info.render;
          const { geometries, textures } = scene.renderer.info.memory;
          game.dataset.performance = JSON.stringify({
            segment: state.segmentId,
            phase: state.phase,
            tick: state.tick,
            samples: durations.length,
            medianMs: durations[Math.floor(durations.length / 2)],
            p95Ms: durations[Math.floor(durations.length * 0.95)],
            calls,
            triangles,
            geometries,
            textures,
            width: canvas?.width,
            height: canvas?.height,
            quality: settings.low ? "low" : "standard",
          });
          lastReport = time;
        }
      }
    }
  }
  requestAnimationFrame(frame);
}

async function boot(): Promise<void> {
  retryChapterLoad = undefined;
  retryLoad.hidden = true;
  bootStatus.hidden = false;
  showBootMessage(() =>
    copy("正在打开晨雾湿地…", "Opening the dawn wetlands…"),
  );
  try {
    if (!flightScene) {
      const context = canvas?.getContext("webgl2", {
        antialias: true,
        alpha: false,
      });
      if (!canvas || !context) {
        showBootMessage(() =>
          copy(
            "无法启动 WebGL 2。请检查浏览器的硬件加速设置，或换用支持 WebGL 2 的浏览器。",
            "WebGL 2 could not start. Check your browser’s hardware acceleration setting or use a browser that supports WebGL 2.",
          ),
        );
        retryLoad.hidden = false;
        return;
      }
      flightScene = new FlightScene(
        canvas,
        context,
        query.get("diagnostics") === "terrain",
      );
    }
    [migration, goose] = await Promise.all([
      loadLevel("migration"),
      loadFlightAssets(),
    ]);
    runtime = new GameRuntime(migration, "journey");
    scene = flightScene;
    scene.setLevel(migration, goose, settings.low);
    updateChapterMenu();
    bootStatus.hidden = true;
    menuActions.hidden = false;
    if (diagnostics && titleReadyMs === undefined)
      titleReadyMs = performance.now();
    if (!coarsePointer.matches && document.activeElement === document.body) {
      enterGame.focus({ preventScroll: true });
    }
  } catch (error) {
    console.error(error);
    showBootMessage(() =>
      copy("无法打开游戏，请重试。", "Could not open the game. Try again."),
    );
    retryLoad.hidden = false;
  }
}

game.tabIndex = -1;
setupLanguagePicker(element<HTMLSelectElement>("language"), () => {
  setText(bootStatus, bootMessage());
  updateChapterMenu();
});
applySettings();
game.addEventListener("click", (event) => {
  if (!(event.target instanceof Element)) return;
  const button = event.target.closest<HTMLButtonElement>("button");
  if (busy && button?.closest("#species-choices")) return;
  const continuing = button?.dataset.continue;
  const choice = continuing ?? button?.dataset.start;
  if (choice) {
    if (canRunFlight()) unlockAudio();
    void (async () => {
      await selectChapter("goose");
      if (selectedSpecies === "goose")
        await choose(choice, Boolean(continuing));
    })();
  }
  switch (button?.dataset.action) {
    case "enter":
      if (!busy && !menuActions.hidden) showMenuScreen("species");
      break;
    case "title":
      if (!busy) {
        void selectChapter("goose");
        showMenuScreen("title");
      }
      break;
    case "whale":
    case "reindeer": {
      const species = button.dataset.action;
      if (canRunFlight()) unlockAudio(species);
      void (async () => {
        await selectChapter(species);
        if (selectedSpecies === species && !retryChapterLoad)
          await choose("journey");
      })();
      break;
    }
    case "practice":
      showPractice();
      break;
    case "settings":
      if (!busy) settingsDialog.showModal();
      break;
    case "soundtrack":
      soundtrackDialog.showModal();
      selectSoundtrack(settings.music);
      break;
    case "pause":
      pause();
      break;
    case "camera":
      if (runtime?.current.phase === "playing") {
        recenterCamera();
        game.focus({ preventScroll: true });
      }
      break;
    case "skip":
      finishLanding();
      break;
    case "tips":
      tips = false;
      game.focus({ preventScroll: true });
      break;
  }
});
soundtrackTrack.addEventListener("change", () => selectSoundtrack(true));
soundtrackPlayer.addEventListener("error", () => {
  if (soundtrackDialog.open) soundtrackStatus.hidden = false;
});
soundtrackDialog.addEventListener("close", () => {
  soundtrackPlayer.pause();
  soundtrackPlayer.removeAttribute("src");
  soundtrackPlayer.load();
});
settingsDialog.addEventListener("input", (event) => {
  const target = event.target;
  if (
    target instanceof HTMLInputElement &&
    target.type === "checkbox" &&
    target.name in settings
  ) {
    saveSettings({ ...settings, [target.name]: target.checked });
  } else if (
    target instanceof HTMLInputElement &&
    target.name === "sensitivity"
  ) {
    saveSettings({ ...settings, sensitivity: target.valueAsNumber });
  } else if (target instanceof HTMLSelectElement && target.name === "mapping") {
    saveSettings({ ...settings, mapping: target.value === "B" ? "B" : "A" });
  }
});
retryLoad.addEventListener(
  "click",
  () =>
    void (async () => {
      const species = retryChapterLoad;
      if (!species) await boot();
      else {
        await selectChapter(species);
        if (selectedSpecies === species && !retryChapterLoad)
          await choose("journey");
      }
    })(),
);
panel.addEventListener("cancel", (event) => {
  if (!hud.hidden) event.preventDefault();
});
settingsDialog.addEventListener("keydown", (event) => {
  if (event.code === "Escape") event.stopPropagation();
});
settingsDialog.addEventListener("click", (event) => {
  if (!(event.target instanceof HTMLButtonElement)) return;
  const id = event.target.dataset.settingsTarget;
  if (!id) return;
  const group = element(id);
  group.focus({ preventScroll: true });
  group.scrollIntoView({ block: "start" });
});
window.addEventListener("blur", pause);
window.addEventListener("pagehide", pause);
document.addEventListener("visibilitychange", () => {
  lastFrame = undefined;
  if (document.hidden) pause();
});
touchPortrait.addEventListener("change", () => {
  const phase = runtime?.current.phase;
  if (
    !hud.hidden &&
    touchPortrait.matches &&
    (phase === "playing" || (phase === "landing" && !landingPaused))
  )
    pause();
  else refreshPausePanel();
});
canvas.addEventListener("webglcontextlost", (event) => {
  event.preventDefault();
  contextLost = true;
  pause();
  if (!hud.hidden && runtime?.current.phase === "paused") showPaused();
  else if (!menu.hidden) {
    bootStatus.hidden = false;
    showBootMessage(() =>
      copy(
        "图形连接已中断，等待浏览器恢复。",
        "Graphics connection lost. Waiting for the browser to restore it.",
      ),
    );
    menuActions.hidden = true;
    speciesChoices.inert = true;
  }
});
canvas.addEventListener("webglcontextrestored", () => {
  contextLost = false;
  refreshPausePanel();
  if (!menu.hidden && goose) {
    bootStatus.hidden = true;
    menuActions.hidden = false;
    speciesChoices.inert = false;
    void refreshMenuSaves();
  }
});

void boot();
requestAnimationFrame(frame);
