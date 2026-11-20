import {
  AmbientLight, BoxGeometry, DirectionalLight, Group, Line, LineBasicMaterial, BufferGeometry,
  Mesh, MeshLambertMaterial, OrthographicCamera, Scene, Vector3, WebGLRenderer
} from "three";

const host = document.querySelector("#stage");
const status = document.querySelector("#state");
const controls = document.querySelector("#controls");
const fallback = document.querySelector("#fallback");
const state = {mode:"OFF", frames:0, draws:0, geometries:0, triangles:0, textures:0, initMs:null};
window.sceneEvidence = state;
let disposeScene;

function setMode(mode,message) {
  state.mode=mode;
  status.textContent=message;
  fallback.toggleAttribute("hidden",mode === "READY");
  controls.hidden=mode !== "READY";
}

function stop(mode = "OFF", message = "二维示意已显示") {
  if (disposeScene) disposeScene();
  disposeScene = null;
  host.replaceChildren();
  setMode(mode,message);
}

function start() {
  if (disposeScene) return;
  const startTime = performance.now();
  let renderer;
  try { renderer = new WebGLRenderer({antialias:true,alpha:false,powerPreference:"low-power"}); }
  catch (_) { stop("FALLBACK","WebGL 不可用，继续显示二维剖面。"); return; }

  const scene = new Scene();
  renderer.setClearColor(0xeef3f8);
  renderer.setPixelRatio(Math.min(devicePixelRatio,1.25));
  const camera = new OrthographicCamera(-7,7,4,-4,.1,80);
  const terrain = new Group();
  scene.add(terrain,new AmbientLight(0xffffff,2));
  const daylight = new DirectionalLight(0xffffff,2);
  daylight.position.set(3,8,4);
  scene.add(daylight);
  const materials = [0xd4b799,0xa47958,0x16a085,0xabcfc3,0x1f4e79]
    .map(color=> new MeshLambertMaterial({color}));
  const geometries=[];
  function block(w,h,d,x,y,z,material) {
    const geometry=new BoxGeometry(w,h,d);
    geometries.push(geometry);
    const mesh = new Mesh(geometry,materials[material]);
    mesh.position.set(x,y,z);
    terrain.add(mesh);
  }
  block(12,.45,7,0,-.3,0,0);
  block(12,.18,7,0,-.62,0,1);
  for (const [w,h,d,x,y,z,m] of [
      [4,.6,3,-3.2,.15,.6,1],[4,.5,1,-3.2,.62,1.6,0],
      [4,.5,1,-3.2,.62,-.4,0],[4,.22,3,3,.05,.6,3],[3.4,.35,2.4,3,.33,.6,2],
      [2.7,.38,1.8,3,.68,.6,3],[2,.35,1.2,3,1.02,.6,2],[.6,.24,.55,.5,.09,-2,4]
    ]) block(w,h,d,x,y,z,m);
  const lineGeometry = new BufferGeometry().setFromPoints([
    new Vector3(-3,0,-1.25),new Vector3(-3,0,-2.2),new Vector3(3,0,-2.2),new Vector3(3,0,-1.25)
  ]);
  const lineMaterial = new LineBasicMaterial({color:0x1f4e79});
  scene.add(new Line(lineGeometry,lineMaterial));

  let direction = .65, elevation = 7.5, zoom = 1;
  function draw() {
    if (document.hidden) return;
    const width = Math.max(host.clientWidth,200);
    const height = Math.min(320,Math.round(width*.67));
    renderer.setSize(width,height,false);
    renderer.domElement.style.width = width+"px";
    renderer.domElement.style.height = height+"px";
    const aspect=width/height;
    camera.left=-6.8*aspect; camera.right=6.8*aspect;
    camera.top=6.8; camera.bottom=-6.8; camera.zoom=zoom;
    camera.updateProjectionMatrix();
    camera.position.set(13*Math.sin(direction),elevation,13*Math.cos(direction));
    camera.lookAt(0,0,0);
    renderer.render(scene,camera);
    state.frames++;
    state.draws=renderer.info.render.calls;
    state.triangles=renderer.info.render.triangles;
    state.geometries=renderer.info.memory.geometries;
    state.textures=renderer.info.memory.textures;
  }
  function navigate(event) {
    const name = event.target.dataset.angle;
    if (name==="rotate") direction += .65;
    else if (name==="top") {direction=0;elevation=18;}
    else if (name==="zoom") zoom = zoom===1?1.3:1;
    else return;
    draw();
  }
  const canvas = renderer.domElement;
  canvas.setAttribute("role","img");
  canvas.setAttribute("aria-label","示意格块从左侧挖方衔接至右侧分层填方");
  const lost = event => {
    event.preventDefault();
    stop("FALLBACK","三维上下文已丢失，继续显示二维剖面。");
  };
  disposeScene = () => {
    controls.removeEventListener("click",navigate);
    window.removeEventListener("resize",draw);
    document.removeEventListener("visibilitychange",draw);
    canvas.removeEventListener("webglcontextlost",lost);
    for (const geometry of geometries) geometry.dispose();
    for (const material of materials) material.dispose();
    lineGeometry.dispose(); lineMaterial.dispose();
    renderer.dispose(); renderer.forceContextLoss();
    state.disposed = true;
  };
  controls.addEventListener("click",navigate);
  window.addEventListener("resize",draw);
  document.addEventListener("visibilitychange",draw);
  canvas.addEventListener("webglcontextlost",lost);
  host.append(canvas);
  try {
    draw();
    state.disposed = false;
    state.initMs = performance.now()-startTime;
    setMode("READY","三维示意已启用。按需切换观察角度。");
  } catch (_) { stop("FALLBACK","三维初始化失败，继续显示二维剖面。"); }
}
document.querySelector("#launch").addEventListener("click",start);
document.querySelector("#close").addEventListener("click",()=>stop());
