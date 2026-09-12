"""The lab's standard event log: what happened, who caused it, and how it went.

Drop this file into a service, construct one `Metrics`, and every request,
connection or job run leaves a durable row behind. It is deliberately plain
stdlib and framework-agnostic — `metrics_api.py` is the FastAPI skin over it,
but a plain script or a thread-based daemon can use this directly.

Two tables, because the servers here produce two shapes of fact:

  * **sessions** — a unit of work that has a duration and an outcome: an HTTP
    request, a websocket connection, a cron run. Opened when it starts, closed
    when it ends. This is what the dashboard's tables and per-actor rollups read.
  * **events** — an append-only timeline of moments, including ones that belong
    to no session at all (`service.start`, a device failure, a config reload).
    This is what you read when you need to know *why*, and what survives to
    answer "what has this thing been doing" months later.

Why SQLite rather than a log file: the questions worth asking are aggregate
ones — who connects most, what fails, is it slower than last week — and those
are one query against a table and a full-text scavenger hunt against a file.
Volume on these services is a handful of rows per minute, so the whole history
fits comfortably and is never pruned unless you ask for it.

The database lives on **local disk** (`/var/lib/<service>/`), never on the NFS
home: SQLite's locking over NFS is not something to bet a service's write path
on. Stdout logging is unaffected and should stay — `journalctl -fu <service>`
remains the right tool for a live tail; this is for history and aggregates.
"""

from __future__ import annotations

import json
import logging
import os
import re
import socket
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

log = logging.getLogger("metrics")

SCHEMA_VERSION = 1

# Session outcomes. `active` is the only non-terminal one; anything still active
# when the process starts up again was cut short by a crash or a restart, and is
# rewritten as `interrupted` so nothing sits open forever.
ACTIVE = "active"
OK = "ok"
ERROR = "error"
REJECTED = "rejected"
INTERRUPTED = "interrupted"

# Field names reach SQL as json_extract paths, so they are checked rather than
# trusted — these come from a service's own schema declaration, but a typo
# should fail loudly here and not somewhere stranger.
_SAFE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _check_name(name: str) -> str:
    if not _SAFE_NAME.match(name):
        raise ValueError(f"unsafe field name {name!r}: expected [A-Za-z_][A-Za-z0-9_]*")
    return name


_DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    kind         TEXT NOT NULL,
    actor        TEXT,
    actor_ip     TEXT,
    actor_host   TEXT,
    actor_source TEXT,
    user_agent   TEXT,
    started_at   REAL NOT NULL,
    ended_at     REAL,
    duration_s   REAL,
    status       TEXT NOT NULL DEFAULT 'active',
    error        TEXT,
    fields       TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS sessions_started ON sessions(started_at DESC);
CREATE INDEX IF NOT EXISTS sessions_actor   ON sessions(actor, started_at DESC);
CREATE INDEX IF NOT EXISTS sessions_kind    ON sessions(kind, started_at DESC);
CREATE INDEX IF NOT EXISTS sessions_status  ON sessions(status);

CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         REAL NOT NULL,
    level      TEXT NOT NULL DEFAULT 'info',
    kind       TEXT NOT NULL DEFAULT 'service',
    event      TEXT NOT NULL,
    session_id TEXT,
    actor      TEXT,
    message    TEXT,
    fields     TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS events_ts      ON events(ts DESC);
CREATE INDEX IF NOT EXISTS events_session ON events(session_id);
CREATE INDEX IF NOT EXISTS events_level   ON events(level, ts DESC);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


# --------------------------------------------------------------------- actors


class ActorResolver:
    """Turn a peer address into a name a person recognises.

    Callers rarely say who they are, so this tries in order and records which
    layer won, because "this is a guess from reverse DNS" and "this client told
    us its name" deserve different amounts of trust on a dashboard:

      1. what the caller declared (an `X-Client-Name` header, a query param) —
         passed in as `declared`;
      2. a static IP→name map from config, for the hosts that have no PTR;
      3. for loopback peers, the process on the other end of the socket, found
         through /proc — this is the layer that matters, because a local client
         is otherwise just "localhost" forever;
      4. reverse DNS;
      5. the bare IP.

    Every lookup is best-effort and cached; none of it may raise into a request
    path, so the whole thing is wrapped and failures degrade to the layer below.
    """

    def __init__(
        self,
        static_map: dict[str, str] | None = None,
        *,
        resolve_local_process: bool = True,
        ttl_s: float = 300.0,
    ) -> None:
        self.static_map = dict(static_map or {})
        self.resolve_local_process = resolve_local_process
        self.ttl_s = ttl_s
        self._cache: dict[tuple[str, int | None], tuple[float, str, str, str | None]] = {}
        self._lock = threading.Lock()

    def resolve(
        self,
        ip: str | None,
        *,
        port: int | None = None,
        declared: str | None = None,
    ) -> tuple[str, str, str | None]:
        """Return `(name, source, hostname)`. Never raises."""
        if declared:
            return declared, "declared", None
        if not ip:
            return "unknown", "unknown", None

        key = (ip, port if self._is_loopback(ip) else None)
        now = time.time()
        with self._lock:
            hit = self._cache.get(key)
            if hit and now - hit[0] < self.ttl_s:
                return hit[1], hit[2], hit[3]

        name, source, hostname = self._lookup(ip, port)
        with self._lock:
            self._cache[key] = (now, name, source, hostname)
        return name, source, hostname

    # -- layers ------------------------------------------------------------

    def _lookup(self, ip: str, port: int | None) -> tuple[str, str, str | None]:
        if ip in self.static_map:
            return self.static_map[ip], "static", None

        if self.resolve_local_process and self._is_loopback(ip) and port:
            proc = self._local_process(ip, port)
            if proc:
                return proc, "process", None

        host = self._reverse_dns(ip)
        if host and host not in ("localhost", "localhost.localdomain"):
            return host.split(".")[0], "dns", host

        return ip, "ip", host

    @staticmethod
    def _is_loopback(ip: str) -> bool:
        return ip in ("127.0.0.1", "::1") or ip.startswith("127.")

    @staticmethod
    def _reverse_dns(ip: str) -> str | None:
        try:
            return socket.gethostbyaddr(ip)[0]
        except Exception:
            return None

    def _local_process(self, ip: str, port: int) -> str | None:
        """Name the process holding the loopback socket on `port`.

        Walks /proc the way `ss -p` does: the peer's port gives a socket inode
        in /proc/net/tcp{,6}, and the pid that has that inode open gives a name.
        Needs to be able to read other processes' fds, which the services here
        get by running as root; without that it simply finds nothing and the
        caller falls through to reverse DNS.
        """
        try:
            inode = self._socket_inode(ip, port)
            if inode is None:
                return None
            target = f"socket:[{inode}]"
            for pid in os.listdir("/proc"):
                if not pid.isdigit():
                    continue
                fd_dir = f"/proc/{pid}/fd"
                try:
                    fds = os.listdir(fd_dir)
                except OSError:
                    continue
                for fd in fds:
                    try:
                        if os.readlink(f"{fd_dir}/{fd}") != target:
                            continue
                    except OSError:
                        continue
                    return self._process_name(pid)
        except Exception:
            log.debug("local process lookup failed for %s:%s", ip, port, exc_info=True)
        return None

    @staticmethod
    def _socket_inode(ip: str, port: int) -> str | None:
        want_port = f"{port:04X}"
        for path in ("/proc/net/tcp", "/proc/net/tcp6"):
            try:
                with open(path) as fh:
                    next(fh, None)  # header
                    for line in fh:
                        parts = line.split()
                        if len(parts) < 10:
                            continue
                        if parts[1].rsplit(":", 1)[-1] == want_port:
                            return parts[9]
            except OSError:
                continue
        return None

    @staticmethod
    def _process_name(pid: str) -> str:
        """Prefer something identifying over `python3`, which names half the lab."""
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as fh:
                argv = [a.decode(errors="replace") for a in fh.read().split(b"\0") if a]
        except OSError:
            argv = []
        for arg in argv:
            # A venv path or a working directory usually carries the service name.
            m = re.search(r"/usr/local/bin/([A-Za-z0-9_-]+)", arg)
            if m:
                return m.group(1)
        try:
            with open(f"/proc/{pid}/comm") as fh:
                return fh.read().strip() or f"pid:{pid}"
        except OSError:
            return f"pid:{pid}"


# -------------------------------------------------------------------- session


class Session:
    """One unit of work, open until it is closed.

    Use it as a context manager. An exception on the way out is recorded as the
    session's error and re-raised — the log should never be the reason a caller
    stops seeing its own failures.
    """

    def __init__(self, metrics: Metrics, session_id: str, kind: str) -> None:
        self.metrics = metrics
        self.session_id = session_id
        self.kind = kind
        self.started_at = time.time()
        self.fields: dict[str, Any] = {}
        self.status = ACTIVE
        self.error: str | None = None
        self._closed = False

    # -- during ------------------------------------------------------------

    def set(self, **fields: Any) -> Session:
        """Record or overwrite measurements on this session."""
        self.fields.update(fields)
        self.metrics._update_session_fields(self.session_id, self.fields)
        return self

    def add(self, field: str, amount: float = 1) -> Session:
        """Increment a counter — bytes moved, messages handled, retries."""
        self.fields[field] = self.fields.get(field, 0) + amount
        return self

    def flush(self) -> Session:
        """Persist counters accumulated with `add()`.

        Separate from `add()` on purpose: a websocket counting every frame would
        otherwise write to disk thousands of times a second. Call this on a slow
        timer or at close.
        """
        self.metrics._update_session_fields(self.session_id, self.fields)
        return self

    def event(self, event: str, *, level: str = "info", message: str | None = None, **fields: Any) -> None:
        self.metrics.event(
            event, kind=self.kind, level=level, session_id=self.session_id, message=message, **fields
        )

    def fail(self, error: str | BaseException, *, status: str = ERROR) -> Session:
        self.error = str(error)
        self.status = status
        return self

    def reject(self, reason: str) -> Session:
        """A caller's fault rather than the service's — a bad upload, a 4xx."""
        return self.fail(reason, status=REJECTED)

    # -- end ---------------------------------------------------------------

    def close(self, status: str | None = None, *, ended_at: float | None = None) -> None:
        """End the session. `ended_at` says when it *really* ended.

        Pass it when the end is noticed later than it happened — a stream whose
        frames stopped and was reaped by a sweep on the next tick, a connection
        found dead by a timeout. Without it the detection delay is recorded as
        part of the work, which quietly inflates every duration and deflates
        every rate computed from one.
        """
        if self._closed:
            return
        self._closed = True
        if status is None:
            # An outcome already chosen by fail()/reject() wins; otherwise an
            # error recorded along the way means error, and silence means ok.
            status = self.status if self.status != ACTIVE else (ERROR if self.error else OK)
        self.status = status
        self.metrics._close_session(
            self.session_id, status, self.error, self.fields, self.started_at, ended_at
        )

    def __enter__(self) -> Session:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc is not None and self.error is None:
            self.fail(f"{exc_type.__name__}: {exc}")
            self.event("exception", level="error", message=str(exc))
        self.close()
        return False


# -------------------------------------------------------------------- metrics


class Metrics:
    """The event log for one service.

    Construct once at startup, close at shutdown. Writes go through a single
    connection under a lock: they are sub-millisecond and a few per request, so
    an executor hop would cost more than it saves. Do not "fix" this by moving
    it to a thread pool without measuring first.
    """

    def __init__(
        self,
        service: str,
        *,
        data_dir: str | os.PathLike[str] | None = None,
        db_name: str = "metrics.db",
        retention_days: float = 0.0,
        schema: dict[str, Any] | None = None,
        resolver: ActorResolver | None = None,
        version: str | None = None,
    ) -> None:
        self.service = service
        self.schema = schema or {}
        self.version = version
        self.resolver = resolver or ActorResolver()
        self.started_at = time.time()

        self.path = Path(data_dir or f"/var/lib/{service}") / db_name
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        # WAL so a long dashboard query never blocks the write path.
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.executescript(_DDL)
        self._db.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(SCHEMA_VERSION),),
        )
        self._db.commit()

        self._gauges: dict[str, Any] = {}
        self._counters: dict[str, float] = {}

        self._reap_active()
        if retention_days > 0:
            self.prune(retention_days)

    # -- lifecycle ---------------------------------------------------------

    def service_start(self, **fields: Any) -> None:
        """Log that the service came up. Restarts should be visible in history."""
        self.event("service.start", kind="service", version=self.version, **fields)

    def service_stop(self, **fields: Any) -> None:
        self.event("service.stop", kind="service", uptime_s=round(self.uptime_s, 3), **fields)

    def close(self) -> None:
        with self._lock:
            self._db.commit()
            self._db.close()

    @property
    def uptime_s(self) -> float:
        return time.time() - self.started_at

    def _reap_active(self) -> None:
        """Close out sessions the last process never got to finish."""
        with self._lock:
            cur = self._db.execute(
                "UPDATE sessions SET status=?, error=COALESCE(error, 'process exited') "
                "WHERE status=?",
                (INTERRUPTED, ACTIVE),
            )
            self._db.commit()
        if cur.rowcount:
            log.warning("%d session(s) were left open by a previous run", cur.rowcount)

    def prune(self, days: float) -> int:
        """Drop history older than `days`. Off by default — history is the point."""
        cutoff = time.time() - days * 86400
        with self._lock:
            n = self._db.execute("DELETE FROM sessions WHERE started_at < ?", (cutoff,)).rowcount
            n += self._db.execute("DELETE FROM events WHERE ts < ?", (cutoff,)).rowcount
            self._db.commit()
        if n:
            log.info("pruned %d row(s) older than %s days", n, days)
        return n

    # -- writing -----------------------------------------------------------

    def event(
        self,
        event: str,
        *,
        kind: str = "service",
        level: str = "info",
        session_id: str | None = None,
        actor: str | None = None,
        message: str | None = None,
        **fields: Any,
    ) -> None:
        """Record a moment. Also mirrored to the stdlib logger for journald."""
        fields = {k: v for k, v in fields.items() if v is not None}
        with self._lock:
            self._db.execute(
                "INSERT INTO events(ts, level, kind, event, session_id, actor, message, fields) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (time.time(), level, kind, event, session_id, actor, message, json.dumps(fields)),
            )
            self._db.commit()
        log.log(
            {"error": logging.ERROR, "warn": logging.WARNING}.get(level, logging.INFO),
            "%s %s%s",
            event,
            message or "",
            f" {fields}" if fields else "",
        )

    def session(
        self,
        kind: str,
        *,
        ip: str | None = None,
        port: int | None = None,
        declared: str | None = None,
        user_agent: str | None = None,
        **fields: Any,
    ) -> Session:
        """Open a session. Resolves the actor as a side effect."""
        actor, source, hostname = self.resolver.resolve(ip, port=port, declared=declared)
        session_id = uuid.uuid4().hex[:16]
        started = time.time()
        fields = {k: v for k, v in fields.items() if v is not None}
        with self._lock:
            self._db.execute(
                "INSERT INTO sessions(session_id, kind, actor, actor_ip, actor_host, actor_source, "
                "user_agent, started_at, status, fields) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (session_id, kind, actor, ip, hostname, source, user_agent, started, ACTIVE,
                 json.dumps(fields)),
            )
            self._db.commit()
        s = Session(self, session_id, kind)
        s.started_at = started
        s.fields = dict(fields)
        return s

    def _update_session_fields(self, session_id: str, fields: dict[str, Any]) -> None:
        payload = json.dumps({k: v for k, v in fields.items() if v is not None})
        with self._lock:
            self._db.execute("UPDATE sessions SET fields=? WHERE session_id=?", (payload, session_id))
            self._db.commit()

    def _close_session(
        self, session_id: str, status: str, error: str | None, fields: dict[str, Any],
        started_at: float, ended_at: float | None = None,
    ) -> None:
        # A caller-supplied end never predates the start, whatever clock it came
        # from — a negative duration is worse than a slightly late one.
        ended = time.time() if ended_at is None else max(ended_at, started_at)
        payload = json.dumps({k: v for k, v in fields.items() if v is not None})
        with self._lock:
            self._db.execute(
                "UPDATE sessions SET ended_at=?, duration_s=?, status=?, error=?, fields=? "
                "WHERE session_id=?",
                (ended, round(ended - started_at, 6), status, error, payload, session_id),
            )
            self._db.commit()

    # -- live state --------------------------------------------------------

    def gauge(self, name: str, value: Any) -> None:
        """Something's current value — queue depth, what's playing, connections."""
        self._gauges[name] = value

    def counter(self, name: str, amount: float = 1) -> None:
        """A since-startup total that isn't worth a row of its own."""
        self._counters[name] = self._counters.get(name, 0) + amount

    # -- reading -----------------------------------------------------------

    def status(self) -> dict[str, Any]:
        with self._lock:
            row = self._db.execute(
                "SELECT COUNT(*) AS total, "
                "SUM(CASE WHEN status=? THEN 1 ELSE 0 END) AS active, "
                "SUM(CASE WHEN status IN (?,?) THEN 1 ELSE 0 END) AS failed, "
                "SUM(CASE WHEN started_at >= ? THEN 1 ELSE 0 END) AS last_24h "
                "FROM sessions",
                (ACTIVE, ERROR, INTERRUPTED, time.time() - 86400),
            ).fetchone()
            actors = self._db.execute(
                "SELECT COUNT(DISTINCT actor) AS n FROM sessions"
            ).fetchone()["n"]
        return {
            "service": self.service,
            "version": self.version,
            "host": socket.gethostname(),
            "now": time.time(),
            "started_at": self.started_at,
            "uptime_s": round(self.uptime_s, 3),
            "db_path": str(self.path),
            "db_bytes": self.path.stat().st_size if self.path.exists() else 0,
            "sessions_total": row["total"] or 0,
            "sessions_active": row["active"] or 0,
            "sessions_failed": row["failed"] or 0,
            "sessions_24h": row["last_24h"] or 0,
            "actors": actors or 0,
            "gauges": dict(self._gauges),
            "counters": dict(self._counters),
        }

    def actors(self, *, days: float | None = None) -> list[dict[str, Any]]:
        """Per-caller rollup — the "who has been talking to this" table."""
        totals = [_check_name(t["field"]) for t in self.schema.get("totals", [])]
        sums = "".join(
            f", SUM(COALESCE(json_extract(fields,'$.{f}'),0)) AS {f}" for f in totals
        )
        where, params = self._window(days)
        sql = (
            "SELECT COALESCE(actor,'unknown') AS actor, "
            "MAX(actor_host) AS host, MAX(actor_ip) AS ip, MAX(actor_source) AS source, "
            "MAX(user_agent) AS user_agent, "
            "MIN(started_at) AS first_seen, MAX(started_at) AS last_seen, "
            "COUNT(*) AS sessions, "
            "SUM(CASE WHEN status IN ('error','interrupted') THEN 1 ELSE 0 END) AS errors, "
            "SUM(COALESCE(duration_s,0)) AS duration_s"
            f"{sums} FROM sessions {where} GROUP BY actor ORDER BY last_seen DESC"
        )
        with self._lock:
            rows = [dict(r) for r in self._db.execute(sql, params)]
            by_kind = self._db.execute(
                f"SELECT COALESCE(actor,'unknown') AS actor, kind, COUNT(*) AS n "
                f"FROM sessions {where} GROUP BY actor, kind",
                params,
            ).fetchall()
            last_err = self._db.execute(
                "SELECT COALESCE(actor,'unknown') AS actor, error, MAX(started_at) AS at "
                "FROM sessions WHERE error IS NOT NULL GROUP BY actor"
            ).fetchall()
        kinds: dict[str, dict[str, int]] = {}
        for r in by_kind:
            kinds.setdefault(r["actor"], {})[r["kind"]] = r["n"]
        errors = {r["actor"]: {"error": r["error"], "at": r["at"]} for r in last_err}
        for row in rows:
            row["kinds"] = kinds.get(row["actor"], {})
            row["last_error"] = errors.get(row["actor"])
        return rows

    def sessions(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        kind: str | None = None,
        actor: str | None = None,
        status: str | None = None,
        since: float | None = None,
    ) -> dict[str, Any]:
        clauses, params = [], []
        for col, val in (("kind", kind), ("actor", actor), ("status", status)):
            if val:
                clauses.append(f"{col} = ?")
                params.append(val)
        if since:
            clauses.append("started_at >= ?")
            params.append(since)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            total = self._db.execute(f"SELECT COUNT(*) AS n FROM sessions {where}", params).fetchone()["n"]
            rows = self._db.execute(
                f"SELECT * FROM sessions {where} ORDER BY started_at DESC LIMIT ? OFFSET ?",
                [*params, min(limit, 1000), offset],
            ).fetchall()
        return {"total": total, "rows": [self._row(r) for r in rows]}

    def events(
        self,
        *,
        limit: int = 200,
        since_id: int | None = None,
        level: str | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses, params = [], []
        if since_id is not None:
            clauses.append("id > ?")
            params.append(since_id)
        if level:
            clauses.append("level = ?")
            params.append(level)
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order = "ASC" if since_id is not None else "DESC"
        with self._lock:
            rows = self._db.execute(
                f"SELECT * FROM events {where} ORDER BY id {order} LIMIT ?",
                [*params, min(limit, 1000)],
            ).fetchall()
        return [self._row(r) for r in rows]

    def series(self, *, bucket: str = "hour", days: float = 7.0) -> dict[str, Any]:
        """Time buckets for the charts: sessions and errors per kind."""
        width = 3600 if bucket == "hour" else 86400
        since = time.time() - days * 86400
        totals = [_check_name(t["field"]) for t in self.schema.get("totals", [])]
        sums = "".join(f", SUM(COALESCE(json_extract(fields,'$.{f}'),0)) AS {f}" for f in totals)
        with self._lock:
            rows = self._db.execute(
                "SELECT CAST(started_at / ? AS INTEGER) * ? AS bucket, kind, COUNT(*) AS n, "
                "SUM(CASE WHEN status IN ('error','interrupted') THEN 1 ELSE 0 END) AS errors"
                f"{sums} FROM sessions WHERE started_at >= ? GROUP BY bucket, kind ORDER BY bucket",
                (width, width, since),
            ).fetchall()
        return {"bucket": bucket, "width_s": width, "rows": [dict(r) for r in rows]}

    # -- helpers -----------------------------------------------------------

    def _window(self, days: float | None) -> tuple[str, list[Any]]:
        if not days:
            return "", []
        return "WHERE started_at >= ?", [time.time() - days * 86400]

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        raw = d.pop("fields", "{}")
        try:
            d["fields"] = json.loads(raw)
        except (TypeError, ValueError):
            d["fields"] = {}
        return d


# ------------------------------------------------------------------- config


def config_from_env(service: str, prefix: str | None = None) -> dict[str, Any]:
    """Read the standard knobs. `prefix` defaults to the service name upcased.

    Every service exposes the same four, so knowing one service's environment
    means knowing all of them:

        <PREFIX>_DATA_DIR              /var/lib/<service>
        <PREFIX>_RETENTION_DAYS        0  (keep everything)
        <PREFIX>_CLIENT_NAMES          ip=name,ip=name
        <PREFIX>_RESOLVE_LOCAL_PROCESS 1
    """
    p = (prefix or service).upper().replace("-", "_")
    names = {}
    for pair in os.environ.get(f"{p}_CLIENT_NAMES", "").split(","):
        if "=" in pair:
            ip, _, name = pair.partition("=")
            names[ip.strip()] = name.strip()
    truthy = os.environ.get(f"{p}_RESOLVE_LOCAL_PROCESS", "1").lower() in ("1", "true", "yes")
    try:
        retention = float(os.environ.get(f"{p}_RETENTION_DAYS", "0"))
    except ValueError:
        retention = 0.0
    return {
        "data_dir": os.environ.get(f"{p}_DATA_DIR", f"/var/lib/{service}"),
        "retention_days": retention,
        "resolver": ActorResolver(names, resolve_local_process=truthy),
    }
