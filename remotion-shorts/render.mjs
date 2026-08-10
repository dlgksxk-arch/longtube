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
if (!manifestPath) {
  throw new Error("Usage: node render.mjs <manifest.json>");
}
const statusPath = `${path.resolve(manifestPath)}.status.json`;
const writeStatus = (stage, detail = {}) => {
  writeFileSync(
    statusPath,
    JSON.stringify({stage, updatedAt: new Date().toISOString(), ...detail}, null, 2),
    "utf8",
  );
};

const manifest = JSON.parse(readFileSync(path.resolve(manifestPath), "utf8"));
if (!Array.isArray(manifest.renders) || manifest.renders.length === 0) {
  throw new Error("Remotion manifest must contain at least one render");
}

const contentType = (filePath) => {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".mp4") return "video/mp4";
  if (ext === ".m4a") return "audio/mp4";
  if (ext === ".mp3") return "audio/mpeg";
  if (ext === ".wav") return "audio/wav";
  if (ext === ".png") return "image/png";
  if (ext === ".jpg" || ext === ".jpeg") return "image/jpeg";
  return "application/octet-stream";
};

const assets = new Map();
manifest.renders.forEach((render, index) => {
  for (const kind of ["video", "audio", "avatar"]) {
    const assetPath = render.assets?.[kind];
    if (!assetPath) continue;
    const resolved = path.resolve(assetPath);
    if (!existsSync(resolved)) {
      throw new Error(`Missing Remotion ${kind} asset: ${resolved}`);
    }
    assets.set(`/asset/${index}/${kind}`, resolved);
  }
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
  const headers = {
    "Accept-Ranges": "bytes",
    "Content-Type": contentType(filePath),
  };

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
    res.writeHead(206, {
      ...headers,
      "Content-Range": `bytes ${start}-${end}/${size}`,
      "Content-Length": end - start + 1,
    });
    if (req.method === "HEAD") {
      res.end();
      return;
    }
    createReadStream(filePath, {start, end}).pipe(res);
    return;
  }

  res.writeHead(200, {...headers, "Content-Length": size});
  if (req.method === "HEAD") {
    res.end();
    return;
  }
  createReadStream(filePath).pipe(res);
});

await new Promise((resolve, reject) => {
  server.once("error", reject);
  server.listen(0, "127.0.0.1", resolve);
});
writeStatus("asset-server-started");

try {
  const address = server.address();
  if (!address || typeof address === "string") {
    throw new Error("Could not resolve Remotion asset server address");
  }
  const assetBase = `http://127.0.0.1:${address.port}`;
  writeStatus("bundle-started");
  const serveUrl = await bundle({
    entryPoint: path.join(here, "src", "index.ts"),
  });
  writeStatus("bundle-completed");

  for (let index = 0; index < manifest.renders.length; index += 1) {
    const item = manifest.renders[index];
    const inputProps = {
      ...item.props,
      videoUrl: `${assetBase}/asset/${index}/video`,
      audioUrl: `${assetBase}/asset/${index}/audio`,
      avatarUrl: item.assets?.avatar ? `${assetBase}/asset/${index}/avatar` : null,
    };
    const shared = {
      serveUrl,
      inputProps,
      browserExecutable: manifest.browserExecutable || undefined,
      timeoutInMilliseconds: 120000,
    };
    writeStatus("composition-selecting", {index});
    const composition = await selectComposition({
      ...shared,
      id: "LongTubeShorts",
    });
    writeStatus("render-started", {index});
    await mkdir(path.dirname(path.resolve(item.outputPath)), {recursive: true});
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
