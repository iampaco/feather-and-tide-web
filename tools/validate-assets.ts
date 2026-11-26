import { deepStrictEqual } from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";

interface Entry {
  assetId: string;
  url: string;
  source: string;
  rights: string;
  size: number;
  sha256: string;
  sourceSha256: string;
}
interface ModelEntry extends Entry {
  clips: string[];
  clipsOnly?: boolean;
  textureSize?: number;
}
interface SceneryEntry extends Entry {
  clip?: string;
  pivotNode?: string;
}
interface MediaEntry extends Entry {
  type: "video/mp4" | "audio/mpeg";
  localSource?: boolean;
}
interface Gltf {
  animations?: {
    name?: string;
    channels: { target: { node: number; path: string } }[];
  }[];
  images?: { uri?: string; bufferView?: number }[];
  bufferViews?: { byteOffset?: number; byteLength: number }[];
  meshes?: unknown[];
  nodes?: { name?: string }[];
  skins?: { joints: number[] }[];
}

const root = new URL("../", import.meta.url);
const path = new URL("public/assets/", root);
const manifest = JSON.parse(
  await readFile(new URL("manifest.json", path), "utf8"),
) as {
  version: number;
  assets: ModelEntry[];
  images: Entry[];
  scenery: SceneryEntry[];
  media: MediaEntry[];
};
if (manifest.version !== 1 || manifest.assets.length === 0)
  throw new Error("Invalid asset manifest");
const ids = new Set<string>();
const names = new Set<string>();

function hash(bytes: Buffer): string {
  return createHash("sha256").update(bytes).digest("hex");
}
async function verifiedRuntime(asset: Entry): Promise<Buffer> {
  if (ids.has(asset.assetId) || !asset.rights)
    throw new Error(`Invalid asset entry ${asset.assetId}`);
  ids.add(asset.assetId);
  const bytes = await readFile(new URL(asset.url, path));
  if (bytes.length !== asset.size || hash(bytes) !== asset.sha256)
    throw new Error(`Runtime/hash mismatch for ${asset.assetId}`);
  return bytes;
}

async function verifiedBytes(
  asset: Entry,
): Promise<{ bytes: Buffer; source: Buffer }> {
  const bytes = await verifiedRuntime(asset);
  const source = await readFile(new URL(asset.source, root));
  if (hash(source) !== asset.sourceSha256)
    throw new Error(`Source/hash mismatch for ${asset.assetId}`);
  return { bytes, source };
}

function geometryAndTextureSize(
  original: Buffer,
  runtime: Buffer,
  size: number,
): void {
  function unpack(bytes: Buffer) {
    const documentEnd = 20 + bytes.readUInt32LE(12);
    const gltf = JSON.parse(bytes.toString("utf8", 20, documentEnd)) as Gltf;
    if (!gltf.images?.length || !gltf.bufferViews)
      throw new Error("Goose model is missing embedded textures");
    const images = new Set(gltf.images.map((image) => image.bufferView));
    const views = gltf.bufferViews.map(({ byteOffset = 0, byteLength }) =>
      bytes.subarray(
        documentEnd + 8 + byteOffset,
        documentEnd + 8 + byteOffset + byteLength,
      ),
    );
    // Only the images and their placement in the binary chunk may change.
    const normalized = {
      ...gltf,
      buffers: undefined,
      bufferViews: gltf.bufferViews.map((view, index) => ({
        ...view,
        byteOffset: undefined,
        byteLength: images.has(index) ? undefined : view.byteLength,
      })),
    };
    return { images, views, normalized };
  }
  const before = unpack(original);
  const after = unpack(runtime);
  deepStrictEqual(
    after.normalized,
    before.normalized,
    "Goose mesh, rig, materials and animation declarations changed",
  );
  for (const [index, view] of after.views.entries()) {
    if (!after.images.has(index)) {
      deepStrictEqual(
        view,
        before.views[index],
        "Non-image goose buffer changed",
      );
      continue;
    }
    if (
      view.toString("hex", 0, 8) !== "89504e470d0a1a0a" ||
      view.readUInt32BE(16) !== size ||
      view.readUInt32BE(20) !== size
    )
      throw new Error(
        `Invalid goose texture size: expected ${size} × ${size} PNG`,
      );
  }
}

for (const asset of manifest.assets) {
  const { bytes, source } = await verifiedBytes(asset);
  if (
    bytes.toString("ascii", 0, 4) !== "glTF" ||
    bytes.readUInt32LE(4) !== 2 ||
    bytes.readUInt32LE(8) !== bytes.length
  ) {
    throw new Error(`Invalid GLB ${asset.assetId}`);
  }
  const documentEnd = 20 + bytes.readUInt32LE(12);
  const gltf = JSON.parse(bytes.toString("utf8", 20, documentEnd)) as Gltf;
  if (asset.textureSize)
    geometryAndTextureSize(source, bytes, asset.textureSize);
  if (gltf.images?.some((image) => image.uri))
    throw new Error(`External texture in ${asset.assetId}`);
  if (asset.clipsOnly && (gltf.meshes?.length || gltf.images?.length))
    throw new Error(`Unexpected mesh or texture in ${asset.assetId}`);
  if (!asset.clipsOnly) {
    for (const index of gltf.skins?.[0]?.joints ?? []) {
      const name = gltf.nodes?.[index]?.name;
      if (name) names.add(name);
    }
    if (!names.size) throw new Error(`Missing rig in ${asset.assetId}`);
  }
  for (const clip of asset.clips) {
    const animation = gltf.animations?.find((item) => item.name === clip);
    if (
      !animation?.channels.length ||
      animation.channels.some(({ target }) => {
        const node = gltf.nodes?.[target.node]?.name;
        return (
          !node ||
          node === "Root" ||
          !names.has(node) ||
          target.path === "weights"
        );
      })
    )
      throw new Error(`Clip ${clip} has invalid bone bindings or root motion`);
  }
  console.log(
    `${asset.assetId} ${bytes.length} bytes · ${asset.clips.join(", ")}`,
  );
}
for (const asset of manifest.scenery) {
  const { bytes } = await verifiedBytes(asset);
  if (
    bytes.toString("ascii", 0, 4) !== "glTF" ||
    bytes.readUInt32LE(4) !== 2 ||
    bytes.readUInt32LE(8) !== bytes.length
  ) {
    throw new Error(`Invalid scenery GLB ${asset.assetId}`);
  }
  const gltf = JSON.parse(
    bytes.toString("utf8", 20, 20 + bytes.readUInt32LE(12)),
  ) as Gltf;
  if (!gltf.meshes?.length || gltf.images?.some((image) => image.uri))
    throw new Error(`Incomplete export ${asset.assetId}`);
  if (
    asset.clip &&
    !gltf.animations?.some((animation) => animation.name === asset.clip)
  )
    throw new Error(`Missing scenery clip ${asset.clip} in ${asset.assetId}`);
  if (
    asset.pivotNode &&
    !gltf.nodes?.some((node) => node.name === asset.pivotNode)
  )
    throw new Error(
      `Missing scenery pivot ${asset.pivotNode} in ${asset.assetId}`,
    );
  console.log(`${asset.assetId} ${bytes.length} bytes · scenery`);
}
for (const asset of manifest.images) {
  const { bytes } = await verifiedBytes(asset);
  const webp = asset.url.endsWith(".webp");
  const valid = webp
    ? bytes.toString("ascii", 0, 4) === "RIFF" &&
      bytes.toString("ascii", 8, 12) === "WEBP"
    : bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff;
  if (!valid) throw new Error(`Invalid image ${asset.assetId}`);
  console.log(
    `${asset.assetId} ${bytes.length} bytes · ${webp ? "WebP" : "JPEG"}`,
  );
}
for (const asset of manifest.media) {
  const bytes = asset.localSource
    ? (await verifiedBytes(asset)).bytes
    : await verifiedRuntime(asset);
  const video =
    asset.type === "video/mp4" &&
    asset.url.endsWith(".mp4") &&
    bytes.toString("ascii", 4, 8) === "ftyp";
  const audio =
    asset.type === "audio/mpeg" &&
    asset.url.endsWith(".mp3") &&
    (bytes.toString("ascii", 0, 3) === "ID3" ||
      (bytes[0] === 0xff && ((bytes[1] ?? 0) & 0xe0) === 0xe0));
  if (
    (!video && !audio) ||
    !asset.source ||
    !/^[0-9a-f]{64}$/.test(asset.sourceSha256)
  )
    throw new Error(`Invalid media entry ${asset.assetId}`);
  console.log(`${asset.assetId} ${bytes.length} bytes · ${asset.type}`);
}
