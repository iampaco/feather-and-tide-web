import type { WorldInput } from "../core/game";
import { clamp, type Vec2 } from "../core/math";
import {
  actionForKey,
  DEFAULT_KEYS,
  isDirection,
  type DesktopAction,
  type KeyBindings,
} from "./keyboard";

export interface Basis {
  readonly right: Vec2;
  readonly up: Vec2;
}
export interface InputSettings {
  readonly mirror: boolean;
  readonly large: boolean;
  readonly toggle: boolean;
  readonly mapping: "A" | "B";
  readonly sensitivity: number;
  readonly vertical: boolean;
  readonly wideMouseOrbit: boolean;
  readonly reduced: boolean;
  readonly low: boolean;
  readonly music: boolean;
  readonly bindings: KeyBindings;
}

export const DEFAULT_SETTINGS: InputSettings = {
  mirror: false,
  large: false,
  toggle: false,
  mapping: "A",
  sensitivity: 1,
  vertical: true,
  wideMouseOrbit: false,
  reduced: false,
  low: false,
  music: true,
  bindings: DEFAULT_KEYS,
};

type Role = "move" | "camera" | "ability";
interface Pointer {
  readonly role: Role;
  readonly owner: HTMLElement;
  readonly type: string;
  readonly mouseButton: number;
  x: number;
  y: number;
}

export class InputManager {
  private readonly pointers = new Map<number, Pointer>();
  private readonly pressed = new Map<string, DesktopAction>();
  private source: "touch" | "keyboard" | undefined;
  private stick: Vec2 = { x: 0, z: 0 };
  private touchBasis: Basis | undefined;
  private keyboardBasis: Basis | undefined;
  private toggled = false;

  constructor(
    private readonly surface: HTMLElement,
    private readonly knob: HTMLElement,
    private readonly settings: () => InputSettings,
    private readonly enabled: () => boolean,
    private readonly basis: () => Basis,
    private readonly orbit: (x: number, y: number, pointerType: string) => void,
    private readonly pause: () => void,
    private readonly recenter: () => void,
  ) {
    surface.addEventListener("pointerdown", this.down);
    surface.addEventListener("pointermove", this.move);
    surface.addEventListener("pointerup", this.up);
    surface.addEventListener("pointercancel", this.cancel);
    surface.addEventListener("lostpointercapture", this.cancel);
    surface.addEventListener("contextmenu", this.contextMenu);
    window.addEventListener("keydown", this.keyDown);
    window.addEventListener("keyup", this.keyUp);
  }

  get movementSource(): "touch" | "keyboard" | undefined {
    return this.source;
  }

  private hasRole(role: Role): boolean {
    return [...this.pointers.values()].some((pointer) => pointer.role === role);
  }

  private contextMenu = (event: MouseEvent): void => {
    if (
      this.enabled() &&
      event.target instanceof Element &&
      !event.target.closest("[data-ui], [data-ability]")
    )
      event.preventDefault();
  };

  private down = (event: PointerEvent): void => {
    const target = event.target;
    const mouse = event.pointerType === "mouse";
    if (
      !(target instanceof HTMLElement) ||
      !this.enabled() ||
      (event.button !== 0 && !(mouse && event.button === 2))
    )
      return;
    const ability = target.closest<HTMLElement>("[data-ability]");
    if (ability && event.button !== 0) return;
    if (!ability && target.closest("[data-ui]")) return;
    const bounds = this.surface.getBoundingClientRect();
    const relative = (event.clientX - bounds.left) / bounds.width;
    const leftFraction = this.settings().mirror ? 1 - relative : relative;
    const role = ability
      ? "ability"
      : !mouse && leftFraction < 0.42
        ? "move"
        : "camera";
    if (this.hasRole(role)) return;

    const owner = ability ?? this.surface;
    try {
      owner.setPointerCapture(event.pointerId);
    } catch {
      // Synthetic browser events still exercise routing without native capture.
      if (event.isTrusted) return;
    }
    event.preventDefault();
    this.pointers.set(event.pointerId, {
      role,
      owner,
      type: event.pointerType,
      mouseButton: mouse ? (event.button === 2 ? 2 : 1) : 0,
      x: event.clientX,
      y: event.clientY,
    });
    if (role === "move") {
      this.source = "touch";
      this.touchBasis = this.basis();
      this.knob.hidden = false;
      // CSS clamps the artwork to the safe area. The gesture still starts at the touch point.
      this.knob.style.setProperty(
        "--stick-x",
        `${event.clientX - bounds.left}px`,
      );
      this.knob.style.setProperty(
        "--stick-y",
        `${event.clientY - bounds.top}px`,
      );
    }
    if (mouse && role === "camera") this.surface.classList.add("orbiting");
    if (role === "ability" && this.settings().toggle)
      this.toggled = !this.toggled;
  };

  private move = (event: PointerEvent): void => {
    const pointer = this.pointers.get(event.pointerId);
    if (!pointer) return;
    if (pointer.mouseButton && !(event.buttons & pointer.mouseButton)) {
      this.up(event);
      return;
    }
    event.preventDefault();
    const x = event.clientX - pointer.x;
    const y = event.clientY - pointer.y;
    if (pointer.role === "camera") {
      pointer.x = event.clientX;
      pointer.y = event.clientY;
      this.orbit(x, y, pointer.type);
    }
    if (pointer.role === "move") {
      const radius = this.settings().large ? 64 : 54;
      const length = Math.hypot(x, y);
      const magnitude = clamp((length / radius - 0.1) / 0.9);
      this.stick = length
        ? { x: (x / length) * magnitude, z: (-y / length) * magnitude }
        : { x: 0, z: 0 };
      const visualLength = Math.max(1, length / radius);
      this.knob.style.setProperty("--dx", `${x / visualLength}px`);
      this.knob.style.setProperty("--dy", `${y / visualLength}px`);
    }
  };

  private up = (event: PointerEvent): void => {
    const pointer = this.pointers.get(event.pointerId);
    if (!pointer) return;
    this.pointers.delete(event.pointerId);
    if (pointer.role === "move") {
      this.clearStick();
      if (this.keyboardBasis) this.source = "keyboard";
    }
    if (pointer.role === "camera") this.surface.classList.remove("orbiting");
    if (pointer.owner.hasPointerCapture(event.pointerId))
      pointer.owner.releasePointerCapture(event.pointerId);
  };

  private cancel = (event: PointerEvent): void => {
    if (this.pointers.has(event.pointerId)) this.clear();
  };

  private keyDown = (event: KeyboardEvent): void => {
    if (event.code === "Escape" && !event.repeat) {
      this.pause();
      return;
    }
    if (!this.enabled() || event.metaKey || event.ctrlKey || event.isComposing)
      return;
    const action = actionForKey(this.settings().bindings, event.code);
    if (!action) return;
    if (event.target instanceof Element) {
      if (event.target.closest("input, select, textarea, [contenteditable]"))
        return;
      // Space still activates the focused toolbar button through the browser.
      if (
        event.code === "Space" &&
        event.target.closest("button:not([data-ability])")
      )
        return;
    }
    event.preventDefault();
    // A key held across a pause must be released before it can re-engage.
    if (event.repeat) return;
    if (action === "recenter") {
      this.recenter();
      return;
    }
    if (isDirection(action)) {
      this.keyboardBasis ??= this.basis();
      this.source = "keyboard";
    }
    if (action === "formation" && this.settings().toggle)
      this.toggled = !this.toggled;
    this.pressed.set(event.code, action);
  };

  private keyUp = (event: KeyboardEvent): void => {
    const action = this.pressed.get(event.code);
    if (!this.pressed.delete(event.code) || !action || !isDirection(action))
      return;
    for (const held of this.pressed.values()) if (isDirection(held)) return;
    this.keyboardBasis = undefined;
    if (this.hasRole("move")) this.source = "touch";
  };

  private held(action: DesktopAction): boolean {
    for (const pressed of this.pressed.values())
      if (pressed === action) return true;
    return false;
  }

  sample(): WorldInput {
    const keyboard = this.source !== "touch";
    const key = (role: DesktopAction): number => Number(this.held(role));
    const x = keyboard ? key("right") - key("left") : this.stick.x;
    const y = keyboard ? key("up") - key("down") : this.stick.z;
    const { toggle, mapping, wideMouseOrbit } = this.settings();
    const locked = keyboard ? this.keyboardBasis : this.touchBasis;
    const basis = (mapping === "B" && locked) || this.basis();
    const { right } = basis;
    // The right axis is already a unit vector on XZ, even at shallow pitch.
    const up =
      keyboard && wideMouseOrbit ? { x: right.z, z: -right.x } : basis.up;
    const wx = right.x * x + up.x * y;
    const wz = right.z * x + up.z * y;
    const length = Math.hypot(wx, wz);
    const speed = keyboard
      ? this.held("slow")
        ? 0.12
        : this.held("boost")
          ? 1
          : 0.84
      : Math.hypot(x, y);
    return {
      move: length
        ? { x: (wx / length) * speed, z: (wz / length) * speed }
        : { x: 0, z: 0 },
      ability: toggle
        ? this.toggled
        : this.hasRole("ability") || this.held("formation"),
    };
  }

  private clearStick(): void {
    this.stick = { x: 0, z: 0 };
    this.touchBasis = undefined;
    this.knob.hidden = true;
    this.knob.style.removeProperty("--dx");
    this.knob.style.removeProperty("--dy");
  }

  clearAbilityToggle(): void {
    this.toggled = false;
  }

  clear(): void {
    const captured = [...this.pointers.entries()];
    this.pointers.clear();
    for (const [id, pointer] of captured) {
      if (pointer.owner.hasPointerCapture(id))
        pointer.owner.releasePointerCapture(id);
    }
    this.pressed.clear();
    this.keyboardBasis = undefined;
    this.surface.classList.remove("orbiting");
    this.toggled = false;
    this.clearStick();
  }
}
