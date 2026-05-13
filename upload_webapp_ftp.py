#!/usr/bin/env python3
"""Upload mini-app static files to hosting via FTP (curl).

Uses the same variables as bot catalog sync: FTP_HOST, FTP_USER, FTP_PASSWORD,
FTP_REMOTE_DIR (пусто/auto — автопоиск каталога на Timeweb, см. README).

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
from urllib.parse import urlparse

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
    path = path.replace("//", "/")
    # Один «/» после хоста — у curl это обычно путь относительно домашней папки FTP.
    # Полный путь вроде /home/… ломался и падал через перебор в «корень» (пустая строка в кандидатах).
    if path.startswith("/"):
        return f"ftp://{host}//{path.lstrip('/')}"
    return f"ftp://{host}/{path}"


def _apply_tls(cmd: list[str], tls_mode: str) -> None:
    if tls_mode == "reqd":
        cmd.insert(1, "--ssl-reqd")
    elif tls_mode == "insecure":
        cmd.insert(1, "--ftp-ssl-control")
        cmd.insert(2, "--insecure")
    elif tls_mode == "yes":
        cmd.insert(1, "--ftp-ssl-control")


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def _paths_relative_to_home_ftp(pref: str) -> list[str]:
    """На Timeweb после логина корень FTP часто = ~аккаунт; путь /home/X/Y/site → site относительно."""
    pref = pref.strip().rstrip("/")
    if not pref.startswith("/"):
        return []
    parts = [p for p in pref.split("/") if p]
    if len(parts) < 4 or parts[0] != "home":
        return []
    tail = "/".join(parts[3:])
    return [tail] if tail else []


def build_remote_candidates(webapp_url: str, ftp_remote_dir_raw: str) -> list[str]:
    raw_in = ftp_remote_dir_raw.strip()
    # Явный «только корень сессии FTP» (редко нужно).
    force_login_root_only = raw_in.lower() in ("-", "cwd", "~")
    # Пусто / auto / точка — авто-поиск (точку раньше многие ставили по ошибке).
    treat_auto = raw_in.lower() in ("", "auto", ".")

    base: list[str] = []
    parsed = urlparse(webapp_url.strip().split("#")[0])
    if parsed.hostname:
        h = parsed.hostname.strip().lower()
        base.extend(
            (
                f"/domains/{h}/public_html",
                f"domains/{h}/public_html",
            )
        )

    base.extend(("public_html", "/public_html", ""))
    base = _dedupe(base)

    if force_login_root_only:
        return _dedupe([""])

    if treat_auto:
        return base

    pref = raw_in.rstrip("/")
    under_home = _paths_relative_to_home_ftp(pref)
    return _dedupe(
        [pref] + under_home + [x for x in base if x != pref and x not in under_home]
    )


def pick_remote_prefix(
    host: str,
    user: str,
    password: str,
    tls_mode: str,
    candidates: list[str],
) -> tuple[str | None, str]:
    probe_local = ROOT / ".ftp_probe_upload_tmp"
    remote_probe_name = ".ftp_upload_probe.delme"
    last_err = ""

    try:
        probe_local.write_bytes(b".")

        for cand in candidates:
            stor_url = _ftp_url(host, cand, remote_probe_name)
            stor_cmd = [
                "curl",
                "-sS",
                "--ipv4",
                "--connect-timeout",
                "25",
                "--max-time",
                "90",
                "--ftp-pasv",
                "--ftp-skip-pasv-ip",
                "-T",
                str(probe_local),
                stor_url,
                "--user",
                f"{user}:{password}",
            ]
            _apply_tls(stor_cmd, tls_mode)
            sr = subprocess.run(
                stor_cmd, capture_output=True, text=True, check=False
            )
            last_err = (sr.stderr or sr.stdout or "").strip()
            if sr.returncode == 0:
                return cand, ""

        return None, last_err or "no FTP path succeeded"
    finally:
        try:
            if probe_local.exists():
                probe_local.unlink()
        except OSError:
            pass


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
    _apply_tls(cmd, tls_mode)
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

    ftp_remote_raw = os.getenv("FTP_REMOTE_DIR", "").strip()
    webapp_url = os.getenv("WEBAPP_URL", "").strip()
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
            "(FTP_REMOTE_DIR: не задавайте или auto — автопоиск каталога; "
            "«.» как авто; «-» — только корень FTP; FTP_TLS=1 для FTPES). "
            "Нужен WEBAPP_URL для domains/*/public_html на Timeweb.",
            file=sys.stderr,
        )
        return 2

    candidates = build_remote_candidates(webapp_url, ftp_remote_raw)
    remote_prefix, probe_msg = pick_remote_prefix(
        host, user, password, tls_mode, candidates
    )
    if remote_prefix is None:
        print(
            f"Не удалось подобрать каталог на FTP ({probe_msg}). "
            f"Проверьте WEBAPP_URL и при необходимости задайте FTP_REMOTE_DIR вручную в .env",
            file=sys.stderr,
        )
        return 1

    hint = "." if remote_prefix == "" else remote_prefix
    print(f"FTP каталог: {hint}")

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
            local, name, host, remote_prefix, user, password, tls_mode=tls_mode
        )
        if ok:
            print(f"OK  {name}")
        else:
            failed = True
            print(f"ERR {name}: {msg or 'curl exit не 0'}", file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
