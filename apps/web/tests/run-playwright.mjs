import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = fileURLToPath(new URL("../", import.meta.url));
const repoRoot = fileURLToPath(new URL("../../../", import.meta.url));
const engineRoot = join(repoRoot, "engine");
const cli = join(webRoot, "node_modules", "@playwright", "test", "cli.js");
const args = process.argv.slice(2);
const command = args[0] ?? "test";
const dataRoot = join(webRoot, ".e2e-data");
let dataDir;
let engine;
let fixture;
let vite;

async function isReachable(url) {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(750) });
    await response.body?.cancel();
    return response.ok;
  } catch {
    return false;
  }
}

async function waitForUrl(url, label, child, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let reachableSince;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`${label} exited with code ${child.exitCode}`);
    }
    if (await isReachable(url)) {
      reachableSince ??= Date.now();
      if (Date.now() - reachableSince >= 1_000) return;
    } else {
      reachableSince = undefined;
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`${label} did not become ready: ${url}`);
}

function stopChild(child) {
  if (!child || child.exitCode !== null || !child.pid) return;
  child.kill("SIGTERM");
}

function stopWindowsListeners(ports) {
  if (process.platform !== "win32") return;
  const result = spawnSync("netstat", ["-ano"], { encoding: "utf8" });
  if (result.error || !result.stdout) return;
  for (const line of result.stdout.split(/\r?\n/)) {
    const match = line.match(/^\s*TCP\s+\S+:(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$/i);
    if (!match || !ports.includes(Number(match[1]))) continue;
    try {
      process.kill(Number(match[2]));
    } catch {
      // The direct child termination may already have closed the listener.
    }
  }
}

function cleanup() {
  stopChild(vite);
  stopChild(engine);
  stopChild(fixture);
  stopWindowsListeners([5173, 8090, 8877]);
  if (dataDir && dirname(dataDir) === dataRoot) {
    rmSync(dataDir, { recursive: true, force: true });
  }
}

async function startServices() {
  for (const url of [
    "http://127.0.0.1:8090/health",
    "http://127.0.0.1:8877/integration.html",
    "http://127.0.0.1:5173",
  ]) {
    if (await isReachable(url)) throw new Error(`E2E port is already in use: ${url}`);
  }

  mkdirSync(dataRoot, { recursive: true });
  dataDir = mkdtempSync(join(dataRoot, "run-"));
  const python = process.env.SIFTLANE_E2E_PYTHON ?? join(
    engineRoot,
    ".venv",
    process.platform === "win32" ? "Scripts" : "bin",
    process.platform === "win32" ? "python.exe" : "python",
  );
  if (!existsSync(python)) {
    throw new Error(`Engine virtualenv is missing: ${python}. Run the repository setup steps first.`);
  }

  engine = spawn(python, ["-m", "siftlane_engine.main"], {
    cwd: engineRoot,
    env: {
      ...process.env,
      SIFTLANE_ENGINE_PORT: "8090",
      SIFTLANE_ENGINE_DATA_DIR: dataDir,
      SIFTLANE_ENGINE_ALLOW_PRIVATE_NETWORKS: "true",
      SIFTLANE_ENGINE_REQUEST_MIN_DELAY_SECONDS: "0",
    },
    stdio: "inherit",
  });
  fixture = spawn(
    python,
    ["-m", "http.server", "8877", "--bind", "127.0.0.1", "--directory", join(engineRoot, "tests", "fixtures")],
    { cwd: engineRoot, stdio: "inherit" },
  );
  const viteNode = process.env.SIFTLANE_E2E_VITE_NODE ?? process.execPath;
  vite = spawn(viteNode, [join(webRoot, "node_modules", "vite", "bin", "vite.js"), "--strictPort"], {
    cwd: webRoot,
    env: { ...process.env, VITE_API_BASE_URL: "http://127.0.0.1:8090" },
    stdio: "inherit",
  });

  await Promise.all([
    waitForUrl("http://127.0.0.1:8090/health", "engine", engine, 120_000),
    waitForUrl("http://127.0.0.1:8877/integration.html", "fixture", fixture, 30_000),
    waitForUrl("http://127.0.0.1:5173", "Vite", vite, 60_000),
  ]);
}

async function main() {
  try {
    if (command === "test") await startServices();
    const result = spawnSync(process.execPath, [cli, ...(args.length ? args : ["test"])], {
      cwd: webRoot,
      env: {
        ...process.env,
        PLAYWRIGHT_BROWSERS_PATH: join(webRoot, ".playwright-browsers"),
      },
      stdio: "inherit",
    });
    if (result.error) throw result.error;
    return result.status ?? 1;
  } finally {
    cleanup();
  }
}

process.exitCode = await main();
