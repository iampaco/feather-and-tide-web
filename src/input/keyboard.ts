import { copy } from "../i18n/language";
export const desktopActions = [
  "up",
  "down",
  "left",
  "right",
  "boost",
  "slow",
  "formation",
  "recenter",
] as const;

export type DesktopAction = (typeof desktopActions)[number];
export type KeyBindings = Readonly<Record<DesktopAction, string>>;

export const DEFAULT_KEYS: KeyBindings = {
  up: "KeyW",
  down: "KeyS",
  left: "KeyA",
  right: "KeyD",
  boost: "Shift",
  slow: "KeyC",
  formation: "Space",
  recenter: "KeyR",
};

const fixedKeys = new Map<string, DesktopAction>([
  ["ArrowUp", "up"],
  ["ArrowDown", "down"],
  ["ArrowLeft", "left"],
  ["ArrowRight", "right"],
  ["AltLeft", "slow"],
]);

export function isDirection(action: DesktopAction): boolean {
  return (
    action === "up" ||
    action === "down" ||
    action === "left" ||
    action === "right"
  );
}

export function flightKey(code: string): string {
  return code === "ShiftLeft" || code === "ShiftRight" ? "Shift" : code;
}

export function canBindKey(code: unknown): code is string {
  return (
    typeof code === "string" && /^(Key[A-Z]|Digit[0-9]|Space|Shift)$/.test(code)
  );
}

export function actionForKey(
  bindings: KeyBindings,
  code: string,
): DesktopAction | undefined {
  const key = flightKey(code);
  return (
    fixedKeys.get(key) ??
    desktopActions.find((action) => bindings[action] === key)
  );
}

export function readBindings(value: unknown): KeyBindings {
  if (!value || typeof value !== "object") return DEFAULT_KEYS;
  const source = value as Partial<Record<DesktopAction, unknown>>;
  const bindings = { ...DEFAULT_KEYS };
  for (const action of desktopActions) {
    const key = source[action];
    if (canBindKey(key)) bindings[action] = key;
  }
  return new Set(Object.values(bindings)).size === desktopActions.length
    ? bindings
    : DEFAULT_KEYS;
}

export function keyLabel(code: string): string {
  if (code === "Space") return copy("空格", "Space");
  return code.replace(/^(Key|Digit)/, "");
}

export function movementLabel(bindings: KeyBindings): string {
  const labels = [
    bindings.up,
    bindings.left,
    bindings.down,
    bindings.right,
  ].map(keyLabel);
  return labels.join(labels.every((label) => label.length === 1) ? "" : " / ");
}
