import os
import sys
import argparse
import subprocess

from typing import List


def serve(argv: List[str] | None = None) -> int:
    """Start the KV-OptKit API server.

    Usage examples:
      kvopt serve                # uses KVOPT_ADAPTER or defaults to SIM
      kvopt serve vllm --model facebook/opt-125m --vllm-port 8000

    If engine == vllm, this will launch a vLLM OpenAI server first (best-effort),
    then start KV-OptKit pointed at it.
    """
    import argparse
    import subprocess

    # Parse optional engine and flags
    parser = argparse.ArgumentParser(prog="kvopt serve", add_help=False)
    parser.add_argument("engine", nargs="?", default=os.environ.get("KVOPT_ADAPTER", "sim"))
    parser.add_argument("--model", dest="model", default=os.environ.get("KVOPT_VLLM_MODEL"))
    parser.add_argument("--vllm-port", dest="vllm_port", default=os.environ.get("KVOPT_VLLM_PORT", "8000"))
    parser.add_argument("--adapter-port", dest="adapter_port", default=os.environ.get("KVOPT_PORT", "9001"))
    args, _ = parser.parse_known_args(argv or [])

    # Ensure server port propagated
    os.environ["KVOPT_PORT"] = str(args.adapter_port)

    vllm_proc = None
    try:
        if str(args.engine).lower() == "vllm":
            # Start vLLM API server (if model provided)
            model = args.model
            if not model:
                print("No --model provided; starting KV-OptKit without launching vLLM.")
            else:
                cmd = [
                    sys.executable,
                    "-m",
                    "vllm.entrypoints.openai.api_server",
                    "--model",
                    model,
                    "--port",
                    str(args.vllm_port),
                ]
                print("Launching vLLM server:", " ".join(cmd))
                try:
                    vllm_proc = subprocess.Popen(cmd)
                    os.environ["UPSTREAM_VLLM_URL"] = f"http://localhost:{args.vllm_port}"
                except FileNotFoundError:
                    print("vLLM not installed; continuing without launching upstream.")

            # Point adapter to vLLM
            os.environ["KVOPT_ADAPTER"] = "vllm"

        # Start KV-OptKit server
        from kvopt.server.main import run
        run()
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        if vllm_proc is not None:
            try:
                vllm_proc.terminate()
            except Exception:
                pass


def quickstart(argv: List[str] | None = None) -> int:
    """Zero-friction quickstart: start server and open QuickView."""
    import webbrowser
    # Start server in a child process (Windows-friendly)
    port = os.environ.get("KVOPT_PORT", "9001")
    env = os.environ.copy()
    env["KVOPT_PORT"] = str(port)
    # Launch uvicorn in a new console if possible
    cmd = [sys.executable, "-m", "kvopt.server.main"]
    print(f"Starting server on :{port} ...")
    proc = subprocess.Popen(cmd, env=env)
    # Open QuickView
    url = f"http://localhost:{port}/"
    print(f"Opening QuickView at {url} ...")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    print("Press Ctrl+C to stop. Server PID:", proc.pid)
    try:
        proc.wait()
        return proc.returncode or 0
    except KeyboardInterrupt:
        proc.terminate()
        return 0


def quickstart_vllm_demo(argv: List[str] | None = None) -> int:
    """Start vLLM adapter with demo sequences and open QuickView."""
    import webbrowser
    env = os.environ.copy()
    env["KVOPT_ADAPTER"] = "vllm"
    env["KVOPT_DEMO_SEQS"] = "1"
    port = env.get("KVOPT_PORT", "9001")
    env["KVOPT_PORT"] = str(port)
    cmd = [sys.executable, "-m", "kvopt.server.main"]
    print(f"Starting KV-OptKit (vLLM demo) on :{port} ...")
    proc = subprocess.Popen(cmd, env=env)
    url = f"http://localhost:{port}/"
    print(f"Opening QuickView at {url} ...")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    print("Press Ctrl+C to stop. Server PID:", proc.pid)
    try:
        proc.wait()
        return proc.returncode or 0
    except KeyboardInterrupt:
        proc.terminate()
        return 0


def dev_hooks(argv: List[str] | None = None) -> int:
    """Start server with KVOPT_DEV=1 and open QuickView (Dev Hooks panel enabled)."""
    import webbrowser
    env = os.environ.copy()
    env["KVOPT_DEV"] = "1"
    port = env.get("KVOPT_PORT", "9001")
    env["KVOPT_PORT"] = str(port)
    cmd = [sys.executable, "-m", "kvopt.server.main"]
    print(f"Starting KV-OptKit (Dev Hooks) on :{port} ...")
    proc = subprocess.Popen(cmd, env=env)
    url = f"http://localhost:{port}/"
    print(f"Opening QuickView at {url} ...")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    print("Dev Hooks API under /dev/hooks; see demo guide for commands.")
    print("Press Ctrl+C to stop. Server PID:", proc.pid)
    try:
        proc.wait()
        return proc.returncode or 0
    except KeyboardInterrupt:
        proc.terminate()
        return 0

def autopilot(argv: List[str] | None = None) -> int:
    """Kick off the Phase 2 combined autopilot demo workflow."""
    script = os.path.join("examples", "demo_phase2_autopilot.ps1")
    if not os.path.exists(script):
        print("Phase 2 demo script not found:", script)
        return 1
    # Let PowerShell handle the demo; user interacts to start server.
    print("Running Phase 2 Autopilot demo...")
    try:
        return subprocess.call(["powershell", "-ExecutionPolicy", "Bypass", "-File", script])
    except FileNotFoundError:
        print("PowerShell not found. Please run the script manually:")
        print(script)
        return 1


def sidecar(argv: List[str] | None = None) -> int:
    """Run the KV-OptKit sidecar proxy (Phase 5).

    Options (also available via environment variables):
      --upstream  / UPSTREAM_VLLM_URL   (default: http://localhost:8000)
      --kvopt-url / KVOPT_URL           (default: http://localhost:9001)
      --port      / PROXY_PORT          (default: 9010)
    """
    import shlex

    parser = argparse.ArgumentParser(prog="kvopt sidecar", add_help=False)
    parser.add_argument("--upstream", dest="upstream", default=os.environ.get("UPSTREAM_VLLM_URL", "http://localhost:8000"))
    parser.add_argument("--kvopt-url", dest="kvopt_url", default=os.environ.get("KVOPT_URL", "http://localhost:9001"))
    parser.add_argument("--port", dest="port", default=os.environ.get("PROXY_PORT", "9010"))
    parser.add_argument("--", dest="--", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    args, _ = parser.parse_known_args(argv or [])

    env = os.environ.copy()
    env["UPSTREAM_VLLM_URL"] = str(args.upstream)
    env["KVOPT_URL"] = str(args.kvopt_url)
    env["PROXY_PORT"] = str(args.port)

    script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "kvopt_sidecar_proxy.py")
    if not os.path.exists(script):
        # Fallback: try relative to CWD (repo root)
        script = os.path.join("scripts", "kvopt_sidecar_proxy.py")
    if not os.path.exists(script):
        print("Sidecar proxy script not found: scripts/kvopt_sidecar_proxy.py")
        return 1

    cmd = [sys.executable, script]
    print("Starting KV-OptKit sidecar proxy:")
    print("  UPSTREAM_VLLM_URL=", env["UPSTREAM_VLLM_URL"])  # noqa: T201
    print("  KVOPT_URL=", env["KVOPT_URL"])  # noqa: T201
    print("  PROXY_PORT=", env["PROXY_PORT"])  # noqa: T201
    try:
        return subprocess.call(cmd, env=env)
    except KeyboardInterrupt:
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="kvopt", description="KV-OptKit CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sp_serve = sub.add_parser("serve", help="Start the API server; optionally launch vLLM")
    sp_serve.add_argument("engine", nargs="?", help="optional engine name, e.g., vllm")
    sp_serve.add_argument("--model", help="vLLM model id to launch when engine=vllm")
    sp_serve.add_argument("--vllm-port", default=os.environ.get("KVOPT_VLLM_PORT", "8000"), help="Port for vLLM OpenAI server")
    sp_serve.add_argument("--adapter-port", default=os.environ.get("KVOPT_PORT", "9001"), help="Port for KV-OptKit server")
    sub.add_parser("quickstart", help="Start server and open QuickView UI")
    sub.add_parser("quickstart-vllm-demo", help="Start vLLM adapter with demo sequences and open QuickView")
    sub.add_parser("dev-hooks", help="Start server with KVOPT_DEV=1 and open QuickView (Dev Hooks enabled)")
    sub.add_parser("autopilot", help="Run Phase 2 combined autopilot demo")
    sp = sub.add_parser("sidecar", help="Run the OpenAI-compatible sidecar proxy")
    sp.add_argument("--upstream", default=os.environ.get("UPSTREAM_VLLM_URL", "http://localhost:8000"), help="Upstream vLLM OpenAI server URL")
    sp.add_argument("--kvopt-url", default=os.environ.get("KVOPT_URL", "http://localhost:9001"), help="KV-OptKit server base URL")
    sp.add_argument("--port", default=os.environ.get("PROXY_PORT", "9010"), help="Sidecar proxy port")

    args = parser.parse_args()
    if args.cmd == "serve":
        return serve()
    if args.cmd == "quickstart":
        return quickstart()
    if args.cmd == "quickstart-vllm-demo":
        return quickstart_vllm_demo()
    if args.cmd == "dev-hooks":
        return dev_hooks()
    if args.cmd == "autopilot":
        return autopilot()
    if args.cmd == "sidecar":
        return sidecar()
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
