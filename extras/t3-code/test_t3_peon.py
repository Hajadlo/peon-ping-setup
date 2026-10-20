"""Main-run routing regressions, using real SQLite reads and stubbed audio."""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

# The watcher reuses the remote extra's gate and worker helpers.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'remote'))

from t3_policy import advance, baseline
from t3_state import snapshot, RunProof
from t3_peon import default_runtime, play
from peon_hook_gate import t3_process
from peon_workers import active_worker_repositories


class MainRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / 'statev2.sqlite'
        self.db = sqlite3.connect(self.database)
        self.addCleanup(self.db.close)
        self.db.executescript('''
            CREATE TABLE orchestration_v2_projection_threads(thread_id,title,payload_json,deleted_at,archived_at);
            CREATE TABLE orchestration_v2_projection_runs(run_id,thread_id,ordinal,status,completed_at,payload_json);
            CREATE TABLE orchestration_v2_projection_messages(message_id,thread_id,role,created_at,payload_json);
            CREATE TABLE orchestration_v2_projection_provider_turns(thread_id,status,run_attempt_id,node_id);
            CREATE TABLE orchestration_v2_projection_runtime_requests(runtime_request_id,thread_id,kind,status);
            CREATE TABLE orchestration_v2_projection_subagents(thread_id,child_thread_id,run_id,status);
        ''')
        self.db.execute('INSERT INTO orchestration_v2_projection_threads VALUES (?,?,?,?,?)',
                        ('main', 'Main title', '{}', None, None))
        self.db.execute('INSERT INTO orchestration_v2_projection_runs VALUES (?,?,?,?,?,?)',
                        ('run', 'main', 1, 'running', None, json.dumps({'activeAttemptId': 'attempt', 'rootNodeId': 'root'})))
        self.db.execute('INSERT INTO orchestration_v2_projection_messages VALUES (?,?,?,?,?)',
                        ('human', 'main', 'user', '2026-10-03T10:00:00Z', '{"createdBy":"user"}'))
        self.db.commit()
        self.now = datetime(2026, 10, 3, 10, 1, tzinfo=timezone.utc).timestamp()

    def finish(self):
        self.db.execute("UPDATE orchestration_v2_projection_runs SET status='completed',completed_at='2026-10-03T10:01:00Z'")
        self.db.commit()

    def test_child_completion_is_silent_and_main_completion_notifies_once(self):
        self.db.execute('INSERT INTO orchestration_v2_projection_threads VALUES (?,?,?,?,?)',
                        ('child', 'Child', '{"lineage":{"relationshipToParent":"subagent"}}', None, None))
        self.db.execute('INSERT INTO orchestration_v2_projection_runs VALUES (?,?,?,?,?,?)',
                        ('child-run', 'child', 1, 'completed', '2026-10-03T10:01:00Z', '{}'))
        self.db.execute('INSERT INTO orchestration_v2_projection_subagents VALUES (?,?,?,?)', ('main', 'child', 'run', 'completed'))
        self.db.commit()
        current, _ = snapshot(self.database)
        self.assertEqual(set(current), {'main'})
        self.assertEqual(current['main'][0], 'working')
        records = baseline(current, self.now)
        sent = []
        proof = RunProof(self.database)
        advance(records, current, self.now + 6, lambda *args: sent.append(args), confirm_completion=proof)
        self.assertEqual(sent, [])
        self.db.execute("DELETE FROM orchestration_v2_projection_runs WHERE thread_id='child'")
        self.finish()
        current, _ = snapshot(self.database)
        for offset in (7, 12, 20):
            advance(records, current, self.now + offset, lambda *args: sent.append(args), confirm_completion=proof)
        self.assertEqual([s[:2] for s in sent], [('completed', 'main')])

    def test_interruption_and_runtime_liveness_do_not_prove_done(self):
        self.db.execute("UPDATE orchestration_v2_projection_runs SET status='interrupted'")
        self.db.commit()
        self.assertEqual(snapshot(self.database)[0]['main'][0], 'idle')
        self.assertFalse(RunProof(self.database)('main', 'run', self.now))
        self.finish()
        self.db.execute("INSERT INTO orchestration_v2_projection_provider_turns VALUES ('main','running','attempt','root')")
        self.db.commit()
        self.assertEqual(snapshot(self.database)[0]['main'][0], 'working')
        self.assertFalse(RunProof(self.database)('main', 'run', self.now))

    def test_background_children_survive_new_main_runs(self):
        # Native task completions wake a new parent run while siblings from the
        # previous run still work. 
        self.db.execute('INSERT INTO orchestration_v2_projection_runs VALUES (?,?,?,?,?,?)',
                        ('older-run', 'main', 0, 'completed', '2026-10-03T10:00:30Z', '{}'))
        self.db.execute('INSERT INTO orchestration_v2_projection_subagents VALUES (?,?,?,?)',
                        ('main', 'background-child', 'older-run', 'running'))
        self.db.execute('INSERT INTO orchestration_v2_projection_messages VALUES (?,?,?,?,?)',
                        ('child-wake', 'main', 'user', '2026-10-03T10:00:50Z', '{"createdBy":"agent"}'))
        self.finish()
        records = baseline({'main': ['working', 'run', 0, 0, '2026-10-03T10:00:00Z']}, self.now)
        sent = []
        for offset in (0, 6):
            advance(records, snapshot(self.database)[0], self.now + offset,
                    lambda *args: sent.append(args), confirm_completion=RunProof(self.database))
        self.assertEqual(sent, [], 'A child wake-up played Done while an older sibling was still running')
        self.assertFalse(RunProof(self.database)('main', 'run', self.now + 6))
        self.assertEqual(snapshot(self.database)[0]['main'][0], 'working')
        self.db.execute("UPDATE orchestration_v2_projection_subagents SET status='completed'")
        self.db.commit()
        for offset in (10, 16, 25):
            advance(records, snapshot(self.database)[0], self.now + offset,
                    lambda *args: sent.append(args), confirm_completion=RunProof(self.database))
        self.assertEqual([s[0] for s in sent], ['completed'])

    def test_requests_deduplicate_and_resolved_requests_stop_alerting(self):
        records = baseline(snapshot(self.database)[0], self.now)
        sent = []
        def tick(offset):
            advance(records, snapshot(self.database)[0], self.now + offset,
                    lambda *args: sent.append(args), confirm_completion=RunProof(self.database))
        self.db.execute("INSERT INTO orchestration_v2_projection_runtime_requests VALUES ('question','main','user_input','pending')")
        self.db.commit()
        tick(0); tick(2)
        self.db.execute("INSERT INTO orchestration_v2_projection_runtime_requests VALUES ('question2','main','user_input','pending')")
        self.db.commit()
        tick(3); tick(8)
        self.assertEqual([s[0] for s in sent], ['input'])
        self.db.execute("UPDATE orchestration_v2_projection_runtime_requests SET status='resolved'")
        self.db.commit()
        tick(9)
        self.db.execute("INSERT INTO orchestration_v2_projection_runtime_requests VALUES ('approval','main','command','pending')")
        self.db.commit()
        tick(10); tick(12)
        self.assertEqual([s[0] for s in sent], ['input', 'approval'])

    def test_system_followups_do_not_reset_human_request(self):
        self.finish()
        self.db.execute('INSERT INTO orchestration_v2_projection_messages VALUES (?,?,?,?,?)',
                        ('child-wake', 'main', 'user', '2026-10-03T10:02:00Z', '{"createdBy":"agent"}'))
        self.db.commit()
        self.assertEqual(snapshot(self.database)[0]['main'][4], '2026-10-03T10:00:00Z')
        self.assertTrue(RunProof(self.database)('main', 'run', self.now + 6))
        self.assertFalse(RunProof(self.database)('main', 'run', self.now + 301))
        self.db.execute('INSERT INTO orchestration_v2_projection_messages VALUES (?,?,?,?,?)',
                        ('new-human', 'main', 'user', '2026-10-03T10:03:00Z', '{"createdBy":"user"}'))
        self.db.commit()
        self.assertEqual(snapshot(self.database)[0]['main'][0], 'working')

    def test_restart_baseline_and_resumed_work_suppress_sounds(self):
        self.finish()
        current, _ = snapshot(self.database)
        records = baseline(current, self.now)
        sent = []
        advance(records, current, self.now + 6, lambda *args: sent.append(args), confirm_completion=RunProof(self.database))
        self.assertEqual(sent, [])
        records = baseline({'main': ['working', 'run', 0, 0, 'request']}, self.now)
        advance(records, current, self.now + 7, lambda *args: sent.append(args), confirm_completion=RunProof(self.database))
        self.db.execute("UPDATE orchestration_v2_projection_runs SET status='running'")
        self.db.commit()
        advance(records, snapshot(self.database)[0], self.now + 10, lambda *args: sent.append(args), confirm_completion=RunProof(self.database))
        self.assertEqual(sent, [])

    def test_verified_sounds_map_to_peon_categories(self):
        with patch('t3_peon.subprocess.run') as run:
            run.return_value.returncode = 0
            for phase, event in (('completed', 'Stop'), ('approval', 'PermissionRequest'), ('input', 'Notification'), ('failed', 'Notification')):
                play(phase, 'main', 'old', 'new', relay_port=19996)
                call = run.call_args.kwargs
                self.assertEqual(json.loads(call['input'])['hook_event_name'], event)
                self.assertEqual(call['env']['PEON_RELAY_PORT'], '19996')
                self.assertEqual(call['env']['PEON_TEST'], '1')

    def test_actual_peon_runtime_reaches_recording_relay_without_audio(self):
        runtime = default_runtime()
        if not runtime.exists():
            self.skipTest('Peon runtime is unavailable (set PEON_RUNTIME)')
        home = Path(self.temp.name) / 'audio-home'
        peon = home / '.claude/hooks/peon-ping'
        pack = peon / 'packs/test/sounds'
        pack.mkdir(parents=True)
        for name in ('done.wav', 'input.wav'):
            (pack / name).write_bytes(b'fixture')
        manifest = {'name': 'test', 'categories': {category: {'sounds': [{'file': 'sounds/' + filename, 'label': category}]}
                    for category, filename in (('task.complete', 'done.wav'), ('input.required', 'input.wav'))}}
        pack.parent.joinpath('openpeon.json').write_text(json.dumps(manifest))
        peon.joinpath('config.json').write_text(json.dumps({'default_pack': 'test', 'enabled': True, 'volume': 0.5,
                'desktop_notifications': False, 'pack_rotation': [], 'debug': True,
                'categories': {'task.complete': True, 'input.required': True}, 'session_start_cooldown_seconds': 0}))
        received = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'OK')
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with patch('t3_peon.Path.home', return_value=home), patch.dict('os.environ', {'HOME': str(home)}):
                for phase in ('completed', 'input', 'approval'):
                    play(phase, phase, 'old', 'new', runtime=runtime, relay_port=server.server_port)
            plays = [url for url in received if url.startswith('/play?')]
            self.assertEqual(len(plays), 3, received)
            self.assertIn('done.wav', plays[0])
            self.assertTrue(all('input.wav' in url for url in plays[1:]))
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

    def test_native_hooks_detect_t3_and_preserve_browser_interview(self):
        proc = Path(self.temp.name) / 'proc/20'
        proc.mkdir(parents=True)
        proc.joinpath('cmdline').write_bytes(b'bun\0/opt/forms/mcp.ts\0')
        proc.joinpath('status').write_text('PPid:\t1\n')
        with patch.dict('os.environ', {'T3CODE_HOME': '/t3', 'PEON_GATE_INPUT_PASSTHROUGH': '/forms/mcp.ts'}):
            self.assertTrue(t3_process(20, proc.parent))
            self.assertFalse(t3_process(20, proc.parent, interview_input=True))
        with patch.dict('os.environ', {}, clear=True):
            self.assertFalse(t3_process(20, proc.parent))

    def test_detached_codex_exec_worker_does_not_play_completion(self):
        proc = Path(self.temp.name) / 'proc/30'
        proc.mkdir(parents=True)
        proc.joinpath('cmdline').write_bytes(b'/usr/bin/codex\0exec\0--json\0')
        proc.joinpath('status').write_text('PPid:\t1\n')
        with patch.dict('os.environ', {}, clear=True):
            self.assertTrue(t3_process(30, proc.parent),
                            'A detached headless worker bypassed the main-thread sound policy')

    def test_detached_worker_keeps_owning_project_busy(self):
        home = Path(self.temp.name)
        repo = home / 'repo'
        git = repo / '.git'
        worker = home / 'worker-wt'
        worker.mkdir()
        (git / 'worktrees/worker').mkdir(parents=True)
        (git / 'worktrees/worker/commondir').write_text('../..\n')
        (worker / '.git').write_text('gitdir: ' + str(git / 'worktrees/worker') + '\n')
        proc = home / 'proc/30'
        proc.mkdir(parents=True)
        proc.joinpath('cmdline').write_bytes(b'/usr/bin/codex\0exec\0--json\0')
        proc.joinpath('cwd').symlink_to(worker)
        self.db.execute('ALTER TABLE orchestration_v2_projection_threads ADD COLUMN project_id')
        self.db.execute('CREATE TABLE projection_projects(project_id,workspace_root)')
        self.db.execute('INSERT INTO projection_projects VALUES (?,?)', ('project', str(repo)))
        self.db.execute("UPDATE orchestration_v2_projection_threads SET project_id='project'")
        self.finish()
        records = baseline({'main': ['working', 'run', 0, 0, '2026-10-03T10:00:00Z']}, self.now)
        sent = []
        with patch('t3_state.WORKER_PROC_ROOT', proc.parent, create=True):
            for offset in (0, 6):
                advance(records, snapshot(self.database)[0], self.now + offset,
                        lambda *args: sent.append(args), confirm_completion=RunProof(self.database))
            self.assertEqual(sent, [], 'The parent notified while a detached worker in its repository was live')
            proc.joinpath('cmdline').unlink()
            for offset in (10, 16):
                advance(records, snapshot(self.database)[0], self.now + offset,
                        lambda *args: sent.append(args), confirm_completion=RunProof(self.database))
            self.assertEqual([s[0] for s in sent], ['completed'])

    def test_provider_background_tasks_keep_parent_busy(self):
        self.db.execute('CREATE TABLE orchestration_v2_projection_provider_threads(thread_id,payload_json)')
        self.db.execute('INSERT INTO orchestration_v2_projection_provider_threads VALUES (?,?)',
                        ('main', '{"pendingBackgroundTasks":[{"taskId":"pending-command","kind":"command"}]}'))
        self.finish()
        self.assertEqual(snapshot(self.database)[0]['main'][0], 'working')
        self.assertFalse(RunProof(self.database)('main', 'run', self.now + 6))

    def test_idle_t3_claude_daemon_is_not_a_detached_worker(self):
        home = Path(self.temp.name)
        repo = home / 'repo'
        (repo / '.git').mkdir(parents=True)
        proc = home / 'proc/30'
        proc.mkdir(parents=True)
        proc.joinpath('cmdline').write_bytes(b'/usr/bin/claude\0--print\0--input-format\0stream-json\0')
        proc.joinpath('status').write_text('PPid:\t40\n')
        proc.joinpath('cwd').symlink_to(repo)
        parent = home / 'proc/40'
        parent.mkdir()
        parent.joinpath('cmdline').write_bytes(b'/usr/bin/t3\0serve\0')
        self.assertEqual(active_worker_repositories(proc.parent), set(),
                         'An idle persistent T3 provider would permanently mute valid completion')


if __name__ == '__main__':
    unittest.main()
