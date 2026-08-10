import {createReadStream, existsSync, readFileSync, statSync, writeFileSync} from "node:fs";
import {mkdir} from "node:fs/promises";
import {createServer} from "node:http";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {bundle} from "@remotion/bundler";
import {renderMedia, selectComposition} from "@remotion/renderer";

const here = path.dirname(fileURLToPath(import.meta.url));
process.chdir(here);
const manifestPath = process.argv[2];
if (!manifestPath) throw new Error("Usage: node render-longform.mjs <manifest.json>");

const statusPath = `${path.resolve(manifestPath)}.status.json`;
const writeStatus = (stage, detail = {}) => writeFileSync(
  statusPath,
  JSON.stringify({stage, updatedAt: new Date().toISOString(), ...detail}, null, 2),
  "utf8",
);
const manifest = JSON.parse(readFileSync(path.resolve(manifestPath), "utf8"));
if (manifest.pipeline !== "shared-all-channels-remotion-longform-v1") {
  throw new Error(`Invalid long-form pipeline: ${manifest.pipeline}`);
}
if (!Array.isArray(manifest.renders) || manifest.renders.length === 0) {
  throw new Error("Long-form manifest must contain at least one render");
}

const assets = new Map();
manifest.renders.forEach((render, renderIndex) => {
  if (render.props?.pipelineId !== manifest.pipeline) {
    throw new Error(`Render ${renderIndex} does not use the shared long-form pipeline`);
  }
  if (!Array.isArray(render.assets) || render.assets.length === 0) {
    throw new Error(`Render ${renderIndex} has no clips`);
  }
  render.assets.forEach((assetPath, clipIndex) => {
    const resolved = path.resolve(assetPath);
    if (!existsSync(resolved)) throw new Error(`Missing long-form clip: ${resolved}`);
    assets.set(`/asset/${renderIndex}/clip/${clipIndex}`, resolved);
  });
});

const server = createServer((req, res) => {
  const pathname = new URL(req.url ?? "/", "http://127.0.0.1").pathname;
  const filePath = assets.get(pathname);
  if (!filePath) {
    res.writeHead(404);
    res.end("Not found");
    return;
  }
  const size = statSync(filePath).size;
  const range = req.headers.range;
  const headers = {"Accept-Ranges": "bytes", "Content-Type": "video/mp4"};
  if (range) {
    const match = /^bytes=(\d*)-(\d*)$/.exec(range);
    if (!match) {
      res.writeHead(416, {"Content-Range": `bytes */${size}`});
      res.end();
      return;
    }
    const start = match[1] ? Number(match[1]) : 0;
    const end = match[2] ? Math.min(Number(match[2]), size - 1) : size - 1;
    if (start > end || start >= size) {
      res.writeHead(416, {"Content-Range": `bytes */${size}`});
      res.end();
      return;
    }
    res.writeHead(206, {...headers, "Content-Range": `bytes ${start}-${end}/${size}`, "Content-Length": end - start + 1});
    if (req.method === "HEAD") res.end();
    else createReadStream(filePath, {start, end}).pipe(res);
    return;
  }
  res.writeHead(200, {...headers, "Content-Length": size});
  if (req.method === "HEAD") res.end();
  else createReadStream(filePath).pipe(res);
});

await new Promise((resolve, reject) => {
  server.once("error", reject);
  server.listen(0, "127.0.0.1", resolve);
});
writeStatus("asset-server-started");

try {
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("Could not resolve asset server");
  const assetBase = `http://127.0.0.1:${address.port}`;
  writeStatus("bundle-started");
  const serveUrl = await bundle({entryPoint: path.join(here, "src", "index.ts")});
  writeStatus("bundle-completed");

  for (let index = 0; index < manifest.renders.length; index += 1) {
    const item = manifest.renders[index];
    const inputProps = {
      ...item.props,
      clips: item.props.clips.map((clip, clipIndex) => ({
        ...clip,
        url: `${assetBase}/asset/${index}/clip/${clipIndex}`,
      })),
    };
    const shared = {
      serveUrl,
      inputProps,
      browserExecutable: manifest.browserExecutable || undefined,
      timeoutInMilliseconds: 120000,
    };
    writeStatus("composition-selecting", {index});
    const composition = await selectComposition({...shared, id: "LongTubeLongform"});
    await mkdir(path.dirname(path.resolve(item.outputPath)), {recursive: true});
    writeStatus("render-started", {index});
    await renderMedia({
      ...shared,
      composition,
      outputLocation: path.resolve(item.outputPath),
      codec: "h264",
      audioCodec: "aac",
      audioBitrate: "192k",
      crf: 16,
      x264Preset: "medium",
      pixelFormat: "yuv420p",
      colorSpace: "bt709",
      overwrite: true,
      concurrency: "50%",
      logLevel: "info",
    });
    writeStatus("render-completed", {index});
  }
  writeStatus("completed");
} finally {
  await new Promise((resolve) => server.close(resolve));
}
