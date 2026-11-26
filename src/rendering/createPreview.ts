import {
  AmbientLight,
  Color,
  DirectionalLight,
  GridHelper,
  Mesh,
  MeshLambertMaterial,
  OctahedronGeometry,
  OrthographicCamera,
  Scene,
  WebGLRenderer,
} from "three";
import { getPreviewFrame } from "./previewFrame";

export function createPreview(
  canvas: HTMLCanvasElement,
  context: WebGL2RenderingContext,
): () => void {
  const renderer = new WebGLRenderer({ canvas, context });
  const scene = new Scene();
  scene.background = new Color("#243334");

  const camera = new OrthographicCamera(-5, 5, 5, -5, 0.1, 60);
  camera.position.set(8, 9, 12);
  camera.lookAt(0, 0, 0);

  const marker = new Mesh(
    new OctahedronGeometry(1.15),
    new MeshLambertMaterial({ color: "#e3bb82" }),
  );
  marker.position.y = 1.2;
  const sun = new DirectionalLight(0xffedd7, 2);
  sun.position.set(-3, 8, 5);
  scene.add(
    marker,
    sun,
    new AmbientLight(0xffffff, 0.8),
    new GridHelper(14, 14, 0x849b8e, 0x49625d),
  );

  function render(): void {
    const { clientWidth, clientHeight } = canvas;
    if (clientWidth === 0 || clientHeight === 0 || context.isContextLost())
      return;

    const frame = getPreviewFrame(clientWidth / clientHeight, 10);
    camera.left = -frame.width / 2;
    camera.right = frame.width / 2;
    camera.top = frame.height / 2;
    camera.bottom = -frame.height / 2;
    camera.updateProjectionMatrix();

    renderer.setDrawingBufferSize(
      clientWidth,
      clientHeight,
      Math.min(window.devicePixelRatio, 2),
    );
    renderer.render(scene, camera);
  }

  render();
  new ResizeObserver(render).observe(canvas);
  return render;
}
