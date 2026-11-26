export interface PreviewFrame {
  width: number;
  height: number;
}

export function getPreviewFrame(
  aspect: number,
  minimumSpan: number,
): PreviewFrame {
  // Fit the scene on the shorter axis so resizing never crops the center marker.
  return {
    width: minimumSpan * Math.max(aspect, 1),
    height: minimumSpan * Math.max(1 / aspect, 1),
  };
}
