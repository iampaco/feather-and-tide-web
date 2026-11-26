import { copy } from "../i18n/language";
import type { Vec2 } from "../core/math";
import type { Basis } from "../input/input";
import { GOOSE } from "../simulation/goose";

export function gooseStamina(
  energy: number,
  recovering: boolean,
): {
  level: "recovering" | "critical" | "low" | "normal";
  text: string;
} {
  if (recovering)
    return { level: "recovering", text: copy("恢复中", "Recovering") };
  if (energy <= GOOSE.boostCutoff)
    return { level: "critical", text: copy("危急", "Critical") };
  if (energy <= GOOSE.lowEnergy)
    return { level: "low", text: copy("偏低", "Low") };
  return { level: "normal", text: "" };
}

export function screenDirection(from: Vec2, to: Vec2, basis: Basis): string {
  const x = to.x - from.x;
  const z = to.z - from.z;
  const side = x * basis.right.x + z * basis.right.z;
  const forward = x * basis.up.x + z * basis.up.z;
  // Four sectors keep the announcement stable as the target moves.
  if (Math.hypot(side, forward) < 2)
    return copy("在画面中央附近", "near the center of the screen");
  if (Math.abs(side) > Math.abs(forward)) {
    return side > 0
      ? copy("在画面右侧", "on the right of the screen")
      : copy("在画面左侧", "on the left of the screen");
  }
  return forward > 0
    ? copy("在画面上方", "toward the top of the screen")
    : copy("在画面下方", "toward the bottom of the screen");
}
