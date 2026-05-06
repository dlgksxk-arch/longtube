import { execFile } from "node:child_process";
import net from "node:net";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const ROOT_DIR = path.resolve(process.cwd(), "..");
const BACKEND_DIR = path.join(ROOT_DIR, "backend");
const COMFY_SCRIPT = path.join(ROOT_DIR, "start-comfyui-lan.bat");

type ServiceName = "backend" | "comfyui" | "all";
type ServiceAction = "start" | "restart";

export const dynamic = "force-dynamic";

function isServiceName(value: string): value is ServiceName {
  return value === "backend" || value === "comfyui" || value === "all";
}

function isServiceAction(value: string): value is ServiceAction {
  return value === "start" || value === "restart";
}

function canConnect(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host: "127.0.0.1", port });
    const done = (ok: boolean) => {
      socket.removeAllListeners();
      socket.destroy();
      resolve(ok);
    };
    socket.setTimeout(900);
    socket.once("connect", () => done(true));
    socket.once("timeout", () => done(false));
    socket.once("error", () => done(false));
  });
}

async function runPowerShell(script: string) {
  return execFileAsync(
    "powershell.exe",
    ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
    {
      cwd: ROOT_DIR,
      windowsHide: true,
      timeout: 15_000,
      maxBuffer: 1024 * 1024,
    },
  );
}

async function stopBackend() {
  await runPowerShell(`
    $ErrorActionPreference = 'SilentlyContinue'
    $pids = @()
    $pids += Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object -ExpandProperty OwningProcess -Unique
    $pids += Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
      Where-Object { $_.CommandLine -like '*uvicorn*app.main:app*' } |
      Select-Object -ExpandProperty ProcessId
    foreach ($pidToStop in ($pids | Sort-Object -Unique)) {
      if ($pidToStop -and $pidToStop -ne $PID) {
        Stop-Process -Id $pidToStop -Force
      }
    }
  `);
}

async function countBackendProcesses(): Promise<number> {
  try {
    const { stdout } = await runPowerShell(`
      $ErrorActionPreference = 'SilentlyContinue'
      $pids = @()
      $pids += Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object -ExpandProperty OwningProcess -Unique
      $pids += Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like '*uvicorn*app.main:app*' } |
        Select-Object -ExpandProperty ProcessId
      ($pids | Sort-Object -Unique | Measure-Object).Count
    `);
    return Number.parseInt(stdout.trim(), 10) || 0;
  } catch {
    return 0;
  }
}

async function startBackend() {
  await runPowerShell(`
    $ErrorActionPreference = 'Stop'
    Start-Process -WindowStyle Hidden -FilePath 'python' -ArgumentList @('-m','uvicorn','app.main:app','--host','0.0.0.0','--port','8000') -WorkingDirectory '${BACKEND_DIR.replaceAll("'", "''")}'
  `);
}

async function startComfy() {
  await runPowerShell(`
    $ErrorActionPreference = 'Stop'
    Start-Process -WindowStyle Hidden -FilePath 'cmd.exe' -ArgumentList @('/c','"${COMFY_SCRIPT.replaceAll("'", "''")}"') -WorkingDirectory '${ROOT_DIR.replaceAll("'", "''")}'
  `);
}

export async function POST(
  _request: Request,
  { params }: { params: { service: string; action: string } },
) {
  const { service: rawService, action: rawAction } = params;
  if (!isServiceName(rawService) || !isServiceAction(rawAction)) {
    return Response.json({ detail: "unsupported service action" }, { status: 400 });
  }

  try {
    if (rawService === "all") {
      if (rawAction === "restart") {
        await stopBackend();
        await new Promise((resolve) => setTimeout(resolve, 1200));
        await startBackend();
        await startComfy();
        return Response.json({ ok: true, service: rawService, action: rawAction, status: "starting" });
      }

      const backendCount = await countBackendProcesses();
      if (!(await canConnect(8000)) || backendCount > 1) {
        if (backendCount > 1) {
          await stopBackend();
          await new Promise((resolve) => setTimeout(resolve, 1200));
        }
        await startBackend();
      }
      if (!(await canConnect(8188))) {
        await startComfy();
      }
      return Response.json({ ok: true, service: rawService, action: rawAction, status: "starting" });
    }

    if (rawService === "backend") {
      const backendCount = await countBackendProcesses();
      if (rawAction === "start" && (await canConnect(8000)) && backendCount <= 1) {
        return Response.json({ ok: true, service: rawService, action: rawAction, status: "already_running" });
      }
      if (rawAction === "restart" || backendCount > 1) {
        await stopBackend();
        await new Promise((resolve) => setTimeout(resolve, 1200));
      }
      await startBackend();
      return Response.json({ ok: true, service: rawService, action: rawAction, status: "starting" });
    }

    if (rawAction === "start" && (await canConnect(8188))) {
      return Response.json({ ok: true, service: rawService, action: rawAction, status: "already_running" });
    }
    await startComfy();
    return Response.json({ ok: true, service: rawService, action: rawAction, status: "starting" });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return Response.json(
      { ok: false, service: rawService, action: rawAction, detail: message },
      { status: 500 },
    );
  }
}
