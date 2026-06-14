from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_web_dependencies_and_ignored_runtime_files_are_configured():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "fastapi" in requirements
    assert "uvicorn[standard]" in requirements
    assert "httpx2" in requirements
    assert "web/industry.db" in gitignore
    assert "web/*.db" in gitignore
    assert "logs/" in gitignore
    assert "archives/" in gitignore


def test_systemd_service_runs_uvicorn_on_loopback_port_8001():
    service = (ROOT / "deploy" / "industry-tracker.service").read_text(
        encoding="utf-8"
    )

    assert "WorkingDirectory=/home/admin/industry-tracker" in service
    assert (
        "ExecStart=/home/admin/industry-tracker/venv/bin/uvicorn "
        "web.app:app --host 127.0.0.1 --port 8001"
    ) in service
    assert "User=admin" in service


def test_nginx_fragment_proxies_to_uvicorn():
    nginx = (ROOT / "deploy" / "nginx.conf").read_text(encoding="utf-8")

    assert "listen 80;" in nginx
    assert "proxy_pass http://127.0.0.1:8001;" in nginx
    assert "proxy_set_header Host $host;" in nginx
    assert "proxy_set_header X-Real-IP $remote_addr;" in nginx
