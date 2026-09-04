"""Create a verified, isolated PostgreSQL validation environment.

The source application database is treated as evidence. This command never
removes its volume and never rewrites its rows. It stops only currently running
application writers, creates and verifies a backup, restores that backup into
an explicitly named temporary database, and then starts a separate validation
Compose project with a fresh database volume.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "infra" / "docker-compose.yml"
WRITER_SERVICES = ("api", "web", "mcp", "temporal-worker")


class ValidationError(RuntimeError):
    """A validation precondition or operation failed."""


def run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    input_bytes: bytes | None = None,
    cwd: Path = ROOT,
) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        input=input_bytes,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValidationError(f"command failed ({completed.returncode}): {' '.join(command)}: {stderr}")
    return completed


def compose_args(project: str, env_file: Path) -> list[str]:
    return [
        "docker",
        "compose",
        "-p",
        project,
        "--env-file",
        str(env_file),
        "-f",
        str(COMPOSE_FILE),
    ]


def compose_config(project: str, env_file: Path, environment: dict[str, str]) -> dict[str, Any]:
    completed = run(
        compose_args(project, env_file) + ["config", "--format", "json"],
        env=environment,
    )
    return json.loads(completed.stdout.decode("utf-8"))


def discover_source_project(explicit: str | None) -> str:
    if explicit:
        return explicit
    completed = subprocess.run(
        [
            "docker",
            "ps",
            "--filter",
            "label=com.docker.compose.service=postgres",
            "--format",
            "{{.Label \"com.docker.compose.project\"}}",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    projects = {item.strip() for item in completed.stdout.decode().splitlines() if item.strip()}
    if len(projects) > 1:
        writer_projects: set[str] = set()
        for project in projects:
            writers = subprocess.run(
                [
                    "docker",
                    "ps",
                    "--filter",
                    f"label=com.docker.compose.project={project}",
                    "--filter",
                    "label=com.docker.compose.service=api",
                    "--format",
                    "{{.ID}}",
                ],
                cwd=ROOT,
                capture_output=True,
                check=False,
            )
            if writers.stdout.decode().strip():
                writer_projects.add(project)
        projects = writer_projects
    if len(projects) != 1:
        raise ValidationError(
            "unable to identify one running source Compose project; set SOURCE_COMPOSE_PROJECT explicitly"
        )
    return projects.pop()


def running_writers(source_args: list[str]) -> list[str]:
    running: list[str] = []
    for service in WRITER_SERVICES:
        completed = subprocess.run(
            source_args + ["ps", "-q", service],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        container_id = completed.stdout.decode().strip()
        if not container_id:
            continue
        inspected = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", container_id],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        if inspected.returncode == 0 and inspected.stdout.decode().strip() == "true":
            running.append(service)
    return running


def reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def source_identity(source_args: list[str], user: str, database: str) -> dict[str, Any]:
    query = (
        "SELECT json_build_object("
        "'database', current_database(),"
        "'user', current_user,"
        "'server_version', current_setting('server_version'),"
        "'schema_version', (SELECT version_num FROM alembic_version LIMIT 1),"
        "'audit_rows', (SELECT count(*) FROM identity_access_decisions),"
        "'audit_min_created_at', (SELECT min(created_at) FROM identity_access_decisions),"
        "'audit_max_created_at', (SELECT max(created_at) FROM identity_access_decisions)"
        ")::text"
    )
    completed = run(
        source_args
        + [
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            user,
            "-d",
            database,
            "-At",
            "-c",
            query,
        ]
    )
    value = completed.stdout.decode("utf-8").strip()
    if not value:
        raise ValidationError("database identity query returned no data")
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValidationError("database identity query returned malformed JSON") from exc


def restore_and_verify(
    source_args: list[str],
    user: str,
    source_identity_data: dict[str, Any],
    backup_path: Path,
    restore_name: str,
) -> None:
    run(
        source_args
        + [
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            user,
            "-d",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            f'CREATE DATABASE "{restore_name}"',
        ]
    )
    try:
        dump = backup_path.read_bytes()
        run(
            source_args
            + [
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                user,
                "-d",
                restore_name,
                "-v",
                "ON_ERROR_STOP=1",
            ],
            input_bytes=dump,
        )
        restored = source_identity(source_args, user, restore_name)
        for key in ("schema_version", "audit_rows", "audit_min_created_at", "audit_max_created_at"):
            if restored.get(key) != source_identity_data.get(key):
                raise ValidationError(
                    f"temporary restore mismatch for {key}: {restored.get(key)!r} != {source_identity_data.get(key)!r}"
                )
    finally:
        # This is an exact generated database name, never a wildcard.
        subprocess.run(
            source_args
            + [
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                user,
                "-d",
                "postgres",
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                f'DROP DATABASE IF EXISTS "{restore_name}"',
            ],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default=os.getenv("VALIDATION_SOURCE_ENV_FILE", ".env.demo"))
    parser.add_argument("--source-project", default=os.getenv("SOURCE_COMPOSE_PROJECT"))
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    if os.getenv("CONFIRM_VALIDATION_CREATE") != "YES" and not args.confirm:
        print("Refusing validation setup. Set CONFIRM_VALIDATION_CREATE=YES explicitly.", file=sys.stderr)
        return 2

    env_file = (ROOT / args.env_file).resolve()
    if not env_file.is_file() or ROOT not in env_file.parents:
        print("Validation env file must exist inside the repository.", file=sys.stderr)
        return 3

    source_project = discover_source_project(args.source_project)
    source_args = compose_args(source_project, env_file)
    source_environment = os.environ.copy()
    source_config = compose_config(source_project, env_file, source_environment)
    postgres_env = source_config["services"]["postgres"]["environment"]
    user = str(postgres_env["POSTGRES_USER"])
    database = str(postgres_env["POSTGRES_DB"])

    stopped: list[str] = []
    cleanup_error: str | None = None
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = ROOT / "backups" / f"validation-{stamp}"
    backup_path = backup_dir / "application.sql"
    manifest_path = backup_dir / "manifest.json"
    source_manifest: dict[str, Any] = {}
    try:
        backup_dir.mkdir(parents=True, exist_ok=False)
        stopped = running_writers(source_args)
        if stopped:
            run(source_args + ["stop", *stopped])

        source_manifest = source_identity(source_args, user, database)
        source_manifest["backup_created_at"] = datetime.now(UTC).isoformat()
        # pg_dump output is captured explicitly to avoid shell redirection.
        dump = subprocess.run(
            source_args
            + [
                "exec",
                "-T",
                "postgres",
                "pg_dump",
                "-U",
                user,
                "-d",
                database,
                "--no-owner",
                "--no-privileges",
            ],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        if dump.returncode != 0 or not dump.stdout:
            raise ValidationError("backup is missing, empty, or pg_dump failed")
        backup_path.write_bytes(dump.stdout)
        digest = hashlib.sha256(dump.stdout).hexdigest()
        source_manifest["backup_sha256"] = digest
        source_manifest["backup_bytes"] = len(dump.stdout)
        manifest_path.write_text(json.dumps(source_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if backup_path.stat().st_size == 0:
            raise ValidationError("backup file is empty")

        restore_and_verify(
            source_args,
            user,
            source_manifest,
            backup_path,
            f"oncoagent_restore_{stamp.lower()}",
        )

        validation_project = f"{source_project}-validation-{stamp.lower()}"
        validation_database = f"oncoagent_validation_{stamp.lower()}"
        validation_port = reserve_port()
        validation_env = os.environ.copy()
        validation_env.update(
            {
                "POSTGRES_DB": validation_database,
                "POSTGRES_USER": user,
                "POSTGRES_PASSWORD": str(postgres_env["POSTGRES_PASSWORD"]),
                "POSTGRES_HOST_PORT": str(validation_port),
            }
        )
        run(
            compose_args(validation_project, env_file) + ["up", "-d", "--wait", "--wait-timeout", "60", "postgres"],
            env=validation_env,
        )
        validation_database_url = (
            f"postgresql+psycopg://{user}:{postgres_env['POSTGRES_PASSWORD']}@127.0.0.1:{validation_port}/{validation_database}"
        )
        migration_env = os.environ.copy()
        migration_env["DATABASE_URL"] = validation_database_url
        run(
            [str(ROOT / "apps" / "api" / ".venv" / "bin" / "alembic"), "-c", "alembic.ini", "upgrade", "head"],
            env=migration_env,
            cwd=ROOT / "apps" / "api",
        )
        run(
            [str(ROOT / "apps" / "api" / ".venv" / "bin" / "python"), str(ROOT / "scripts" / "audit_integrity_verify.py")],
            env=migration_env,
        )
        validation_manifest = {
            "source_project": source_project,
            "validation_project": validation_project,
            "validation_database": validation_database,
            "validation_postgres_host_port": validation_port,
            "validation_volume": f"{validation_project}_oncoagent-postgres-data",
            "source_backup": str(backup_path.relative_to(ROOT)),
            "source_backup_sha256": digest,
            "created_at": datetime.now(UTC).isoformat(),
        }
        (backup_dir / "validation.json").write_text(
            json.dumps(validation_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(validation_manifest, sort_keys=True))
        return 0
    except (ValidationError, OSError, subprocess.SubprocessError, KeyError, json.JSONDecodeError) as exc:
        print(f"validation setup failed: {exc}", file=sys.stderr)
        return 3
    finally:
        if stopped:
            restarted = subprocess.run(
                source_args + ["start", *stopped],
                cwd=ROOT,
            capture_output=True,
                check=False,
            )
            if restarted.returncode != 0:
                cleanup_error = restarted.stderr.decode("utf-8", errors="replace").strip()
                print(f"cleanup failed to restart writers: {cleanup_error}", file=sys.stderr)
        if cleanup_error is not None:
            raise SystemExit(3)


if __name__ == "__main__":
    raise SystemExit(main())
