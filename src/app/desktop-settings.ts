import { copy, isEnglish } from "../i18n/language";
import {
  canBindKey,
  DEFAULT_KEYS,
  desktopActions,
  flightKey,
  keyLabel,
  type DesktopAction,
  type KeyBindings,
} from "../input/keyboard";

export function setupDesktopSettings(
  dialog: HTMLDialogElement,
  bindings: () => KeyBindings,
  save: (bindings: KeyBindings) => void,
  abilityLabel: () => string,
): () => void {
  const grid = dialog.querySelector("#key-bindings");
  const hint = dialog.querySelector("#key-hint");
  const reset = dialog.querySelector("#key-defaults");
  if (!grid || !hint || !reset) throw new Error("Missing desktop controls");
  let pending: DesktopAction | undefined;
  const rows = new Map<
    DesktopAction,
    { button: HTMLButtonElement; title: HTMLSpanElement }
  >();
  function actionTitle(action: DesktopAction): string {
    switch (action) {
      case "up":
        return copy("向前", "Forward");
      case "down":
        return copy("向后", "Back");
      case "left":
        return copy("向左", "Left");
      case "right":
        return copy("向右", "Right");
      case "boost":
        return copy("加速", "Boost");
      case "slow":
        return copy("缓行", "Slow down");
      case "formation":
        return abilityLabel();
      case "recenter":
        return copy("镜头复位", "Reset camera");
    }
  }
  const refresh = (): void => {
    for (const [action, { button, title }] of rows) {
      const label = keyLabel(bindings()[action]);
      title.textContent = actionTitle(action);
      button.textContent =
        pending === action ? copy("按下新键", "Press a new key") : label;
      button.setAttribute(
        "aria-label",
        isEnglish()
          ? `${actionTitle(action)} key · ${label}`
          : `${actionTitle(action)}键 · ${label}`,
      );
    }
  };
  const stop = (message: string): void => {
    pending = undefined;
    hint.textContent = message;
    refresh();
  };
  for (const action of desktopActions) {
    const row = document.createElement("div");
    const label = document.createElement("span");
    const button = document.createElement("button");
    button.type = "button";
    button.addEventListener("click", () => {
      button.focus({ preventScroll: true });
      pending = action;
      hint.textContent = copy(
        "按字母、数字、Shift 或空格。Esc 取消。",
        "Press a letter, number, Shift, or Space. Esc cancels.",
      );
      refresh();
    });
    button.addEventListener("blur", () => {
      if (pending === action) stop("");
    });
    row.append(label, button);
    grid.append(row);
    rows.set(action, { button, title: label });
  }
  dialog.addEventListener("keydown", (event) => {
    if (!pending || event.code === "Tab" || event.metaKey || event.ctrlKey)
      return;
    event.preventDefault();
    event.stopPropagation();
    if (event.repeat) return;
    if (event.code === "Escape") {
      stop(copy("已取消改键。", "Key change canceled."));
      return;
    }
    const code = flightKey(event.code);
    if (!canBindKey(code)) {
      hint.textContent = copy(
        "请选择字母、数字、Shift 或空格。",
        "Choose a letter, number, Shift, or Space.",
      );
      return;
    }
    const action = pending;
    const keys = bindings();
    const conflict = desktopActions.find(
      (other) => other !== action && keys[other] === code,
    );
    if (conflict) {
      hint.textContent = isEnglish()
        ? `${keyLabel(code)} is already assigned to ${actionTitle(conflict)}.`
        : `${keyLabel(code)} 已用于${actionTitle(conflict)}。`;
      return;
    }
    stop(
      isEnglish()
        ? `${actionTitle(action)} is now bound to ${keyLabel(code)}.`
        : `${actionTitle(action)}键已设为 ${keyLabel(code)}。`,
    );
    save({ ...keys, [action]: code });
  });
  reset.addEventListener("click", () => {
    stop(copy("已恢复默认键位。", "Default keys restored."));
    save(DEFAULT_KEYS);
  });
  dialog.addEventListener("close", () => stop(""));
  refresh();
  return refresh;
}
