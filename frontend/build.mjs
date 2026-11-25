import { mkdir, readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const sourceDirectory = path.dirname(fileURLToPath(import.meta.url));
const outputDirectory = path.join(sourceDirectory, "dist");
const configuredBase = (process.env.PUBLIC_API_BASE || "").trim();
let apiBase = "";
if (configuredBase) {
  const url = new URL(configuredBase);
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  if (
    !(url.protocol === "https:" || (url.protocol === "http:" && local)) ||
    url.username || url.password || url.search || url.hash || url.pathname !== "/"
  ) {
    throw new Error("PUBLIC_API_BASE must be an HTTPS backend origin, without a path or credentials.");
  }
  apiBase = url.origin;
}

await mkdir(outputDirectory, { recursive: true });
await writeFile(path.join(outputDirectory, "index.html"), await readFile(path.join(sourceDirectory, "index.html")));
await writeFile(path.join(outputDirectory, "config.js"),
  `window.NEWSAGENT_CONFIG = ${JSON.stringify({ apiBase })};\n`);
console.log("Static frontend built in dist/; API origin:", apiBase || "same origin");
