#!/usr/bin/env python3
"""Upload mini-app static files to hosting via FTP (curl).

Uses the same variables as bot catalog sync: FTP_HOST, FTP_USER, FTP_PASSWORD,
FTP_REMOTE_DIR (directory on server, e.g. /public_html/water).

Usage (from repo root):
  python3 upload_webapp_ftp.py
  python3 upload_webapp_ftp.py --ftp-user LOGIN_FROM_PANEL
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if key:
            os.environ[key] = val


def _ftp_url(host: str, remote_dir: str, remote_name: str) -> str:
    base = remote_dir.rstrip("/") if remote_dir.strip() else ""
    path = f"{base}/{remote_name}" if base else remote_name
    return f"ftp://{host}/{path.lstrip('/')}"


def curl_upload(
    local: Path,
    remote_name: str,
    host: str,
    remote_dir: str,
    user: str,
    password: str,
    *,
    tls_mode: str,
) -> tuple[bool, str]:
    url = _ftp_url(host, remote_dir, remote_name)
    cmd = [
        "curl",
        "-sS",
        "--ipv4",
        "--connect-timeout",
        "30",
        "--max-time",
        "180",
        "--ftp-pasv",
        "--ftp-skip-pasv-ip",
        "-T",
        str(local),
        url,
        "--user",
        f"{user}:{password}",
    ]
    if tls_mode == "reqd":
        cmd.insert(1, "--ssl-reqd")
    elif tls_mode == "insecure":
        cmd.insert(1, "--ftp-ssl-control")
        cmd.insert(2, "--insecure")
    elif tls_mode == "yes":
        cmd.insert(1, "--ftp-ssl-control")
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    err = (proc.stderr or proc.stdout or "").strip()
    return proc.returncode == 0, err


def main(argv: list[str] | None = None) -> int:
    raw_argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(description="Upload webapp static files via FTP (curl).")
    parser.add_argument(
        "--ftp-user",
        dest="ftp_user",
        metavar="LOGIN",
        help="FTP login from hosting panel (overrides FTP_USER in .env)",
    )
    parser.add_argument(
        "--ftp-password",
        dest="ftp_password",
        metavar="PASS",
        help="FTP password (overrides FTP_PASSWORD in .env; avoid shell history if possible)",
    )
    args, _unknown = parser.parse_known_args(raw_argv)

    load_env_file(ROOT / ".env")
    if args.ftp_user:
        os.environ["FTP_USER"] = args.ftp_user.strip()
    if args.ftp_password:
        os.environ["FTP_PASSWORD"] = args.ftp_password.strip()

    host = os.getenv("FTP_HOST", "").strip()
    user = os.getenv("FTP_USER", "").strip()
    password = os.getenv("FTP_PASSWORD", "").strip()
    remote_dir = os.getenv("FTP_REMOTE_DIR", "").strip().rstrip("/")
    if not remote_dir:
        remote_dir = "/public_html"
    tls_raw = os.getenv("FTP_TLS", "").strip().lower()
    # yes/1/true — явный TLS на управляющем канале (--ftp-ssl-control), как в Timeweb/FileZilla;
    # reqd — полный --ssl-reqd; insecure — то же + --insecure (только если проблемы с сертификатом).
    if tls_raw in ("reqd", "required", "strict"):
        tls_mode = "reqd"
    elif tls_raw in ("insecure", "insec"):
        tls_mode = "insecure"
    elif tls_raw in ("1", "true", "yes", "on"):
        tls_mode = "yes"
    else:
        tls_mode = ""

    if not (host and user and password):
        print(
            "FTP не настроен: задайте FTP_HOST, FTP_USER, FTP_PASSWORD "
            "(FTP_REMOTE_DIR по умолчанию /public_html; FTP_TLS=1 для FTPES)",
            file=sys.stderr,
        )
        return 2

    webapp = ROOT / "webapp"
    pairs: list[tuple[Path, str]] = [
        (webapp / "index.html", "index.html"),
        (webapp / "styles.css", "styles.css"),
        (webapp / "script.js", "script.js"),
    ]
    catalog = ROOT / "data" / "catalog.json"
    if catalog.exists():
        pairs.append((catalog, "catalog.json"))

    failed = False
    for local, name in pairs:
        if not local.is_file():
            print(f"skip (нет файла): {local}", file=sys.stderr)
            failed = True
            continue
        ok, msg = curl_upload(
            local, name, host, remote_dir, user, password, tls_mode=tls_mode
        )
        if ok:
            print(f"OK  {name}")
        else:
            failed = True
            print(f"ERR {name}: {msg or 'curl exit не 0'}", file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
