export type GooseMarkerKind =
  "landmark" | "route" | "supply" | "rescue" | "hazard" | "gathering" | "pin";

interface Point {
  readonly x: number;
  readonly y: number;
}

interface Size {
  readonly width: number;
  readonly height: number;
}

interface Box extends Point, Size {}

interface Projection extends Point {
  readonly edge: boolean;
  readonly angle: number;
}

interface MarkerRequest {
  readonly node: HTMLElement;
  readonly point: Projection;
  readonly kind: GooseMarkerKind;
  readonly primary: boolean;
}

interface Marker extends Projection, Size {
  readonly kind: GooseMarkerKind;
  readonly primary?: boolean;
}

interface Placement extends Point {
  readonly mode: "text" | "arrow";
  readonly angle: number;
}

const padding = 6;
const arrowSize = 24;

const priorities: Record<GooseMarkerKind, number> = {
  hazard: 6,
  rescue: 5,
  gathering: 4,
  route: 2,
  pin: 2,
  supply: 1,
  landmark: 0,
};

function priority(marker: Marker): number {
  if (marker.primary && marker.kind === "supply") return 3;
  if (marker.primary && marker.kind === "route") return 2.5;
  return priorities[marker.kind];
}

function intersects(a: Box, b: Box): boolean {
  return (
    a.x < b.x + b.width + padding &&
    b.x < a.x + a.width + padding &&
    a.y < b.y + b.height + padding &&
    b.y < a.y + a.height + padding
  );
}

function candidate(
  target: Point,
  size: Size,
  area: Size,
  occupied: readonly Box[],
  maximumShift: number,
): Box | undefined {
  const maxX = area.width - size.width;
  const maxY = area.height - size.height;
  if (maxX < 0 || maxY < 0 || !size.width || !size.height) return;
  const x = Math.max(0, Math.min(target.x - size.width / 2, maxX));
  const y = Math.max(0, Math.min(target.y - size.height, maxY));
  const anchor = { ...size, x, y };
  if (!occupied.some((box) => intersects(anchor, box))) return anchor;
  if (!maximumShift) return;

  // A clear position needs to be either on the preferred axis or alongside an occupied box.
  const xs = [x, 0, maxX];
  const ys = [y, 0, maxY];
  for (const box of occupied) {
    xs.push(box.x - size.width - padding, box.x + box.width + padding);
    ys.push(box.y - size.height - padding, box.y + box.height + padding);
  }
  let best: Box | undefined;
  let nearest = maximumShift * maximumShift;
  for (const nextX of xs) {
    if (nextX < 0 || nextX > maxX) continue;
    for (const nextY of ys) {
      if (nextY < 0 || nextY > maxY) continue;
      const distance = (nextX - x) ** 2 + (nextY - y) ** 2;
      if (distance > nearest || (best && distance === nearest)) continue;
      const box = { ...size, x: nextX, y: nextY };
      if (occupied.some((other) => intersects(box, other))) continue;
      best = box;
      nearest = distance;
    }
  }
  return best;
}

export function placeGooseMarkers(
  markers: readonly Marker[],
  area: Size,
  obstacles: readonly Box[],
): readonly (Placement | undefined)[] {
  const occupied = [...obstacles];
  const output: (Placement | undefined)[] = Array.from(
    markers,
    () => undefined,
  );
  const order = markers.map((marker, index) => ({ marker, index }));
  order.sort((a, b) => priority(b.marker) - priority(a.marker));
  const rescuing = markers.some(({ kind }) => kind === "rescue");
  for (const { marker, index } of order) {
    const important = priority(marker) >= priorities.route;
    const maximumShift =
      marker.primary && marker.kind === "route"
        ? Infinity
        : important
          ? marker.edge
            ? 56
            : 24
          : marker.kind === "supply" && !rescuing
            ? 56
            : 0;
    const box = candidate(
      marker,
      { width: marker.width, height: marker.height },
      area,
      occupied,
      maximumShift,
    );
    if (box) {
      occupied.push(box);
      output[index] = { x: box.x, y: box.y, mode: "text", angle: marker.angle };
      continue;
    }
    if (!important) continue;
    const arrow = candidate(
      marker,
      { width: arrowSize, height: arrowSize },
      area,
      occupied,
      Infinity,
    );
    if (!arrow) continue;
    const centerX = arrow.x + arrow.width / 2;
    const centerY = arrow.y + arrow.height / 2;
    const angle = marker.edge
      ? marker.angle
      : (Math.atan2(marker.y - centerY, marker.x - centerX) * 180) / Math.PI;
    occupied.push(arrow);
    output[index] = { x: arrow.x, y: arrow.y, mode: "arrow", angle };
  }
  return output;
}

interface Measurement extends Size {
  readonly text: string | null;
  readonly kind: GooseMarkerKind;
  readonly edge: boolean;
}

function markerBox(rect: DOMRect, layer: DOMRect): Box {
  return {
    x: rect.left - layer.left,
    y: rect.top - layer.top,
    width: rect.width,
    height: rect.height,
  };
}

export class GooseMarkerLayout {
  private queue: MarkerRequest[] = [];
  private measurements = new WeakMap<HTMLElement, Measurement>();

  constructor(
    private readonly layer: HTMLElement,
    private readonly controls: readonly HTMLElement[],
  ) {
    new ResizeObserver(() => {
      this.measurements = new WeakMap();
    }).observe(layer);
  }

  add(
    node: HTMLElement,
    point: Projection,
    kind: GooseMarkerKind,
    primary = false,
  ): void {
    this.queue.push({ node, point, kind, primary });
  }

  render(leader?: Projection, opening?: Projection): void {
    const queue = this.queue;
    this.queue = [];
    const hud = this.layer.parentElement;
    if (!hud || !queue.length) return;

    const dirty = queue.filter(({ node, kind, point }) => {
      const old = this.measurements.get(node);
      return (
        !old ||
        old.text !== node.textContent ||
        old.kind !== kind ||
        old.edge !== point.edge
      );
    });
    for (const { node } of dirty) {
      if (node.dataset.markerPlacement === "arrow")
        delete node.dataset.markerPlacement;
    }
    // Batch reads before positioning to avoid reflows between moving markers.
    const layer = this.layer.getBoundingClientRect();
    const viewport = hud.getBoundingClientRect();
    const blocked = this.controls
      .filter((control) => !control.hidden)
      .map((control) => control.getBoundingClientRect())
      .filter((rect) => rect.width && rect.height)
      .map((rect) => markerBox(rect, layer));
    const screenPoint = (point: Point): Point => ({
      x: viewport.left + (point.x / 100) * viewport.width - layer.left,
      y: viewport.top + (point.y / 100) * viewport.height - layer.top,
    });
    if (leader && !leader.edge) {
      const { x, y } = screenPoint(leader);
      blocked.push({ x: x - 13, y: y - 11, width: 26, height: 22 });
    }
    if (opening) {
      const { x, y } = screenPoint(opening);
      const width = Math.min(110, layer.width * 0.17);
      blocked.push({ x: x - width / 2, y: y - 30, width, height: 60 });
    }

    for (const { node, kind, point } of dirty) {
      this.measurements.set(node, {
        width: node.offsetWidth,
        height: node.offsetHeight,
        text: node.textContent,
        kind,
        edge: point.edge,
      });
    }
    const markers = queue.map(({ node, point, kind, primary }): Marker => {
      const size = this.measurements.get(node);
      return {
        ...point,
        ...screenPoint(point),
        width: size?.width ?? 0,
        height: size?.height ?? 0,
        kind,
        primary,
      };
    });
    const positions = placeGooseMarkers(markers, layer, blocked);
    for (const [index, { node }] of queue.entries()) {
      const position = positions[index];
      const mode = position?.mode ?? "suppressed";
      if (node.dataset.markerPlacement !== mode)
        node.dataset.markerPlacement = mode;
      if (position) {
        node.style.setProperty("--placed-x", `${position.x}px`);
        node.style.setProperty("--placed-y", `${position.y}px`);
        node.style.setProperty("--arrow", `${position.angle}deg`);
      }
    }
  }
}
