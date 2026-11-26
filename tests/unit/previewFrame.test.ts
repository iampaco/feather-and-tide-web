import { describe, expect, it } from "vitest";
import { getPreviewFrame } from "../../src/rendering/previewFrame";

describe("getPreviewFrame", () => {
  it.each([
    [2, 20, 10],
    [1, 10, 10],
    [0.5, 10, 20],
  ])("preserves scale and aspect ratio at %s", (aspect, width, height) => {
    expect(getPreviewFrame(aspect, 10)).toEqual({ width, height });
  });
});
