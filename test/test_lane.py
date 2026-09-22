"""Transition table for the rules-completion lane. No herdr process."""

import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest

SOURCE = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(SOURCE / 'lib'))
import lane


def world(root, *, budget=40, state='shipping', verb=None, cost=1, pr='https://example.test/pull/1',
          omit_cost=False, role='ship'):
    lane_id = 'rules-r3'
    task = f'{lane_id}-s' if role == 'ship' else f'{lane_id}-v1'
    wt = root / 'wt' / task
    (wt / '.crew').mkdir(parents=True, exist_ok=True)
    if verb:
        (wt / '.crew' / 'status').write_text(f'100 {verb}: note\n')
    else:
        (wt / '.crew' / 'status').write_text('100 working: spawned\n')
    verdict = wt / '.crew' / 'lane-result.json'
    if verdict.exists():
        verdict.unlink()
    usage = {'schema': 'crew-usage/v1'}
    if pr:
        usage['pr'] = {'url': pr}
    if not omit_cost:
        usage['costUsd'] = cost
    (wt / '.crew' / 'usage.json').write_text(json.dumps(usage))
    meta = {'id': task, 'worktree': str(wt), 'pane': f'pane-{task}', 'kind': 'ship' if role != 'review' else 'scout'}
    (root / 'state').mkdir(exist_ok=True)
    (root / 'state' / f'{task}.meta').write_text(json.dumps(meta))
    review = root / 'state' / 'lanes' / lane_id
    review.mkdir(parents=True, exist_ok=True)
    (review / 'review-1.md').write_text('review one\n')
    (review / 'review-2.md').write_text('review two\n')
    data = {
        'id': lane_id,
        'kind': 'rules-completion',
        'state': state,
        'project': '/repo',
        'base': 'feature/isometric-demo',
        'share': 'community-demo-design',
        'freeze': '/freeze.md',
        'budgetUsd': budget,
        'maxCycles': 2,
        'stallMinutes': 60,
        'reviewCount': 0 if role == 'ship' else 1,
        'currentTask': task,
        'tasks': [task] if role == 'ship' else [f'{lane_id}-s', task],
        'roles': {task: role} if role == 'ship' else {f'{lane_id}-s': 'ship', task: 'review'},
        'panes': {task: f'pane-{task}'},
        'briefs': {},
        'ship': {'model': 'grok-4.7', 'effort': 'high', 'agent': 'grok'},
        'review': {'model': 'grok-4.7', 'effort': 'high', 'agent': 'grok'},
        'applied': [],
        'notified': [],
        'lastEventAt': {},
        'workingSince': {},
        'stopReason': None,
        'fixBrief': f'state/lanes/{lane_id}/fix-1.md',
        'pendingSpawn': None,
    }
    if role != 'ship':
        ship_wt = root / 'wt' / f'{lane_id}-s'
        (ship_wt / '.crew').mkdir(parents=True, exist_ok=True)
        (ship_wt / '.crew' / 'usage.json').write_text(json.dumps({
            'costUsd': 1, 'pr': {'url': 'https://example.test/pull/1'},
        }))
        (root / 'state' / f'{lane_id}-s.meta').write_text(json.dumps({
            'id': f'{lane_id}-s', 'worktree': str(ship_wt), 'pane': 'pane-ship', 'kind': 'ship',
        }))
    return data, task


class LaneTransitionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='lane-')
        self.root = Path(self.tmp.name)
        self.spawns = []
        self.notes = []

    def tearDown(self):
        self.tmp.cleanup()

    def spawn(self, root, lane_data, task_id, kind, brief, role, spec):
        self.spawns.append(task_id)
        wt = root / 'wt' / task_id
        (wt / '.crew').mkdir(parents=True)
        (wt / '.crew' / 'status').write_text('200 working: spawned\n')
        meta = {'id': task_id, 'worktree': str(wt), 'pane': f'pane-{task_id}', 'kind': kind}
        (root / 'state' / f'{task_id}.meta').write_text(json.dumps(meta))
        return meta

    def notify(self, sound, title, body):
        self.notes.append((sound, title, body))

    def drive(self, data, task, status, **kwargs):
        action = lane.reconcile(self.root, data, task, status, **kwargs)
        lane.commit(self.root, data, action, spawn=self.spawn, notify=self.notify)
        return data

    def test_ship_done_spawns_one_review_even_while_herdr_still_working(self):
        data, task = world(self.root, verb='done')
        self.drive(data, task, 'working')
        self.assertEqual(self.spawns, ['rules-r3-v1'])
        self.assertEqual(data['state'], 'reviewing')
        self.assertEqual(data['reviewCount'], 1)
        self.drive(data, task, 'idle')
        self.assertEqual(self.spawns, ['rules-r3-v1'])

    def test_duplicate_terminal_line_does_not_spawn_again(self):
        data, task = world(self.root, verb='done', role='review')
        (self.root / 'wt' / task / '.crew' / 'lane-result.json').write_text(
            json.dumps({'verdict': 'pass', 'summary': 'ok'})
        )
        self.drive(data, task, 'idle')
        self.assertEqual(data['state'], 'passed')
        self.assertEqual(self.notes[0][0], 'done')
        again = lane.reconcile(self.root, data, task, 'done')
        self.assertIsNone(again['notify'])
        self.assertNotEqual(again['kind'], 'spawn')

    def test_idle_without_done_notifies_and_does_not_spawn(self):
        data, task = world(self.root, verb=None)
        self.drive(data, task, 'idle')
        self.assertEqual(self.spawns, [])
        self.assertEqual(data['state'], 'shipping')
        self.assertIn('stopped without reporting', self.notes[0][2])
        self.drive(data, task, 'idle')
        self.assertEqual(len(self.notes), 1)

    def test_blocked_unknown_stall_and_exit(self):
        data, task = world(self.root)
        self.drive(data, task, 'blocked')
        self.assertEqual(data['state'], 'shipping')
        self.assertIn('blocked', self.notes[0][1])
        self.drive(data, task, 'unknown', tick=False)
        self.assertEqual(len(self.notes), 1)
        self.drive(data, task, 'unknown', tick=True)
        self.assertIn('unavailable', self.notes[-1][2])
        self.drive(data, task, 'working', now=1_000)
        self.drive(data, task, 'working', tick=True, now=1_000 + 3600)
        self.assertIn('still working', self.notes[-1][2])
        self.assertEqual(self.spawns, [])
        self.drive(data, task, 'gone', gone=True)
        self.assertEqual(data['state'], 'stopped')
        self.assertEqual(data['stopReason'], 'pane exited')

    def test_null_cost_missing_pr_and_budget_stop(self):
        data, task = world(self.root, verb='done', omit_cost=True)
        self.drive(data, task, 'idle')
        self.assertEqual(data['stopReason'], 'null costUsd')
        self.assertEqual(self.spawns, [])
        data, task = world(self.root, verb='done', pr=None)
        self.drive(data, task, 'idle')
        self.assertEqual(data['stopReason'], 'missing pr.url')
        data, task = world(self.root, verb='done', cost=41, budget=40)
        self.drive(data, task, 'done')
        self.assertEqual(data['stopReason'], 'budget exceeded')

    def test_failed_needs_decision_and_cancel_stop_without_resume(self):
        data, task = world(self.root, verb='failed')
        self.drive(data, task, 'idle')
        self.assertEqual(data['stopReason'], 'failed')
        data, task = world(self.root, verb='needs-decision')
        self.drive(data, task, 'idle')
        self.assertEqual(data['stopReason'], 'needs-decision')
        data, task = world(self.root, verb='done', state='cancelled')
        self.drive(data, task, 'idle')
        self.assertEqual(self.spawns, [])
        self.assertEqual(data['state'], 'cancelled')

    def test_fail_spawns_one_fix_then_cycle_cap(self):
        data, task = world(self.root, verb='done', role='review')
        fix = self.root / 'state' / 'lanes' / 'rules-r3' / 'fix-1.md'
        fix.write_text(
            '## Edit-Map\n\n`lib/lane.py:1`\n\n## Thin TDD\n\nmust-stay-green\n\n```\nmake check\n```\n'
        )
        (self.root / 'wt' / task / '.crew' / 'lane-result.json').write_text(json.dumps({
            'verdict': 'fail', 'summary': 'no', 'fixBrief': 'state/lanes/rules-r3/fix-1.md',
        }))
        self.drive(data, task, 'idle')
        self.assertEqual(self.spawns, ['rules-r3-f1'])
        self.assertEqual(data['state'], 'fixing')
        fix_task = 'rules-r3-f1'
        (self.root / 'wt' / fix_task / '.crew' / 'status').write_text('300 done: fixed\n')
        (self.root / 'wt' / fix_task / '.crew' / 'usage.json').write_text(json.dumps({
            'costUsd': 2, 'pr': {'url': 'https://example.test/pull/2'},
        }))
        self.drive(data, fix_task, 'idle')
        self.assertEqual(self.spawns, ['rules-r3-f1', 'rules-r3-v2'])
        self.assertEqual(data['reviewCount'], 2)
        second = 'rules-r3-v2'
        (self.root / 'wt' / second / '.crew' / 'status').write_text('400 done: no again\n')
        (self.root / 'wt' / second / '.crew' / 'usage.json').write_text(json.dumps({'costUsd': 1}))
        (self.root / 'wt' / second / '.crew' / 'lane-result.json').write_text(
            json.dumps({'verdict': 'fail', 'summary': 'still', 'fixBrief': 'state/lanes/rules-r3/fix-1.md'})
        )
        self.drive(data, second, 'done')
        self.assertEqual(data['state'], 'stopped')
        self.assertEqual(data['stopReason'], 'cycle cap')
        self.assertEqual(self.spawns, ['rules-r3-f1', 'rules-r3-v2'])

    def test_bad_fix_brief_and_block_and_missing_verdict_stop(self):
        data, task = world(self.root, verb='done', role='review')
        (self.root / 'wt' / task / '.crew' / 'lane-result.json').write_text(
            json.dumps({'verdict': 'block', 'summary': 'product'})
        )
        self.drive(data, task, 'idle')
        self.assertEqual(data['stopReason'], 'block')
        data, task = world(self.root, verb='done', role='review')
        self.drive(data, task, 'idle')
        self.assertEqual(data['stopReason'], 'missing verdict')
        data, task = world(self.root, verb='done', role='review')
        bad = self.root / 'state' / 'lanes' / 'rules-r3' / 'fix-1.md'
        bad.write_text('vague\n')
        (self.root / 'wt' / task / '.crew' / 'lane-result.json').write_text(json.dumps({
            'verdict': 'fail', 'summary': 'no', 'fixBrief': str(bad),
        }))
        self.drive(data, task, 'idle')
        self.assertEqual(data['stopReason'], 'fix brief invalid')
        self.assertEqual(self.spawns, [])

    def test_spawn_template_has_no_banned_flags(self):
        data, _task = world(self.root)
        argv = lane.build_spawn_argv(SOURCE, data, 'rules-r3-v1', 'scout', '/brief.md', data['review'])
        self.assertNotIn('--yolo', argv)
        self.assertNotIn('--permission-mode', argv)
        self.assertNotIn('xhigh', argv)
        self.assertIn('--lane', argv)
        pi = dict(data['review'], agent='pi')
        pi_argv = lane.build_spawn_argv(SOURCE, data, 'rules-r3-v1', 'scout', '/brief.md', pi)
        self.assertIn('--unattended-bypass', pi_argv)

    def test_entry_text_and_yolo_word(self):
        good = '## Edit-Map\n\n`bin/lane:1`\n\n## Thin TDD\n\nmust-stay-green\n\n```\nmake check\n```\n'
        self.assertEqual(lane.brief_problems(good), [])
        self.assertTrue(lane.brief_problems('nope'))
        self.assertTrue(lane.brief_problems(good + 'Mode: packet-path\n'))
        self.assertEqual(lane.yolo_word('# Yolo\n\n**Status:** OFF (owner)\n'), 'OFF')
        self.assertEqual(lane.yolo_word('**Status:** ON\n'), 'ON')
        self.assertIsNone(lane.yolo_word('no status\n'))

    def test_socket_subscribe_reads_one_push(self):
        path = self.root / 'herdr.sock'
        seen = {}
        ready = threading.Event()

        def serve():
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            srv.bind(str(path))
            srv.listen(1)
            ready.set()
            conn, _addr = srv.accept()
            buf = b''
            while b'\n' not in buf:
                buf += conn.recv(4096)
            req = json.loads(buf.split(b'\n', 1)[0])
            seen['method'] = req['method']
            seen['types'] = [item['type'] for item in req['params']['subscriptions']]
            conn.sendall((json.dumps({
                'id': req['id'], 'result': {'type': 'subscription_started'},
            }) + '\n').encode())
            conn.sendall((json.dumps({
                'event': 'pane_agent_status_changed',
                'data': {
                    'type': 'pane_agent_status_changed',
                    'pane_id': 'pane-rules-r3-s',
                    'workspace_id': 'w',
                    'agent_status': 'idle',
                },
            }) + '\n').encode())
            time.sleep(0.2)
            conn.close()
            srv.close()

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        self.assertTrue(ready.wait(2))
        parsed = lane.read_one_push(str(path), lane.subscriptions_for([{
            'state': 'shipping',
            'currentTask': 'rules-r3-s',
            'panes': {'rules-r3-s': 'pane-rules-r3-s'},
        }]))
        thread.join(2)
        self.assertEqual(seen['method'], 'events.subscribe')
        self.assertIn('pane.agent_status_changed', seen['types'])
        self.assertIn('pane.exited', seen['types'])
        self.assertEqual(parsed['agent_status'], 'idle')
        dotted = lane.parse_push({
            'event': 'pane.output_matched',
            'data': {'pane_id': 'p', 'matched_line': '1 done: x', 'read': {}},
        })
        self.assertEqual(dotted['kind'], 'output')

if __name__ == '__main__':
    unittest.main(verbosity=2)
