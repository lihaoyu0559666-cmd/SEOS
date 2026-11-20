import {build} from "esbuild";
import {readFile,writeFile} from "node:fs/promises";

const bundle = await build({entryPoints:["scene.js"],bundle:true,format:"iife",write:false,minify:true,
  treeShaking:true,legalComments:"inline",target:["chrome110","edge110"]});
const template = await readFile("prototype.html","utf8");
const source = bundle.outputFiles[0].text.replace(/<\/script/gi,"<\\/script");
const license = (await readFile("node_modules/three/LICENSE","utf8")).replaceAll("--","—");
await writeFile("index.html",template.replace("<!--LICENSE-->",()=>("<!--\n"+license+"\n-->"))
  .replace("__SCENE__",()=>source));
