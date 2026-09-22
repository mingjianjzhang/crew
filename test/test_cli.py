"""CLI integration checks: isolated fake herdr, real Git and real Bash scripts."""
import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

SOURCE = Path(__file__).resolve().parents[1]

class CrewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='crew-test-')
        self.root = Path(self.tmp.name).resolve()
        self.crew = self.root / 'crew home'
        shutil.copytree(SOURCE, self.crew, ignore=shutil.ignore_patterns('.git', 'state', 'data', '__pycache__'))
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir()
        self.fakebin = self.root / 'fakebin'
        self.fakebin.mkdir()
        if os.environ.get('CREW_TEST_BASH'):
            (self.fakebin / 'bash').symlink_to(os.environ['CREW_TEST_BASH'])
        shutil.copy(SOURCE / 'test/fake-herdr.py', self.fakebin / 'herdr')
        (self.fakebin / 'herdr').chmod(0o755)
        for kind in ['claude', 'grok', 'codex', 'pi']:
            p = self.fakebin / kind
            p.write_text('#!/bin/sh\nexit 0\n')
            p.chmod(0o755)
        p = self.fakebin / 'gh'
        p.write_text('#!/bin/sh\nprintf "%s\\n" "${CREW_TEST_PRS:-[]} "\n')
        p.chmod(0o755)
        self.env = dict(os.environ, PATH=f'{self.fakebin}:{os.environ["PATH"]}', HERDR_ENV='1',
                        CREW_TEST_RUNTIME=str(self.runtime), GIT_CONFIG_NOSYSTEM='1',
                        GIT_CONFIG_GLOBAL='/dev/null', GIT_AUTHOR_NAME='Crew Test',
                        GIT_AUTHOR_EMAIL='test@example.invalid', GIT_COMMITTER_NAME='Crew Test',
                        GIT_COMMITTER_EMAIL='test@example.invalid')
        self.origin = self.root / 'origin.git'
        self.project = self.root / 'project with spaces'
        self.git('init', '--bare', '--initial-branch=main', str(self.origin))
        self.git('clone', str(self.origin), str(self.project))
        (self.project / 'hello.txt').write_text('original\n')
        self.git('-C', str(self.project), 'add', '.')
        self.git('-C', str(self.project), 'commit', '-m', 'Initial')
        self.git('-C', str(self.project), 'push', '-u', 'origin', 'main')
        self.brief = self.root / 'brief.md'
        self.brief.write_text('Investigate hello.txt. Write .crew/report.md. Do not edit project files.\n')

    def tearDown(self):
        self.tmp.cleanup()

    def run_cmd(self, cmd, *, ok=True, env=None):
        result = subprocess.run(cmd, env=env or self.env, cwd=self.crew, text=True, capture_output=True, timeout=30)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def git(self, *args, **kwargs):
        return self.run_cmd(['git', *args], **kwargs).stdout.strip()

    def cli(self, name, *args, **kwargs):
        return self.run_cmd([str(self.crew / 'bin' / name), *args], **kwargs)

    def spawn(self, ident='one', kind='scout', **kwargs):
        return self.cli('spawn', '--id', ident, '--project', str(self.project), '--kind', kind,
                        '--agent', 'claude', '--brief', str(self.brief), **kwargs)

    def meta(self, ident='one'):
        return json.loads((self.crew / 'state' / f'{ident}.meta').read_text())

    def worktree(self, ident='one'):
        return Path(self.meta(ident)['worktree'])

    def agent(self, state, ident='one'):
        path = self.runtime / f'crew-{ident}.json'
        data = json.loads(path.read_text())
        data['state'] = state
        path.write_text(json.dumps(data))

    def event(self, verb, note, ident='one', **kwargs):
        return self.run_cmd([str(self.worktree(ident) / '.crew/crew-status'), verb, note], **kwargs)

    def usage(self, ident='one', **kwargs):
        wt = self.worktree(ident)
        meta = self.meta(ident)
        cmd = [str(wt / '.crew/crew-usage'),
               '--input', str(kwargs.get('input', 100)),
               '--output', str(kwargs.get('output', 20)),
               '--cached-read', str(kwargs.get('cached_read', 50)),
               '--source', kwargs.get('source', 'harness'),
               '--task-id', ident,
               '--kind', meta['kind'],
               '--harness', meta.get('harness') or 'claude',
               '--model', meta.get('model') or 'test-model']
        if 'pr_url' in kwargs:
            cmd.extend(['--pr-url', kwargs['pr_url']])
        if 'pr_number' in kwargs:
            cmd.extend(['--pr-number', str(kwargs['pr_number'])])
        if 'cost_usd' in kwargs:
            cmd.extend(['--cost-usd', str(kwargs['cost_usd'])])
        return self.run_cmd(cmd)

    def report(self, ident='one'):
        (self.worktree(ident) / '.crew/report.md').write_text('Findings.\n')
        self.usage(ident)
        self.event('done', '.crew/report.md', ident)
        self.agent('done', ident)

    def calls(self):
        return [json.loads(line) for line in (self.runtime / 'calls.jsonl').read_text().splitlines()]

    def test_outside_herdr_refuses_all_scripts(self):
        env = dict(self.env, HERDR_ENV='0')
        for name, args in [
            ('spawn', []),
            ('status', []),
            ('answer', ['one', 'key', 'text']),
            ('finish', ['one', 'done note']),
            ('teardown', ['one']),
            ('share-retire', ['demo-board']),
        ]:
            result = self.cli(name, *args, ok=False, env=env)
            self.assertIn('herdr-managed pane', result.stderr)
        self.assertFalse((self.runtime / 'calls.jsonl').exists())

    def test_share_retire_archives_manifest_paths(self):
        share = self.crew / 'state/share/demo-board'
        playtest = self.crew / 'state/playtest/demo-board'
        (share / 'updates').mkdir(parents=True)
        (share / 'pack' / 'study' / 'frames').mkdir(parents=True)
        (share / 'README.md').write_text('# board\n')
        (share / 'updates' / 'old.md').write_text('landed\n')
        (share / 'pack' / 'study' / 'frames' / 'a.png').write_text('png\n')
        (share / 'pack' / 'owner-freeze.md').write_text('keep\n')
        playtest.mkdir(parents=True)
        (playtest / 'keep.txt').write_text('playtest\n')

        init = self.cli('share-retire', 'demo-board', '--init')
        self.assertIn('RETIRE.manifest', init.stdout)
        manifest = share / 'RETIRE.manifest'
        self.assertTrue(manifest.is_file())
        self.assertTrue((share / 'CURRENT.md').is_file())
        # Keep only heavy disposables; leave owner freeze on the board.
        manifest.write_text('updates/\npack/study/\n')

        dry = self.cli('share-retire', 'demo-board', '--dry-run')
        self.assertIn('move updates', dry.stdout)
        self.assertTrue((share / 'updates' / 'old.md').is_file())

        self.cli('share-retire', 'demo-board')
        self.assertFalse((share / 'updates').exists())
        self.assertFalse((share / 'pack' / 'study').exists())
        self.assertTrue((share / 'pack' / 'owner-freeze.md').is_file())
        self.assertTrue((share / 'README.md').is_file())
        self.assertEqual((playtest / 'keep.txt').read_text(), 'playtest\n')
        archives = list((self.crew / 'data/share-retired/demo-board').iterdir())
        self.assertEqual(len(archives), 1)
        arch = archives[0]
        self.assertTrue((arch / 'updates' / 'old.md').is_file())
        self.assertTrue((arch / 'pack' / 'study' / 'frames' / 'a.png').is_file())
        self.assertTrue((share / 'RETIRED.md').is_file())

        # Live task on the same share must block a later retire.
        self.cli('spawn', '--id', 'held', '--project', str(self.project), '--kind', 'scout',
                 '--agent', 'claude', '--brief', str(self.brief), '--share', 'demo-board')
        blocked = self.cli('share-retire', 'demo-board', ok=False)
        self.assertIn('still referenced by live task held', blocked.stderr)

    def test_spawn_is_fresh_isolated_and_returns_without_wait(self):
        (self.project / 'hello.txt').write_text('dirty human work\n')
        self.spawn()
        meta = self.meta()
        self.assertEqual(meta['phase'], 'dispatched')
        self.assertEqual(meta['port_base'], 5100)
        self.assertEqual(meta['workspace'], 'opaque-crew-one')
        self.assertEqual(meta['base'], 'origin/main')
        self.assertEqual(meta['pr_base'], 'main')
        self.assertIsNone(meta.get('share'))
        self.assertFalse((self.worktree() / '.crew/share').exists())
        self.assertEqual((self.worktree() / 'hello.txt').read_text(), 'original\n')
        self.assertEqual((self.project / 'hello.txt').read_text(), 'dirty human work\n')
        self.assertEqual(self.git('-C', str(self.worktree()), 'status', '--porcelain'), '')
        agent = json.loads((self.runtime / 'crew-one.json').read_text())
        self.assertIn('PORT=5100', agent['shell_command'])
        self.assertIn('CHROME_DEVTOOLS_AXI_SESSION=one', agent['shell_command'])
        env = (self.worktree() / '.crew/env').read_text()
        self.assertIn('export PORT=5100', env)
        self.assertIn('export CHROME_DEVTOOLS_AXI_SESSION=one', env)
        self.assertNotIn('PLAYTEST_DIR', env)
        self.assertNotIn('PLAYTEST_DIR', agent['shell_command'])
        self.assertEqual(len(agent['prompts']), 1)
        self.cli('spawn', '--resume', 'one')
        self.assertEqual(len(json.loads((self.runtime / 'crew-one.json').read_text())['prompts']), 1)
        for call in self.calls():
            self.assertNotIn('--wait', call)
            self.assertNotIn('wait', call)
            self.assertNotIn('focus', call)

    def test_spawn_base_stacks_onto_feature_branch(self):
        self.git('-C', str(self.project), 'checkout', '-b', 'crew/ipf')
        (self.project / 'feature.txt').write_text('integration\n')
        self.git('-C', str(self.project), 'add', '.')
        self.git('-C', str(self.project), 'commit', '-m', 'Integration base')
        self.git('-C', str(self.project), 'push', '-u', 'origin', 'crew/ipf')
        self.git('-C', str(self.project), 'checkout', 'main')
        self.cli('spawn', '--id', 'stacked', '--project', str(self.project), '--kind', 'scout',
                 '--agent', 'claude', '--brief', str(self.brief), '--base', 'crew/ipf')
        meta = self.meta('stacked')
        self.assertEqual(meta['base'], 'origin/crew/ipf')
        self.assertEqual(meta['pr_base'], 'crew/ipf')
        self.assertEqual(meta['share'], 'crew-ipf')
        playtest_dir = self.crew / 'state/playtest/crew-ipf'
        self.assertTrue(playtest_dir.is_dir())
        env = (self.worktree('stacked') / '.crew/env').read_text()
        playtest_shell_path = str(playtest_dir).replace(' ', '\\ ')
        self.assertIn(f'export PLAYTEST_DIR={playtest_shell_path}', env)
        agent = json.loads((self.runtime / 'crew-stacked.json').read_text())
        self.assertIn(f'PLAYTEST_DIR={playtest_shell_path}', agent['shell_command'])
        brief = (self.crew / 'state/stacked.brief.md').read_text()
        self.assertIn(f'PLAYTEST_DIR={playtest_dir}', brief)
        create = next(c for c in self.calls() if c[:2] == ['worktree', 'create'])
        self.assertEqual(create[create.index('--base') + 1], 'origin/crew/ipf')
        brief = (self.crew / 'state/stacked.brief.md').read_text()
        self.assertIn('Open the GitHub PR against `crew/ipf`', brief)
        self.assertIn('not `main`', brief)
        self.assertIn('Shared board', brief)
        self.assertTrue((self.worktree('stacked') / 'feature.txt').exists())
        share_link = self.worktree('stacked') / '.crew/share'
        self.assertTrue(share_link.is_symlink())
        self.assertEqual(share_link.resolve(), (self.crew / 'state/share/crew-ipf').resolve())
        self.assertTrue((self.crew / 'state/share/crew-ipf/README.md').is_file())
        self.assertTrue((self.crew / 'state/share/crew-ipf/updates').is_dir())
        note = self.crew / 'state/share/crew-ipf/updates/hello.md'
        note.write_text('from stacked\n')
        self.assertEqual((share_link / 'updates/hello.md').read_text(), 'from stacked\n')
        self.cli('spawn', '--resume', 'stacked', '--base', 'main', ok=False)

    def test_share_explicit_and_none(self):
        self.git('-C', str(self.project), 'checkout', '-b', 'crew/ipf')
        self.git('-C', str(self.project), 'commit', '--allow-empty', '-m', 'Integration')
        self.git('-C', str(self.project), 'push', '-u', 'origin', 'crew/ipf')
        self.git('-C', str(self.project), 'checkout', '-b', 'crew/ipf-pr1')
        self.git('-C', str(self.project), 'commit', '--allow-empty', '-m', 'PR head')
        self.git('-C', str(self.project), 'push', '-u', 'origin', 'crew/ipf-pr1')
        self.git('-C', str(self.project), 'checkout', 'main')
        self.cli('spawn', '--id', 'fix', '--project', str(self.project), '--kind', 'scout',
                 '--agent', 'claude', '--brief', str(self.brief),
                 '--base', 'crew/ipf-pr1', '--share', 'crew-ipf')
        self.assertEqual(self.meta('fix')['share'], 'crew-ipf')
        self.assertEqual((self.worktree('fix') / '.crew/share').resolve(),
                         (self.crew / 'state/share/crew-ipf').resolve())
        self.cli('spawn', '--id', 'solo', '--project', str(self.project), '--kind', 'scout',
                 '--agent', 'claude', '--brief', str(self.brief),
                 '--base', 'crew/ipf', '--share', 'none')
        self.assertIsNone(self.meta('solo')['share'])
        self.assertFalse((self.worktree('solo') / '.crew/share').exists())
        self.assertNotIn('PLAYTEST_DIR', (self.worktree('solo') / '.crew/env').read_text())
        self.assertNotIn('PLAYTEST_DIR', json.loads((self.runtime / 'crew-solo.json').read_text())['shell_command'])

    def test_release_resources_stops_axi_and_frees_ports(self):
        axi_log = self.root / 'axi-stop.log'
        axi = self.fakebin / 'chrome-devtools-axi'
        axi.write_text(
            '#!/bin/sh\n'
            'echo "session=${CHROME_DEVTOOLS_AXI_SESSION-} args=$*" >> "$CREW_TEST_AXI_LOG"\n'
            'exit 0\n'
        )
        axi.chmod(0o755)
        env = dict(self.env, CREW_TEST_AXI_LOG=str(axi_log))
        server = subprocess.Popen(
            ['python3', '-m', 'http.server', '5197', '--bind', '127.0.0.1'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        self.addCleanup(server.kill)
        for _ in range(50):
            listening = subprocess.run(
                ['lsof', '-nP', '-iTCP:5197', '-sTCP:LISTEN', '-t'],
                capture_output=True, text=True)
            if listening.returncode == 0 and listening.stdout.strip():
                break
            time.sleep(0.05)
        else:
            self.fail('test server did not listen on 5197')
        out = subprocess.check_output(
            ['bash', str(self.crew / 'lib/release-resources.sh'),
             '--id', 'cleanup', '--port-base', '5190', '--worktree', str(self.project)],
            text=True, env=env)
        self.assertIn('session=cleanup', out)
        self.assertIn('axi_stop=1', out)
        self.assertIn('session=cleanup args=stop', axi_log.read_text())
        listening = subprocess.run(
            ['lsof', '-nP', '-iTCP:5197', '-sTCP:LISTEN', '-t'],
            capture_output=True, text=True)
        self.assertNotEqual(listening.returncode, 0, listening.stdout)
        server.wait(timeout=2)

    def test_parallel_allocations_are_distinct_or_busy(self):
        def launch(ident):
            return subprocess.run([str(self.crew / 'bin/spawn'), '--id', ident, '--project', str(self.project),
                '--kind', 'scout', '--agent', 'claude', '--brief', str(self.brief)],
                env=self.env, cwd=self.crew, text=True, capture_output=True, timeout=30)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(launch, ['one', 'two']))
        for ident, result in zip(['one', 'two'], outcomes):
            if result.returncode:
                # Git fetch may also reject concurrent updates. Both failures are retryable.
                if (self.crew / 'state' / f'{ident}.meta').exists():
                    self.cli('spawn', '--resume', ident)
                else:
                    self.spawn(ident)
        self.assertEqual({self.meta('one')['port_base'], self.meta('two')['port_base']}, {5100, 5110})

    def test_allocation_lock_refuses_without_orphan(self):
        lock = self.crew / 'state/.allocation.lock'
        lock.mkdir(parents=True)
        result = self.spawn(ok=False)
        self.assertIn('Busy', result.stderr)
        self.assertFalse((self.crew / 'state/one.meta').exists())
        self.assertFalse(any(c[:2] == ['worktree', 'create'] for c in self.calls()))

    def test_failed_creation_keeps_reservation_and_resumes(self):
        self.spawn(ok=False, env=dict(self.env, CREW_TEST_CREATE_FAIL='1'))
        self.assertEqual(self.meta()['phase'], 'creating')
        self.spawn('two')
        self.assertEqual(self.meta('two')['port_base'], 5110)
        self.cli('spawn', '--resume', 'one')
        self.assertEqual(self.meta()['phase'], 'dispatched')

    def test_lost_creation_response_recovers_existing_worktree(self):
        self.spawn(ok=False, env=dict(self.env, CREW_TEST_CREATE_CRASH='1'))
        self.assertTrue(self.worktree().is_dir())
        self.cli('spawn', '--resume', 'one')
        self.assertEqual(self.meta()['phase'], 'dispatched')
        self.assertEqual(sum(c[:2] == ['worktree', 'create'] for c in self.calls()), 1)

    def test_blocked_start_resumes_without_starting_twice(self):
        self.spawn(ok=False, env=dict(self.env, CREW_TEST_START_BLOCKED='1'))
        self.assertEqual(self.meta()['phase'], 'starting')
        self.agent('idle')
        self.cli('spawn', '--resume', 'one')
        self.assertEqual(sum(c[:2] == ['agent', 'start'] for c in self.calls()), 1)

    def test_uncertain_prompt_never_automatically_repeats(self):
        self.spawn(ok=False, env=dict(self.env, CREW_TEST_PROMPT_FAIL='1'))
        result = self.cli('spawn', '--resume', 'one', ok=False)
        self.assertIn('uncertain', result.stderr)
        self.assertEqual(sum(c[:2] == ['agent', 'prompt'] for c in self.calls()), 1)

    def test_pending_answer_then_manual_delivery(self):
        self.spawn()
        self.event('needs-decision', 'color Which color?')
        self.cli('answer', 'one', 'color', 'Blue $(touch /tmp/crew-should-not-execute)')
        self.assertEqual(sum(c[:2] == ['agent', 'prompt'] for c in self.calls()), 1)
        self.assertIn('answer pending: color pending', self.cli('status').stdout)
        self.agent('done')
        self.cli('answer', 'one', 'color', '--deliver')
        self.assertEqual(sum(c[:2] == ['agent', 'prompt'] for c in self.calls()), 2)
        self.assertNotIn('answer pending:', self.cli('status').stdout)
        self.cli('answer', 'one', '../unsafe', 'no', ok=False)
        self.cli('answer', 'one', 'missing', 'no', ok=False)

    def test_answer_refuses_done_only_closeout(self):
        """Farewell-shaped answers must not wake the agent; use bin/finish."""
        self.spawn()
        self.event('needs-decision', 'pr-review Ready for review')
        self.agent('idle')
        before = sum(c[:2] == ['agent', 'prompt'] for c in self.calls())
        result = self.cli(
            'answer', 'one', 'pr-review',
            'Merged. Emit done and refresh usage.',
            ok=False,
        )
        self.assertIn('done-only closeout', result.stderr)
        self.assertIn('bin/finish', result.stderr)
        self.assertEqual(sum(c[:2] == ['agent', 'prompt'] for c in self.calls()), before)
        self.assertFalse((self.worktree() / '.crew/answers/pr-review.md').exists())
        # Explicit continue reason is allowed (worker must keep going).
        self.cli(
            'answer', 'one', 'pr-review',
            'CI failed after merge attempt; fix the INV assertion and update the PR.',
        )
        self.assertEqual(sum(c[:2] == ['agent', 'prompt'] for c in self.calls()), before + 1)

    def test_answer_force_allows_done_only_looking_note(self):
        self.spawn()
        self.event('needs-decision', 'pr-review Ready for review')
        self.agent('idle')
        before = sum(c[:2] == ['agent', 'prompt'] for c in self.calls())
        result = self.cli(
            'answer', '--force', 'one', 'pr-review',
            'Merged. Emit done and refresh usage.',
        )
        self.assertIn('warning', result.stderr.lower())
        self.assertEqual(sum(c[:2] == ['agent', 'prompt'] for c in self.calls()), before + 1)
        self.assertTrue((self.worktree() / '.crew/answers/pr-review.md').exists())

    def test_status_unread_ack_and_missing_agent(self):
        self.spawn()
        self.report()
        self.assertIn('unread: done', self.cli('status').stdout)
        self.assertIn('unread: done', self.cli('status', '--ack').stdout)
        self.assertNotIn('unread:', self.cli('status').stdout)
        self.agent('gone')
        result = self.cli('status').stdout
        self.assertIn('done', result)
        self.assertIn('gone', result)

    def test_scout_teardown_checks_then_archives(self):
        self.cli('spawn', '--id', 'one', '--project', str(self.project), '--kind', 'scout',
                 '--agent', 'claude', '--brief', str(self.brief), '--share', 'retained')
        marker = self.crew / 'state/playtest/retained/marker.txt'
        marker.write_text('keep packet evidence')
        self.cli('teardown', 'one', ok=False)  # live worker
        self.agent('done')
        self.cli('teardown', 'one', ok=False)  # no report / no usage
        self.report()
        (self.worktree() / 'dirty.txt').write_text('keep me')
        self.cli('teardown', 'one', ok=False)
        (self.worktree() / 'dirty.txt').unlink()
        self.cli('teardown', 'one')
        self.assertTrue((self.crew / 'data/one/report.md').exists())
        self.assertTrue((self.crew / 'data/one/usage.json').exists())
        self.assertTrue((self.crew / 'state/usage/one.json').exists())
        self.assertTrue((self.crew / 'state/usage.jsonl').exists())
        self.assertFalse((self.crew / 'state/one.meta').exists())
        self.assertFalse((self.crew / 'state/worktrees/one').exists())
        self.assertEqual(marker.read_text(), 'keep packet evidence')
        self.spawn(ok=False)  # archived ids cannot be reused

    def test_finish_closes_without_agent_prompt(self):
        """Merge/done-only closeout must not herdr agent prompt (token burn)."""
        self.cli('spawn', '--id', 'one', '--project', str(self.project), '--kind', 'scout',
                 '--agent', 'claude', '--brief', str(self.brief))
        self.event('needs-decision', 'design-review Pick a direction')
        self.agent('idle')
        (self.worktree() / '.crew/report.md').write_text('Findings.\n')
        self.usage()
        before = sum(c[:2] == ['agent', 'prompt'] for c in self.calls())
        self.cli('finish', 'one', '--decision', 'design-review',
                 'Owner approved; primary finish; no agent turn.')
        after = sum(c[:2] == ['agent', 'prompt'] for c in self.calls())
        self.assertEqual(after, before)
        self.assertTrue((self.crew / 'data/one/usage.json').exists())
        self.assertTrue((self.crew / 'data/one/answers/design-review.md').exists())
        self.assertFalse((self.crew / 'state/one.meta').exists())
        archive_status = (self.crew / 'data/one/status').read_text()
        self.assertIn('resolved: design-review primary-finish', archive_status)
        self.assertIn('done: Owner approved; primary finish', archive_status)

    def test_teardown_requires_usage_even_with_discard(self):
        self.spawn()
        self.agent('done')
        (self.worktree() / '.crew/report.md').write_text('Findings.\n')
        self.event('done', '.crew/report.md')
        result = self.cli('teardown', 'one', '--discard', ok=False)
        self.assertIn('usage', result.stderr.lower())
        self.usage(pr_url='https://example.com/pull/1', pr_number=1, cost_usd=0.5)
        self.cli('teardown', 'one', '--discard')
        self.assertTrue((self.crew / 'data/one/usage.json').exists())

    def test_crew_usage_claude_auto_prices_transcript(self):
        """--auto dedups Claude JSONL usage and prices costUsd from list rates."""
        self.spawn()
        wt = self.worktree()
        transcript = wt / 'session.jsonl'
        # Duplicate msg_1 exercises unique_by(.id); haiku id exercises dated alias match.
        transcript.write_text(
            json.dumps({
                'message': {
                    'model': 'claude-sonnet-5',
                    'id': 'msg_1',
                    'usage': {
                        'input_tokens': 2,
                        'output_tokens': 4,
                        'cache_read_input_tokens': 18531,
                        'cache_creation_input_tokens': 14204,
                        'cache_creation': {
                            'ephemeral_1h_input_tokens': 14204,
                            'ephemeral_5m_input_tokens': 0,
                        },
                    },
                }
            }) + '\n'
            + json.dumps({
                'message': {
                    'model': 'claude-sonnet-5',
                    'id': 'msg_1',
                    'usage': {
                        'input_tokens': 2,
                        'output_tokens': 4,
                        'cache_read_input_tokens': 18531,
                        'cache_creation_input_tokens': 14204,
                        'cache_creation': {
                            'ephemeral_1h_input_tokens': 14204,
                            'ephemeral_5m_input_tokens': 0,
                        },
                    },
                }
            }) + '\n'
            + json.dumps({
                'message': {
                    'model': 'claude-haiku-4-5-20251001',
                    'id': 'msg_2',
                    'usage': {
                        'input_tokens': 898,
                        'output_tokens': 14,
                        'cache_read_input_tokens': 0,
                        'cache_creation_input_tokens': 0,
                        'cache_creation': {
                            'ephemeral_1h_input_tokens': 0,
                            'ephemeral_5m_input_tokens': 0,
                        },
                    },
                }
            }) + '\n'
        )
        result = self.run_cmd([
            str(wt / '.crew/crew-usage'),
            '--transcript', str(transcript),
            '--source', 'harness',
        ])
        self.assertIn('Wrote', result.stdout)
        usage = json.loads((wt / '.crew/usage.json').read_text())
        self.assertEqual(usage['tokens']['input'], 900)
        self.assertEqual(usage['tokens']['output'], 18)
        self.assertEqual(usage['tokens']['cachedRead'], 18531)
        self.assertEqual(usage['tokens']['cacheCreation'], 14204)
        self.assertEqual(usage['tokens']['reasoning'], 0)
        # Scout-validated: sonnet probe 0.0605662 + haiku 0.000968.
        self.assertAlmostEqual(usage['costUsd'], 0.0615342, places=7)
        self.assertEqual(usage['source'], 'harness')
        self.assertEqual(usage['harness'], 'claude')

    def test_ship_landing_and_local_tip_guard(self):
        self.spawn(kind='ship')
        wt = self.worktree()
        (wt / 'hello.txt').write_text('changed\n')
        self.git('-C', str(wt), 'commit', '-am', 'Change')
        self.usage(pr_url='https://example.com/pull/9', pr_number=9)
        self.agent('done')
        self.cli('teardown', 'one', ok=False)
        tip = self.git('-C', str(wt), 'rev-parse', 'HEAD')
        stale = json.dumps([{'state': 'MERGED', 'headRefOid': 'bad', 'isCrossRepository': False}])
        self.cli('teardown', 'one', ok=False, env=dict(self.env, CREW_TEST_PRS=stale))
        merged = json.dumps([{'state': 'MERGED', 'headRefOid': tip, 'isCrossRepository': False}])
        self.cli('teardown', 'one', env=dict(self.env, CREW_TEST_PRS=merged))
        self.assertFalse(wt.exists())

    def test_changed_workspace_identity_refuses_removal(self):
        self.spawn()
        self.report()
        self.cli('teardown', 'one', '--discard', ok=False, env=dict(self.env, CREW_TEST_WRONG_WORKSPACE='1'))
        self.assertTrue(self.worktree().exists())

    def test_invalid_integration_and_event_refused(self):
        self.spawn(ok=False, env=dict(self.env, CREW_TEST_OUTDATED='1'))
        self.assertFalse((self.crew / 'state/one.meta').exists())
        self.spawn()
        self.event('done', 'first\nsecond', ok=False)
        self.event('invented', 'no', ok=False)
        self.event('needs-decision', '../unsafe question', ok=False)


    def test_scout_decisions_prevent_teardown(self):
        self.spawn()
        self.report()
        self.event('needs-decision', 'scope Is this sufficient?')
        self.cli('teardown', 'one', ok=False)
        self.agent('working')
        self.cli('answer', 'one', 'scope', 'Yes')
        self.agent('done')
        self.cli('teardown', 'one', ok=False)

    def test_teardown_retry_rechecks_dirty_files(self):
        self.spawn()
        self.report()
        self.cli('teardown', 'one', ok=False, env=dict(self.env, CREW_TEST_REMOVE_FAIL='1'))
        self.assertEqual(self.meta()['phase'], 'removing')
        (self.worktree() / 'new-work.txt').write_text('do not lose this')
        self.cli('teardown', 'one', ok=False)
        (self.worktree() / 'new-work.txt').unlink()
        self.cli('teardown', 'one')

    def test_failed_reservation_discard_releases_port(self):
        self.spawn(ok=False, env=dict(self.env, CREW_TEST_CREATE_FAIL='1'))
        self.cli('teardown', 'one', ok=False)
        # Incomplete reservation (no checkout) may discard without usage.
        self.cli('teardown', 'one', '--discard')
        self.spawn('two')
        self.assertEqual(self.meta('two')['port_base'], 5100)

    def test_bypass_requires_explicit_flag(self):
        args = ['--id', 'pi-test', '--project', str(self.project), '--kind', 'scout',
                '--agent', 'pi', '--brief', str(self.brief)]
        self.cli('spawn', *args, ok=False)
        self.cli('spawn', *args, '--unattended-bypass')
        start = next(c for c in self.calls() if c[:2] == ['agent', 'start'])
        self.assertEqual(start[-1], '--')  # no empty string passed as a CLI argument

    def test_identical_ship_tree_can_land_without_pr(self):
        self.spawn(kind='ship')
        self.usage()
        self.agent('done')
        self.cli('teardown', 'one')

    def test_unknown_live_state_never_allows_teardown(self):
        self.spawn()
        self.report()
        self.cli('teardown', 'one', ok=False, env=dict(self.env, CREW_TEST_SERVER_DOWN='1'))
        self.assertTrue(self.worktree().exists())


    def profile_spawn(self, ident, *options, **kwargs):
        # OpenAI profiles use Pi (bypass). Passing the flag is harmless for Claude.
        return self.cli('spawn', '--id', ident, '--project', str(self.project), '--kind', 'ship',
                        '--brief', str(self.brief), '--unattended-bypass', *options, **kwargs)

    def start_args(self, ident):
        call = next(c for c in self.calls() if c[:3] == ['agent', 'start', f'crew-{ident}'])
        return call, call[call.index('--') + 1:]

    def test_worker_profile_models_and_effort(self):
        cases = [('implicit', [], 'default', 'pi', 'openai-codex/gpt-5.6-luna', 'high'),
                 ('explicit', ['--profile', 'default'], 'default', 'pi', 'openai-codex/gpt-5.6-luna', 'high'),
                 ('planning', ['--profile', 'planning'], 'planning', 'pi', 'openai-codex/gpt-6-astra', 'high'),
                 ('routine', ['--profile', 'routine'], 'routine', 'pi', 'openai-codex/gpt-5.6-luna', 'high'),
                 ('mechanics', ['--profile', 'mechanics'], 'mechanics', 'pi', 'openai-codex/gpt-5.6-sol', 'xhigh'),
                 ('new-feature', ['--profile', 'new-feature'], 'new-feature', 'claude', 'claude-sonnet-5', None)]
        for ident, options, profile, harness, model, effort in cases:
            with self.subTest(profile=ident):
                self.profile_spawn(ident, *options)
                meta = self.meta(ident)
                self.assertEqual((meta['profile'], meta['harness'], meta['model'], meta['effort']),
                                 (profile, harness, model, effort))
                call, args = self.start_args(ident)
                self.assertEqual(call[call.index('--kind') + 1], harness)
                self.assertEqual(args[args.index('--model') + 1], model)
                if effort:
                    self.assertEqual(args[args.index('--thinking') + 1], effort)
                else:
                    self.assertNotIn('--thinking', args)
                    self.assertNotIn('--effort', args)

    def test_profile_overrides_and_native_harness_route(self):
        self.profile_spawn('override', '--profile', 'planning', '--model', 'gpt-5.6-luna', '--effort', 'xhigh')
        self.assertEqual(self.meta('override')['effort'], 'xhigh')
        override_args = self.start_args('override')[1]
        self.assertEqual(override_args[override_args.index('--thinking') + 1], 'xhigh')
        self.profile_spawn('native-effort', '--effort', 'default')
        self.assertIsNone(self.meta('native-effort')['effort'])
        self.assertNotIn('--thinking', self.start_args('native-effort')[1])
        self.profile_spawn('custom', '--agent', 'claude', '--model', 'claude-sonnet-5', '--effort', 'high')
        args = self.start_args('custom')[1]
        self.assertEqual(args[args.index('--effort')+1], 'high')
        self.profile_spawn('native', '--agent', 'claude')
        self.assertIsNone(self.meta('native')['model'])
        self.assertNotIn('--model', self.start_args('native')[1])

    def test_profile_conflicts_fail_before_creation(self):
        for options in [('--profile', 'unknown'), ('--profile', 'planning', '--agent', 'claude')]:
            self.profile_spawn('invalid', *options, ok=False)
        self.assertFalse((self.crew / 'state/invalid.meta').exists())
        self.assertFalse((self.runtime / 'calls.jsonl').exists())

    def test_openai_profiles_require_unattended_bypass(self):
        result = self.cli('spawn', '--id', 'need-bypass', '--project', str(self.project),
                          '--kind', 'scout', '--profile', 'routine', '--brief', str(self.brief), ok=False)
        self.assertIn('unattended-bypass', result.stderr)
        self.assertFalse((self.crew / 'state/need-bypass.meta').exists())

    def test_resume_preserves_model_even_after_defaults_change(self):
        self.profile_spawn('saved', '--profile', 'planning', ok=False,
                           env=dict(self.env, CREW_TEST_CREATE_FAIL='1'))
        p = self.crew / 'profiles.tsv'
        p.write_text(p.read_text().replace('gpt-6-astra', 'changed-default'))
        self.cli('spawn', '--resume', 'saved')
        self.assertIn('openai-codex/gpt-6-astra', self.start_args('saved')[1])
        self.cli('spawn', '--resume', 'saved', '--model', 'different', ok=False)

    def test_legacy_task_resume_keeps_original_arguments(self):
        self.spawn(ok=False, env=dict(self.env, CREW_TEST_CREATE_FAIL='1'))
        p = self.crew / 'state/one.meta'
        meta = self.meta()
        for key in ['profile', 'model', 'effort', 'launch_args']:
            del meta[key]
        p.write_text(json.dumps(meta))
        self.cli('spawn', '--resume', 'one')
        self.assertEqual(self.start_args('one')[1], ['--permission-mode', 'auto'])

    def test_crew_usage_keeps_null_cost_and_warns(self):
        self.spawn()
        result = self.usage()
        self.assertIn('costUsd is null', result.stderr)
        self.assertIn('not $0', result.stderr)
        data = json.loads((self.worktree() / '.crew/usage.json').read_text())
        self.assertIsNone(data['costUsd'])
        priced = self.usage(cost_usd='1.5')
        self.assertNotIn('costUsd is null', priced.stderr)
        data = json.loads((self.worktree() / '.crew/usage.json').read_text())
        self.assertEqual(data['costUsd'], 1.5)
        estimated = self.usage(source='estimated')
        self.assertIn('totalTokens', estimated.stderr)
        self.assertIsNone(json.loads((self.worktree() / '.crew/usage.json').read_text())['costUsd'])

    def test_usage_rollup_splits_known_and_blind(self):
        day = self.run_cmd(['date', '-u', '+%Y-%m-%d']).stdout.strip()
        state = self.crew / 'state'
        state.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                'schema': 'crew-usage/v1', 'taskId': 'priced', 'kind': 'ship',
                'harness': 'claude', 'model': 'claude-opus-5-5',
                'recordedAt': f'{day}T01:00:00Z', 'source': 'harness',
                'costUsd': 1.25, 'tokens': {'input': 1, 'output': 1},
            },
            {
                'schema': 'crew-usage/v1', 'taskId': 'blind-ship', 'kind': 'ship',
                'harness': 'grok', 'model': 'grok-4.7',
                'recordedAt': f'{day}T02:00:00Z', 'source': 'estimated',
                'tokens': {'input': 1300000, 'output': 1},
            },
            {
                'schema': 'crew-usage/v1', 'taskId': 'explicit-null', 'kind': 'scout',
                'harness': 'grok', 'model': 'grok-4.7',
                'recordedAt': f'{day}T03:00:00Z', 'source': 'unavailable',
                'costUsd': None, 'tokens': {'input': 0, 'output': 0},
            },
            {
                'schema': 'crew-usage/v1', 'taskId': 'old-priced', 'kind': 'scout',
                'harness': 'claude', 'model': 'claude-fable-5-1',
                'recordedAt': '2020-01-01T00:00:00Z', 'source': 'harness',
                'costUsd': 9.5, 'tokens': {'input': 1, 'output': 1},
            },
        ]
        (state / 'usage.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
        window = self.cli('usage', '--since', day, '--until', day).stdout
        self.assertIn('records: 3', window)
        self.assertIn('known_usd: 1.25', window)
        self.assertIn('priced: 1', window)
        self.assertIn('blind: 2', window)
        self.assertIn('blind-ship grok/grok-4.7 ship estimated', window)
        self.assertIn('explicit-null grok/grok-4.7 scout unavailable', window)
        self.assertNotIn('old-priced', window)
        self.assertNotIn('9.50', window)
        everything = self.cli('usage').stdout
        self.assertIn('records: 4', everything)
        self.assertIn('known_usd: 10.75', everything)
        self.assertIn('old-priced', everything)


if __name__ == '__main__':
    unittest.main(verbosity=2)
