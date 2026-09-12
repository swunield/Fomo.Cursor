# -*- coding: utf-8 -*-
"""Upload FOMO Desk to the Linux host and configure nginx + systemd."""
from __future__ import annotations

import posixpath
import stat
import sys
import time
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
REMOTE_DIR = "/opt/Fomo"
DOMAIN = "fomo.niceshotgame.xyz"
SKIP_DIRS = {
    ".git",
    ".cursor",
    ".playwright-fomo-chrome",
    ".playwright-debot-chrome",
    "__pycache__",
    ".venv",
    "tmp_fomo_js",
    ".tmp_fomo_js",
}
SKIP_FILES = {
    "Server.conf",
    "push.py",
    "fomo_auth.json",
    "fomo_oauth_pending.json",
    "fomo_token_meta_cache.json",
    "fomo_mcap_ath_cache.json",
    "fomo_mcap_live_cache.json",
    "fomo_settings.json",
}
SKIP_SUFFIXES = {".pyc", ".bat"}
SKIP_NAME_PREFIXES = ("tmp_", "probe_")
SKIP_NAME_SUFFIXES = (
    "_last_result.json",
    "_holdings_by_token.csv",
    "_holdings_by_token.json",
    "_holdings_by_token.md",
)


def load_conf() -> dict[str, str]:
    kv: dict[str, str] = {}
    for line in (ROOT / "Server.conf").read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        kv[key.strip()] = value.strip()
    return kv


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 300) -> tuple[int, str, str]:
    print(f"$ {cmd}", flush=True)
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    if out.strip():
        print(out.rstrip(), flush=True)
    if err.strip():
        print(err.rstrip(), flush=True)
    if code != 0:
        print(f"[exit {code}]", flush=True)
    return code, out, err


def should_skip(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in SKIP_DIRS for part in rel.parts):
        return True
    name = path.name
    if name in SKIP_FILES:
        return True
    if path.suffix in SKIP_SUFFIXES:
        return True
    if name.startswith(SKIP_NAME_PREFIXES):
        return True
    if name.endswith(SKIP_NAME_SUFFIXES):
        return True
    return False


def local_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or should_skip(path):
            continue
        files.append(path)
    return files


def ensure_remote_dir(sftp: paramiko.SFTPClient, remote: str) -> None:
    parts = [p for p in remote.split("/") if p]
    cur = ""
    for part in parts:
        cur += "/" + part
        try:
            sftp.stat(cur)
        except FileNotFoundError:
            sftp.mkdir(cur)


def upload(sftp: paramiko.SFTPClient) -> int:
    files = local_files()
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        remote = posixpath.join(REMOTE_DIR, rel)
        ensure_remote_dir(sftp, posixpath.dirname(remote))
        print(f"put {rel}", flush=True)
        data = path.read_bytes()
        if path.suffix in {".py", ".sh", ".conf", ".service", ".txt", ".md", ".html", ".js", ".css", ".json", ".csv"} or path.name in {".gitignore"}:
            data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        with sftp.file(remote, "wb") as fh:
            fh.write(data)
    return len(files)


def main() -> int:
    conf = load_conf()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"connect {conf['Host']} ...", flush=True)
    client.connect(
        conf["Host"],
        username=conf["User"],
        password=conf["Password"],
        timeout=20,
        look_for_keys=False,
        allow_agent=False,
    )

    code, _, _ = run(
        client,
        "dnf install -y nginx python3-pip certbot python3-certbot-nginx",
        timeout=300,
    )
    if code != 0:
        return code

    sftp = client.open_sftp()
    ensure_remote_dir(sftp, REMOTE_DIR)
    count = upload(sftp)
    print(f"uploaded {count} files", flush=True)
    run(client, "rm -f /opt/Fomo/fomo_debot.py /opt/Fomo/tests/test_debot_story.py")

    code, _, _ = run(client, "chmod +x /opt/Fomo/deploy/remote-setup.sh && bash /opt/Fomo/deploy/remote-setup.sh", timeout=600)
    if code != 0:
        run(client, "journalctl -u fomo -n 80 --no-pager; nginx -t; systemctl status fomo nginx --no-pager")
        return code

    run(client, "sleep 1; curl -fsS http://127.0.0.1:8787/ | head -c 200; echo; curl -fsSI http://127.0.0.1/ -H 'Host: fomo.niceshotgame.xyz' | head")

    cert = (
        "certbot --nginx -d "
        + DOMAIN
        + " --non-interactive --agree-tos --register-unsafely-without-email --redirect"
    )
    cert_code, _, _ = run(client, cert, timeout=180)
    if cert_code != 0:
        print("certbot failed; HTTP may still work if 80/443 are open in the cloud security group", flush=True)

    run(
        client,
        "install -m 644 /opt/Fomo/deploy/nginx-fomo-ip.conf /etc/nginx/conf.d/fomo-ip.conf; "
        "sed -i 's/listen 80 default_server;/listen 80;/' /etc/nginx/conf.d/fomo.conf; "
        "sed -i 's/listen \\[::\\]:80 default_server;/listen [::]:80;/' /etc/nginx/conf.d/fomo.conf; "
        "nginx -t && systemctl reload nginx",
    )

    run(client, "systemctl --no-pager --full status fomo nginx | sed -n '1,40p'")
    run(client, "ss -lntp | grep -E ':80|:443|:8787' || true")
    run(
        client,
        f"curl -fsSI http://127.0.0.1/ -H 'Host: {DOMAIN}' | head; "
        f"curl -kfsSI https://127.0.0.1/ -H 'Host: {DOMAIN}' | head || true; "
        f"curl -fsS http://127.0.0.1/ -H 'Host: {conf['Host']}' | head -c 180; echo",
    )
    client.close()
    return 0 if cert_code == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
