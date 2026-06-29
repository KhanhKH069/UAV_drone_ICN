"""
scripts/health_check.py
Kiểm tra toàn bộ Drone Edge Server stack với đo Response Time.

Cách dùng:
  python scripts/health_check.py                       # kiểm tra localhost
  python scripts/health_check.py --server 192.168.1.100
  python scripts/health_check.py --watch               # loop mỗi 5 giây
  python scripts/health_check.py --json                # output JSON (cho CI/CD)
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error

SERVICES = [
    {
        "name": "api-gateway",
        "port": 8056,
        "path": "/health",
        "target_ms": 200,
        "critical": True,
        "emoji": "🌐",
    },
    {
        "name": "whisperlive (STT)",
        "port": 8001,
        "path": "/health",
        "target_ms": 500,
        "critical": True,
        "emoji": "🎙️",
    },

    {
        "name": "agent-service (LLM)",
        "port": 8005,
        "path": "/health",
        "target_ms": 300,
        "critical": True,
        "emoji": "🧠",
    },
    {
        "name": "ollama",
        "port": 11434,
        "path": "/api/tags",
        "target_ms": 500,
        "critical": False,
        "emoji": "🤖",
    },
    {
        "name": "redis",
        "port": 6379,
        "path": None,
        "target_ms": 50,
        "critical": False,
        "emoji": "🗄️",
    },
]

_R   = "\033[91m"
_G   = "\033[92m"
_Y   = "\033[93m"
_B   = "\033[94m"
_C   = "\033[96m"
_RST = "\033[0m"
_BOLD = "\033[1m"


def _check_tcp(host: str, port: int, timeout: float = 2.0) -> tuple:
    """Kiểm tra TCP connection (cho Redis không có HTTP endpoint)."""
    import socket
    t0 = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            ms = (time.perf_counter() - t0) * 1000
            return True, ms, {}
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        return False, ms, {"error": str(e)}


def _check_http(host: str, port: int, path: str, timeout: float = 5.0) -> tuple:
    """Kiểm tra HTTP endpoint và đo response time."""
    url = f"http://{host}:{port}{path}"
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "health-checker/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ms = (time.perf_counter() - t0) * 1000
            data = json.loads(resp.read().decode("utf-8"))
            return True, ms, data
    except urllib.error.HTTPError as e:
        ms = (time.perf_counter() - t0) * 1000
        return False, ms, {"http_error": e.code}
    except urllib.error.URLError as e:
        ms = (time.perf_counter() - t0) * 1000
        return False, ms, {"error": str(e.reason)}
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        return False, ms, {"error": str(e)}


def check(server: str, as_json: bool = False) -> dict:
    """
    Kiểm tra tất cả services và trả về báo cáo.

    Returns:
        dict: {"all_ok": bool, "results": [...]}
    """
    results = []
    all_ok = True

    for svc in SERVICES:
        name   = svc["name"]
        port   = svc["port"]
        emoji  = svc["emoji"]
        target = svc["target_ms"]
        critical = svc["critical"]

        if svc["path"] is None:
            ok, ms, data = _check_tcp(server, port)
        else:
            ok, ms, data = _check_http(server, port, svc["path"])

        if ok:
            if ms <= target:
                speed_label = f"{_G}FAST{_RST}"
                speed_sym = "⚡"
            elif ms <= target * 2:
                speed_label = f"{_Y}SLOW{_RST}"
                speed_sym = "🐢"
            else:
                speed_label = f"{_R}VERY SLOW{_RST}"
                speed_sym = "🐌"
        else:
            speed_label = f"{_R}DOWN{_RST}"
            speed_sym = "❌"
            if critical:
                all_ok = False

        extra = ""
        if ok and data:
            if "model" in data:
                extra = f" | model={data['model']}"
            elif "status" in data:
                extra = f" | {data['status']}"
            if "device" in data:
                extra += f" | {data['device']}"
            if "version" in data:
                extra += f" | v{data['version']}"

        result = {
            "name": name,
            "port": port,
            "ok": ok,
            "latency_ms": round(ms, 1),
            "target_ms": target,
            "critical": critical,
            "extra": data,
        }
        results.append(result)

        if not as_json:
            ok_icon = f"{_G}✅{_RST}" if ok else (f"{_R}❌{_RST}" if critical else f"{_Y}⚠️ {_RST}")
            ms_color = _G if ms <= target else _Y if ms <= target * 2 else _R
            print(
                f"  {ok_icon} {emoji} {name:<24} "
                f":{port:<6} "
                f"{ms_color}{ms:>6.0f}ms{_RST} "
                f"(target:{target}ms) "
                f"{speed_sym} {speed_label}"
                f"{extra}"
            )

    return {"all_ok": all_ok, "results": results}


def print_header(server: str):
    print(f"""
{_BOLD}{_B}╔══════════════════════════════════════════════════════════╗
║   🚁 Drone Edge Server — Health Check v2.0               ║
║   Target: {server:<48}║
╚══════════════════════════════════════════════════════════╝{_RST}
""")
    header = (
        f"  {'STATUS':<4} {'EMOJI':<4} {'SERVICE':<26} "
        f"{'PORT':<8} {'LATENCY':>8}  {'BENCHMARK':<16} NOTES"
    )
    print(f"{_BOLD}{header}{_RST}")
    print("  " + "─" * 78)


def print_summary(report: dict):
    results = report["results"]
    ok_count = sum(1 for r in results if r["ok"])
    total = len(results)
    all_ok = report["all_ok"]

    print("  " + "─" * 78)

    if all_ok:
        print(f"\n  {_G}{_BOLD}✅ ALL CRITICAL SERVICES HEALTHY ({ok_count}/{total} services up){_RST}")
        print(f"  {_G}Drone Edge Server ready — Open App Android và kết nối!{_RST}\n")
    else:
        down_critical = [r for r in results if not r["ok"] and r["critical"]]
        print(f"\n  {_R}{_BOLD}❌ {len(down_critical)} CRITICAL SERVICE(S) DOWN{_RST}")
        for svc in down_critical:
            print(f"  {_R}  → {svc['name']} (port {svc['port']}) không phản hồi{_RST}")
        print(f"\n  {_Y}💡 Chạy: docker-compose up -d để khởi động lại{_RST}\n")


def main():
    parser = argparse.ArgumentParser(
        description="🚁 Drone Edge Server — Health Check Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--server", default="localhost", help="IP của Edge Server")
    parser.add_argument("--watch", action="store_true", help="Loop kiểm tra mỗi 5 giây")
    parser.add_argument("--interval", default=5, type=int, help="Giây giữa các lần kiểm tra (--watch)")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Output JSON (cho CI/CD)")
    args = parser.parse_args()

    if args.watch:
        print(f"{_C}Watch mode: Kiểm tra mỗi {args.interval}s — Nhấn Ctrl+C để dừng{_RST}")
        try:
            while True:
                print_header(args.server)
                report = check(args.server, as_json=False)
                print_summary(report)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print(f"\n{_Y}Watch mode đã dừng.{_RST}")
        return

    if args.as_json:
        report = check(args.server, as_json=True)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        sys.exit(0 if report["all_ok"] else 1)

    print_header(args.server)
    report = check(args.server, as_json=False)
    print_summary(report)
    sys.exit(0 if report["all_ok"] else 1)


if __name__ == "__main__":
    main()
