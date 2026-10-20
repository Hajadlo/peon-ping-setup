"""Read T3 v2 main-run notification metadata without reading message text."""
from datetime import datetime
from pathlib import Path
import sqlite3
from peon_workers import active_worker_repositories, git_directory

WORKER_PROC_ROOT = Path('/proc')


def default_database():
    directory = Path.home() / '.t3/userdata'
    return directory / ('statev2.sqlite' if (directory / 'statev2.sqlite').exists() else 'state.sqlite')


def is_v2(connection):
    return connection.execute("SELECT 1 FROM sqlite_master WHERE name='orchestration_v2_projection_runs'").fetchone() is not None


QUERY = """
SELECT t.thread_id, r.run_id, r.status AS run_status, r.completed_at,
       (SELECT MAX(m.created_at) FROM orchestration_v2_projection_messages m
        WHERE m.thread_id=t.thread_id AND m.role='user'
          AND json_extract(m.payload_json, '$.createdBy')='user') AS user_at,
       (SELECT COUNT(*) FROM orchestration_v2_projection_runtime_requests q
        WHERE q.thread_id=t.thread_id AND q.status='pending'
          AND q.kind IN ('command','file-read','file-change','mcp-elicitation','permission')) AS approvals,
       (SELECT COUNT(*) FROM orchestration_v2_projection_runtime_requests q
        WHERE q.thread_id=t.thread_id AND q.status='pending' AND q.kind IN ('user_input','auth_refresh')) AS inputs,
       EXISTS(SELECT 1 FROM orchestration_v2_projection_runs a WHERE a.thread_id=t.thread_id
              AND a.status IN ('preparing','queued','starting','running','waiting')) AS active,
       EXISTS(SELECT 1 FROM orchestration_v2_projection_provider_turns p
              WHERE p.thread_id=t.thread_id
                AND p.run_attempt_id=json_extract(r.payload_json, '$.activeAttemptId')
                AND p.node_id=json_extract(r.payload_json, '$.rootNodeId')
                AND p.status IN ('starting','running','waiting')) AS provider_active,
       -- Native task results wake new parent runs while earlier siblings work.
       -- Outstanding children belong to the entire thread, across parent runs.
       EXISTS(SELECT 1 FROM orchestration_v2_projection_subagents a
              WHERE a.thread_id=t.thread_id
                AND a.status IN ('pending','queued','starting','running','waiting')) AS child_active
FROM orchestration_v2_projection_threads t
LEFT JOIN orchestration_v2_projection_runs r ON r.run_id=(
  SELECT latest.run_id FROM orchestration_v2_projection_runs latest
  WHERE latest.thread_id=t.thread_id ORDER BY latest.ordinal DESC LIMIT 1)
WHERE t.deleted_at IS NULL AND t.archived_at IS NULL
  AND COALESCE(json_extract(t.payload_json, '$.lineage.relationshipToParent'), '') != 'subagent'
  AND NOT EXISTS(SELECT 1 FROM orchestration_v2_projection_subagents child WHERE child.child_thread_id=t.thread_id)
"""


def read_snapshot(connection):
    current = {}
    completions = {}
    background_threads = set()
    tables = {row[0] for row in connection.execute('SELECT name FROM sqlite_master WHERE type=\'table\'')}
    if 'orchestration_v2_projection_provider_threads' in tables:
        background_threads.update(row[0] for row in connection.execute("""
            SELECT thread_id FROM orchestration_v2_projection_provider_threads
            WHERE json_array_length(json_extract(payload_json, '$.pendingBackgroundTasks')) > 0
        """))
    if 'projection_projects' in tables:
        workers = active_worker_repositories(WORKER_PROC_ROOT)
        if workers:
            # Detached systemd jobs have no native T3 parent identity. Keep
            # completion quiet while the same repository still has a CLI worker.
            for row in connection.execute("""
                SELECT t.thread_id, COALESCE(json_extract(t.payload_json, '$.worktreePath'), p.workspace_root) AS workspace
                FROM orchestration_v2_projection_threads t
                LEFT JOIN projection_projects p ON p.project_id=t.project_id
                WHERE t.deleted_at IS NULL AND t.archived_at IS NULL
            """):
                if row['workspace'] and git_directory(row['workspace']) in workers:
                    background_threads.add(row['thread_id'])
    for row in connection.execute(QUERY):
        if row['approvals']:
            phase = 'approval'
        elif row['inputs']:
            phase = 'input'
        elif row['active'] or row['provider_active'] or row['child_active'] or row['thread_id'] in background_threads:
            phase = 'working'
        elif row['run_status'] == 'completed':
            phase = ('working' if row['user_at'] and
                     (not row['completed_at'] or row['user_at'] > row['completed_at']) else 'completed')
        elif row['run_status'] == 'failed':
            phase = 'failed'
        else:
            phase = 'idle'
        current[row['thread_id']] = [phase, row['run_id'], row['approvals'], row['inputs'], row['user_at']]
        if phase == 'completed':
            completions[(row['thread_id'], row['run_id'])] = row['completed_at']
    return current, completions


def snapshot(database):
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True, timeout=2) as connection:
        connection.row_factory = sqlite3.Row
        return read_snapshot(connection)


class RunProof:
    """Recheck durable main-run success, liveness and age at delivery time."""
    def __init__(self, database):
        self.database = database

    def __call__(self, thread, run, now):
        try:
            _, completions = snapshot(self.database)
            completed = completions.get((thread, run))
            return bool(completed and 0 <= now - datetime.fromisoformat(completed.replace('Z', '+00:00')).timestamp() <= 300)
        except (sqlite3.Error, OSError, ValueError, TypeError):
            return False
