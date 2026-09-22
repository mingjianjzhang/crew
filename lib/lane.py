#!/usr/bin/env python3
"""Rules-completion lane driver.

v0 is bin/lane assign, cancel, and watch. Watch subscribes to herdr's
newline-delimited JSON socket (protocol 22) and reconciles .crew/status
before it spawns. There is no crew-status write-site hook.
"""

import json
import os
from decimal import Decimal
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

TICK_SECONDS = 60
ID_RE = re.compile(r'^[a-z][a-z0-9-]{0,26}$')
EFFORT_RE = re.compile(r'^[a-z][a-z0-9-]*$')
PATH_LINE_RE = re.compile(
    r'[\w./-]+\.[A-Za-z0-9]+:\d+(?:-\d+)?|[\w.-]+(?:/[\w.-]+)+:\d+(?:-\d+)?'
)
STATUS_RE = re.compile(
    r'^(\d+) (working|needs-decision|resolved|done|failed): (.*)$'
)
STATUS_VERB_REGEX = r'[0-9]+ (working|needs-decision|resolved|done|failed):'
TERMINAL = {'done', 'failed', 'needs-decision'}
CLOSED = {'passed', 'stopped', 'cancelled'}
ROOT = Path(__file__).resolve().parents[1]


class BusyLock(Exception):
    pass


class LaneError(Exception):
    pass


def die(message):
    print(f'crew: {message}', file=sys.stderr)
    raise SystemExit(1)


def valid_id(value, label='id'):
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        die(f'Invalid {label}: use 1-27 lowercase letters, digits or hyphens, starting with a letter.')


def lane_dir(root):
    return root / 'state' / 'lanes'


def lane_path(root, lane_id):
    return lane_dir(root) / f'{lane_id}.json'


def save_lane(root, lane):
    path = lane_path(root, lane['id'])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(lane, indent=2) + '\n')
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def load_lane(root, lane_id):
    path = lane_path(root, lane_id)
    if not path.is_file():
        die(f'No lane: {lane_id}')
    return json.loads(path.read_text())


def list_lanes(root):
    directory = lane_dir(root)
    if not directory.is_dir():
        return []
    lanes = []
    for path in sorted(directory.glob('*.json')):
        try:
            lanes.append(json.loads(path.read_text()))
        except (OSError, json.JSONDecodeError):
            print(f'lane-watch: skipped unreadable {path.name}', file=sys.stderr)
    return lanes


class lane_lock:
    def __init__(self, root, lane_id):
        self.path = lane_dir(root) / f'{lane_id}.lock'

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.mkdir()
        except FileExistsError:
            raise BusyLock(self.path) from None
        (self.path / 'owner').write_text(f'{os.getpid()} {int(time.time())}\n')
        return self

    def __exit__(self, exc_type, exc, tb):
        owner = self.path / 'owner'
        if owner.exists():
            owner.unlink()
        try:
            self.path.rmdir()
        except OSError:
            pass
        return False


def brief_problems(text):
    problems = []
    if 'Edit-Map' not in text:
        problems.append('brief needs an Edit-Map heading or the words Edit-Map')
    elif not PATH_LINE_RE.search(text):
        problems.append('brief Edit-Map needs a path:line cite')
    if 'Thin TDD' not in text and 'must-stay-green' not in text:
        problems.append('brief needs a Thin TDD block or must-stay-green')
    elif not _has_run_command(text):
        problems.append('brief Thin TDD needs a fenced run command')
    if 'Mode: hosted-debug-session' in text or 'Mode: packet-path' in text:
        problems.append('lane refuses hosted-debug and packet-path briefs')
    return problems


def _has_run_command(text):
    for match in re.finditer(r'```[^\n]*\n(.*?)```', text, re.S):
        for line in match.group(1).splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                return True
    return False


def yolo_word(text):
    match = re.search(r'(?im)^.*Status:\**\s*(ON|OFF)\b', text)
    if not match:
        return None
    return match.group(1).upper()


def check_spec(spec, label):
    if spec['effort'] == 'xhigh':
        die(f'{label} effort xhigh is refused')
    if not EFFORT_RE.fullmatch(spec['effort'] or ''):
        die(f'Invalid {label} effort')
    if not spec['model'] or any(char in spec['model'] for char in '\n\r\t'):
        die(f'Invalid {label} model')
    if not EFFORT_RE.fullmatch(spec['agent'] or ''):
        die(f'Invalid {label} agent')


def harness_policy(root, kind):
    for line in (root / 'harnesses.tsv').read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        fields = line.split('\t')
        if fields and fields[0] == kind:
            return fields[1]
    die(f'Unsupported harness: {kind}')


def build_spawn_argv(root, lane, task_id, kind, brief, spec):
    check_spec(spec, kind)
    argv = [
        str(root / 'bin' / 'spawn'),
        '--id', task_id,
        '--project', lane['project'],
        '--kind', kind,
        '--brief', str(brief),
        '--agent', spec['agent'],
        '--model', spec['model'],
        '--effort', spec['effort'],
        '--base', lane['base'],
        '--share', lane['share'],
        '--lane', lane['id'],
    ]
    if harness_policy(root, spec['agent']) == 'bypass':
        argv.append('--unattended-bypass')
    banned = {'--yolo', '--await-human'}
    if banned.intersection(argv) or 'xhigh' in argv or 'plan' in argv:
        die('lane spawn template grew a banned flag')
    return argv


def default_spawn(root, lane, task_id, kind, brief, role, spec):
    argv = build_spawn_argv(root, lane, task_id, kind, brief, spec)
    result = subprocess.run(argv, text=True, capture_output=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or 'spawn failed').strip()
        raise LaneError(detail)
    meta_path = root / 'state' / f'{task_id}.meta'
    if not meta_path.is_file():
        raise LaneError('spawn returned without task metadata')
    return json.loads(meta_path.read_text())


def default_notify(sound, title, body):
    subprocess.run(
        ['herdr', 'notification', 'show', '--sound', sound, '--body', body or '', title],
        check=False,
    )


def read_meta(root, task_id):
    path = root / 'state' / f'{task_id}.meta'
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def read_log(root, task_id):
    meta = read_meta(root, task_id)
    if not meta:
        return None, None
    path = Path(meta['worktree']) / '.crew' / 'status'
    if not path.is_file():
        return None, None
    last = None
    for line in path.read_text().splitlines():
        if STATUS_RE.match(line):
            last = line
    if not last:
        return None, None
    return STATUS_RE.match(last).group(2), last


def read_usage(root, task_id):
    meta = read_meta(root, task_id)
    if not meta:
        return None
    path = Path(meta['worktree']) / '.crew' / 'usage.json'
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def pr_url(usage):
    pr = usage.get('pr') if isinstance(usage, dict) else None
    if isinstance(pr, dict) and isinstance(pr.get('url'), str) and pr['url']:
        return pr['url']
    return None


def as_cost(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and (value != value or value in (float('inf'), float('-inf'))):
        return None
    return Decimal(str(value))


def cost_problem(root, lane):
    total = Decimal(0)
    for task in lane['tasks']:
        usage = read_usage(root, task)
        if usage is None or 'costUsd' not in usage:
            return 'missing usage' if usage is None else 'null costUsd'
        cost = as_cost(usage.get('costUsd'))
        if cost is None:
            return 'null costUsd'
        total += cost
    budget = as_cost(lane.get('budgetUsd'))
    if budget is None:
        return 'null costUsd'
    if total > budget:
        return 'budget exceeded'
    return None


def latest_pr(root, lane):
    found = None
    for task in lane['tasks']:
        if lane.get('roles', {}).get(task) not in ('ship', 'fix'):
            continue
        usage = read_usage(root, task)
        if usage and pr_url(usage):
            found = pr_url(usage)
    return found


def read_verdict(root, task_id):
    meta = read_meta(root, task_id)
    if not meta:
        return None
    path = Path(meta['worktree']) / '.crew' / 'lane-result.json'
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def fix_brief_path(root, lane, raw):
    if not isinstance(raw, str) or not raw or any(char in raw for char in '\n\r\t'):
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    allowed = (lane_dir(root) / lane['id']).resolve()
    if path != allowed and allowed not in path.parents:
        return None
    return path


def notify_once(lane, key, sound, title, body):
    if key in lane['notified']:
        return None
    lane['notified'].append(key)
    return {'sound': sound, 'title': title, 'body': body}


def stop(lane, reason):
    lane['state'] = 'stopped'
    lane['stopReason'] = reason
    lane['pendingSpawn'] = None
    note = notify_once(lane, f'stopped:{reason}', 'request', f"Lane {lane['id']} stopped", reason)
    return {'kind': 'update', 'notify': note}


def adopt(lane, meta, spec):
    task = spec['task']
    lane['currentTask'] = task
    if task not in lane['tasks']:
        lane['tasks'].append(task)
    lane['roles'][task] = spec['role']
    lane['briefs'][task] = spec['brief']
    pane = meta.get('pane')
    if pane:
        lane.setdefault('panes', {})[task] = pane
    lane['state'] = spec['state']
    lane['pendingSpawn'] = None


def resolve_pending(root, lane):
    pending = lane.get('pendingSpawn')
    if not pending:
        return {'kind': 'update', 'notify': None}
    meta = read_meta(root, pending['task'])
    if meta:
        adopt(lane, meta, pending)
        return {'kind': 'update', 'notify': None}
    return stop(lane, 'spawn did not record a task')


def reconcile(root, lane, task, agent_status, *, gone=False, tick=False, now=None):
    """Return an action. Mutates lane. Does not spawn and does not save."""
    now = int(time.time()) if now is None else int(now)
    if lane.get('pendingSpawn'):
        return {'kind': 'resolve', 'notify': None}
    if lane.get('kind') != 'rules-completion':
        return stop(lane, 'unknown lane kind')
    if lane.get('state') in CLOSED:
        return {'kind': 'update', 'notify': None}
    if task != lane.get('currentTask'):
        return {'kind': 'update', 'notify': None}

    lane.setdefault('lastEventAt', {})
    lane.setdefault('workingSince', {})
    lane.setdefault('notified', [])
    lane.setdefault('applied', [])
    lane.setdefault('panes', {})
    lane['lastEventAt'][task] = now

    if gone or agent_status == 'gone':
        return stop(lane, 'pane exited')

    verb, line = read_log(root, task)
    terminal = verb in TERMINAL
    title = f"Lane {lane['id']}"

    if agent_status == 'blocked':
        note = notify_once(lane, f'blocked:{task}', 'request', f'{title} blocked', 'blocked in pane')
        return {'kind': 'update', 'notify': note}
    if agent_status == 'unknown':
        note = None
        if tick:
            note = notify_once(lane, f'unknown:{task}', 'request', f'{title} unknown', 'live state unavailable')
        return {'kind': 'update', 'notify': note}
    if agent_status == 'working' and not terminal:
        lane['workingSince'].setdefault(task, now)
        note = None
        stall = int(lane.get('stallMinutes') or 60) * 60
        age = now - int(lane['workingSince'][task])
        if tick and age >= stall:
            minutes = max(1, age // 60)
            note = notify_once(
                lane, f'stall:{task}', 'request', f'{title} still working',
                f'still working, age {minutes}m',
            )
        return {'kind': 'update', 'notify': note}

    if line and line in lane['applied']:
        return {'kind': 'update', 'notify': None}
    if verb == 'needs-decision':
        lane['applied'].append(line)
        return stop(lane, 'needs-decision')
    if verb == 'failed':
        lane['applied'].append(line)
        return stop(lane, 'failed')
    if verb != 'done':
        note = None
        if agent_status in ('idle', 'done'):
            note = notify_once(
                lane, f'silent:{task}', 'request', f'{title} stopped',
                'stopped without reporting',
            )
        return {'kind': 'update', 'notify': note}

    lane['applied'].append(line)
    role = lane.get('roles', {}).get(task)
    problem = cost_problem(root, lane)
    if problem:
        return stop(lane, problem)
    if role in ('ship', 'fix'):
        usage = read_usage(root, task)
        if not usage or not pr_url(usage):
            return stop(lane, 'missing pr.url')
        return _spawn_review(root, lane)
    if role == 'review':
        return _finish_review(root, lane, task)
    return stop(lane, 'unknown task role')


def _spawn_review(root, lane):
    count = int(lane.get('reviewCount') or 0) + 1
    if count > int(lane.get('maxCycles') or 2):
        return stop(lane, 'cycle cap')
    task_id = f"{lane['id']}-v{count}"
    brief = lane_dir(root) / lane['id'] / f'review-{count}.md'
    if not brief.is_file() or brief.stat().st_size == 0:
        return stop(lane, 'missing review brief')
    lane['reviewCount'] = count
    lane['pendingSpawn'] = {
        'task': task_id,
        'kind': 'scout',
        'role': 'review',
        'brief': str(brief),
        'spec': lane['review'],
        'state': 'reviewing',
    }
    return {'kind': 'spawn', 'notify': None, 'spawn': lane['pendingSpawn']}


def _finish_review(root, lane, task):
    verdict = read_verdict(root, task)
    if not verdict or verdict.get('verdict') not in ('pass', 'fail', 'block'):
        return stop(lane, 'missing verdict')
    decision = verdict['verdict']
    if decision == 'block':
        return stop(lane, 'block')
    if decision == 'pass':
        lane['state'] = 'passed'
        lane['stopReason'] = None
        body = latest_pr(root, lane) or 'review passed'
        note = notify_once(lane, 'passed', 'done', f"Lane {lane['id']} ready to merge", body)
        return {'kind': 'update', 'notify': note}
    if int(lane.get('reviewCount') or 0) >= int(lane.get('maxCycles') or 2):
        return stop(lane, 'cycle cap')
    path = fix_brief_path(root, lane, verdict.get('fixBrief'))
    if path is None or not path.is_file():
        return stop(lane, 'fix brief missing')
    problems = brief_problems(path.read_text())
    if problems:
        return stop(lane, 'fix brief invalid')
    task_id = f"{lane['id']}-f1"
    lane['pendingSpawn'] = {
        'task': task_id,
        'kind': 'ship',
        'role': 'fix',
        'brief': str(path),
        'spec': lane['ship'],
        'state': 'fixing',
    }
    return {'kind': 'spawn', 'notify': None, 'spawn': lane['pendingSpawn']}


def commit(root, lane, action, spawn=None, notify=None):
    spawn = spawn or default_spawn
    notify = notify or default_notify
    if action.get('kind') == 'resolve':
        action = resolve_pending(root, lane)
    save_lane(root, lane)
    note = action.get('notify')
    if note:
        notify(note['sound'], note['title'], note['body'])
    if action.get('kind') != 'spawn':
        return lane
    spec = action['spawn']
    try:
        meta = spawn(root, lane, spec['task'], spec['kind'], spec['brief'], spec['role'], spec['spec'])
    except (LaneError, OSError) as exc:
        lane['state'] = 'stopped'
        lane['stopReason'] = f'spawn failed: {exc}'
        lane['pendingSpawn'] = None
        note = notify_once(lane, 'stopped:spawn failed', 'request', f"Lane {lane['id']} stopped", lane['stopReason'])
        save_lane(root, lane)
        if note:
            notify(note['sound'], note['title'], note['body'])
        return lane
    adopt(lane, meta, spec)
    save_lane(root, lane)
    return lane


def locked_commit(root, lane_id, mutate, spawn=None, notify=None):
    try:
        with lane_lock(root, lane_id):
            lane = load_lane(root, lane_id)
            action = mutate(lane)
            return commit(root, lane, action, spawn=spawn, notify=notify)
    except BusyLock:
        print('crew: lane lock busy; skipped', file=sys.stderr)
        return None


def write_review_brief(root, lane, number, ship_task):
    review_task = f"{lane['id']}-v{number}"
    path = lane_dir(root) / lane['id'] / f'review-{number}.md'
    path.parent.mkdir(parents=True, exist_ok=True)
    ship_meta = f"state/{ship_task}.meta"
    text = f'''# Review {lane['id']} cycle {number}

Outcome: review task `{ship_task}` against the freeze named on the lane.
Read `{ship_meta}:1` and that worktree's `.crew/usage.json` for the PR url.
Review the PR diff. Do not merge it.

## Edit-Map

Write only these paths:
- `.crew/lane-result.json:1` in this worktree
- `state/lanes/{lane['id']}/fix-1.md:1` only when the verdict is fail
- `.crew/share/reviews/{review_task}.md:1` (the one share deliverable)

Open only these. Do not edit `CURRENT.md`, indexes, or memory.

## Thin TDD

must-stay-green: re-run the fenced command from the ship brief. This scout does not change project code.

```
git status --short
```

## Verdict

Write `.crew/usage.json` and `.crew/lane-result.json` before `done`.
`costUsd` must be a number. Null stops the lane.

Pass: `{{"verdict":"pass","summary":"one line"}}`
Fail: `{{"verdict":"fail","summary":"one line","fixBrief":"state/lanes/{lane['id']}/fix-1.md"}}`
The fix brief needs its own Edit-Map path:line cite and a Thin TDD fenced run command.
Block: `{{"verdict":"block","summary":"needs a product call"}}`

Then `.crew/crew-status done`.

Non-goals: no `bin/spawn`, no `bin/answer`, no `bin/finish`, no `gh pr merge`, no CURRENT.md.
'''
    path.write_text(text)
    return path


def other_live_share(root, share, lane_id):
    for lane in list_lanes(root):
        if lane.get('id') == lane_id:
            continue
        if lane.get('share') == share and lane.get('state') not in CLOSED:
            return lane.get('id')
    return None


def parse_assign(argv):
    if not argv or argv[0].startswith('-'):
        die('Usage: bin/lane assign ID --project PATH --base REF --share ID --freeze FILE --budget-usd N --brief FILE [--max-cycles 2] [--stall-minutes 60] --ship-model M --ship-effort E --review-model M --review-effort E [--ship-agent grok] [--review-agent grok] [--no-watch]')
    lane_id = argv[0]
    opts = {
        'max-cycles': '2',
        'stall-minutes': '60',
        'ship-agent': 'grok',
        'review-agent': 'grok',
    }
    flags = set()
    index = 1
    while index < len(argv):
        key = argv[index]
        if key == '--no-watch':
            flags.add('no-watch')
            index += 1
            continue
        if not key.startswith('--') or index + 1 >= len(argv):
            die(f'Unknown or incomplete argument: {key}')
        opts[key[2:]] = argv[index + 1]
        index += 2
    required = (
        'project', 'base', 'share', 'freeze', 'budget-usd', 'brief',
        'ship-model', 'ship-effort', 'review-model', 'review-effort',
    )
    missing = [name for name in required if name not in opts]
    if missing:
        die('Missing ' + ' '.join(f'--{name}' for name in missing))
    return lane_id, opts, flags


def cmd_assign(root, argv):
    lane_id, opts, flags = parse_assign(argv)
    valid_id(lane_id, 'lane id')
    for suffix in ('-s', '-v1', '-f1', '-v2'):
        valid_id(lane_id + suffix, f'derived task {lane_id}{suffix}')
    valid_id(opts['share'], 'share id')
    if any(char in opts['base'] for char in '\n\r\t') or not opts['base']:
        die('Invalid --base')
    if not re.fullmatch(r'\d+(\.\d+)?', opts['budget-usd']):
        die('Invalid --budget-usd')
    if not re.fullmatch(r'[1-9]\d*', opts['max-cycles']):
        die('Invalid --max-cycles')
    if not re.fullmatch(r'[1-9]\d*', opts['stall-minutes']):
        die('Invalid --stall-minutes')
    project = Path(opts['project']).expanduser().resolve()
    if not project.is_dir():
        die('Project path does not exist')
    freeze = Path(opts['freeze']).expanduser().resolve()
    if not freeze.is_file() or 'FROZEN' not in freeze.read_text():
        die('--freeze must be an existing file whose text contains FROZEN')
    brief = Path(opts['brief']).expanduser().resolve()
    if not brief.is_file() or brief.stat().st_size == 0:
        die('Brief file is empty or missing')
    problems = brief_problems(brief.read_text())
    if problems:
        die('; '.join(problems))
    ship = {'agent': opts['ship-agent'], 'model': opts['ship-model'], 'effort': opts['ship-effort']}
    review = {'agent': opts['review-agent'], 'model': opts['review-model'], 'effort': opts['review-effort']}
    check_spec(ship, 'ship')
    check_spec(review, 'review')
    yolo = root / 'state' / 'share' / opts['share'] / 'YOLO.md'
    if yolo.is_file():
        word = yolo_word(yolo.read_text())
        if word != 'OFF':
            die('YOLO.md status is not OFF; the lane will not FF-push the tip')
    if lane_path(root, lane_id).exists():
        die(f'Lane already exists: {lane_id}')
    live = other_live_share(root, opts['share'], lane_id)
    if live:
        die(f'Share {opts["share"]} already has live lane {live}')
    ship_task = f'{lane_id}-s'
    lane = {
        'id': lane_id,
        'kind': 'rules-completion',
        'state': 'shipping',
        'project': str(project),
        'base': opts['base'],
        'share': opts['share'],
        'freeze': str(freeze),
        'budgetUsd': float(opts['budget-usd']) if '.' in opts['budget-usd'] else int(opts['budget-usd']),
        'maxCycles': int(opts['max-cycles']),
        'stallMinutes': int(opts['stall-minutes']),
        'reviewCount': 0,
        'currentTask': ship_task,
        'tasks': [ship_task],
        'roles': {ship_task: 'ship'},
        'panes': {},
        'briefs': {ship_task: str(brief)},
        'ship': ship,
        'review': review,
        'applied': [],
        'notified': [],
        'lastEventAt': {},
        'workingSince': {},
        'stopReason': None,
        'fixBrief': f'state/lanes/{lane_id}/fix-1.md',
        'pendingSpawn': {
            'task': ship_task,
            'kind': 'ship',
            'role': 'ship',
            'brief': str(brief),
            'spec': ship,
            'state': 'shipping',
        },
    }
    write_review_brief(root, lane, 1, ship_task)
    write_review_brief(root, lane, 2, f'{lane_id}-f1')
    try:
        with lane_lock(root, lane_id):
            if other_live_share(root, opts['share'], lane_id):
                die(f'Share {opts["share"]} already has a live lane')
            save_lane(root, lane)
            try:
                meta = default_spawn(
                    root, lane, ship_task, 'ship', brief, 'ship', ship,
                )
            except (LaneError, OSError) as exc:
                lane['state'] = 'stopped'
                lane['stopReason'] = f'spawn failed: {exc}'
                lane['pendingSpawn'] = None
                save_lane(root, lane)
                die(lane['stopReason'])
            adopt(lane, meta, lane['pendingSpawn'])
            lane['state'] = 'shipping'
            save_lane(root, lane)
    except BusyLock:
        die(f'Busy: {lane_dir(root) / (lane_id + ".lock")}')
    if 'no-watch' not in flags:
        ensure_watch(root)
    print(f'{lane_id}: {lane_path(root, lane_id)}')
    print(f'task: {ship_task}')


def cmd_cancel(root, argv):
    if len(argv) != 1:
        die('Usage: bin/lane cancel ID')
    lane_id = argv[0]
    valid_id(lane_id, 'lane id')
    try:
        with lane_lock(root, lane_id):
            lane = load_lane(root, lane_id)
            if lane.get('state') != 'cancelled':
                lane['state'] = 'cancelled'
                lane['stopReason'] = 'cancelled'
                lane['pendingSpawn'] = None
                save_lane(root, lane)
    except BusyLock:
        die('lane lock busy')
    pid = watch_pid(root)
    if pid:
        try:
            os.kill(pid, signal.SIGHUP)
        except OSError:
            pass
    print(f'{lane_id}: cancelled')


def cmd_reconcile(root, argv):
    lane_id = None
    task = None
    agent_status = None
    gone = False
    tick = False
    index = 0
    if argv and not argv[0].startswith('-'):
        lane_id = argv[0]
        index = 1
    while index < len(argv):
        key = argv[index]
        if key == '--gone':
            gone = True
            index += 1
            continue
        if key == '--tick':
            tick = True
            index += 1
            continue
        if key in ('--task', '--agent-status') and index + 1 < len(argv):
            if key == '--task':
                task = argv[index + 1]
            else:
                agent_status = argv[index + 1]
            index += 2
            continue
        die(f'Unknown argument: {key}')
    if not lane_id or not task:
        die('Usage: bin/lane reconcile ID --task TASK [--agent-status STATUS] [--gone] [--tick]')
    valid_id(lane_id, 'lane id')

    def mutate(lane):
        return reconcile(root, lane, task, agent_status, gone=gone, tick=tick)

    locked_commit(root, lane_id, mutate)


def watch_pid_path(root):
    return lane_dir(root) / 'watch.pid'


def watch_pid(root):
    path = watch_pid_path(root)
    if not path.is_file():
        return None
    try:
        pid = int(path.read_text().strip())
    except ValueError:
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    return pid


def ensure_watch(root):
    pid = watch_pid(root)
    if pid:
        try:
            os.kill(pid, signal.SIGHUP)
        except OSError:
            pass
        return
    log_path = lane_dir(root) / 'watch.log'
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(log_path, 'a')
    proc = subprocess.Popen(
        [str(root / 'bin' / 'lane'), 'watch'],
        stdout=handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        cwd=str(root),
        env=os.environ.copy(),
    )
    watch_pid_path(root).write_text(f'{proc.pid}\n')


def active_lanes(root):
    return [
        lane for lane in list_lanes(root)
        if lane.get('kind') == 'rules-completion' and lane.get('state') not in CLOSED
    ]


def subscriptions_for(lanes):
    subs = []
    for lane in lanes:
        pane = (lane.get('panes') or {}).get(lane.get('currentTask'))
        if not pane:
            continue
        subs.append({'type': 'pane.agent_status_changed', 'pane_id': pane})
        subs.append({'type': 'pane.exited', 'pane_id': pane})
        subs.append({
            'type': 'pane.output_matched',
            'pane_id': pane,
            'source': 'recent',
            'strip_ansi': True,
            'match': {'type': 'regex', 'value': STATUS_VERB_REGEX},
        })
    return subs


def parse_push(message):
    if not isinstance(message, dict) or 'id' in message:
        return None
    event = message.get('event')
    data = message.get('data') if isinstance(message.get('data'), dict) else {}
    pane = data.get('pane_id')
    if event in ('pane.agent_status_changed', 'pane_agent_status_changed'):
        return {'kind': 'status', 'pane_id': pane, 'agent_status': data.get('agent_status')}
    if event in ('pane.exited', 'pane_exited', 'pane.closed', 'pane_closed'):
        return {'kind': 'exited', 'pane_id': pane}
    if event in ('pane.output_matched', 'pane_output_matched'):
        return {'kind': 'output', 'pane_id': pane}
    return None


class LineReader:
    def __init__(self, sock):
        self.sock = sock
        self.buf = b''

    def read(self):
        while b'\n' not in self.buf:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError('herdr socket closed')
            self.buf += chunk
        line, self.buf = self.buf.split(b'\n', 1)
        return line.decode()


def herdr_socket_path():
    override = os.environ.get('HERDR_SOCK')
    if override:
        return override
    return str(Path.home() / '.config' / 'herdr' / 'herdr.sock')


def send_line(sock, payload):
    sock.sendall(json.dumps(payload, separators=(',', ':')).encode() + b'\n')


def task_for_pane(lanes, pane_id):
    if not pane_id:
        return None
    for lane in lanes:
        task = lane.get('currentTask')
        if (lane.get('panes') or {}).get(task) == pane_id:
            return lane['id'], task
    return None


def due_for_tick(lane, now):
    task = lane.get('currentTask')
    last = int((lane.get('lastEventAt') or {}).get(task) or 0)
    return now - last >= TICK_SECONDS


def agent_status_of(task):
    result = subprocess.run(
        ['herdr', 'agent', 'get', f'crew-{task}'],
        text=True, capture_output=True,
    )
    raw = result.stdout or ''
    if result.returncode != 0:
        if 'agent_not_found' in (result.stderr or '') or 'agent_not_found' in raw:
            return 'gone', None
        return 'unknown', None
    try:
        agent = json.loads(raw)['result']['agent']
    except (json.JSONDecodeError, KeyError, TypeError):
        return 'unknown', None
    return agent.get('agent_status') or 'unknown', agent.get('pane_id')


def apply_observation(root, lane_id, task, agent_status, *, gone=False, tick=False, now=None):
    def mutate(lane):
        if agent_status and task == lane.get('currentTask'):
            # pane id may arrive from agent get before the lane file has it
            pass
        return reconcile(root, lane, task, agent_status, gone=gone, tick=tick, now=now)

    return locked_commit(root, lane_id, mutate)


def catch_up(root, now=None):
    now = int(time.time()) if now is None else int(now)
    for lane in active_lanes(root):
        task = lane.get('currentTask')
        if not task or not due_for_tick(lane, now):
            continue
        status, pane = agent_status_of(task)

        def mutate(current, status=status, pane=pane, task=task):
            if pane and task == current.get('currentTask'):
                current.setdefault('panes', {})[task] = pane
            return reconcile(
                root, current, task, status,
                gone=(status == 'gone'), tick=True, now=now,
            )

        locked_commit(root, lane['id'], mutate)


def read_one_push(sock_path, subs, timeout=5):
    """Subscribe and return the first parsed push. Test seam for the socket client."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(sock_path)
    reader = LineReader(sock)
    request_id = f'lane-watch-{os.getpid()}'
    send_line(sock, {
        'id': request_id,
        'method': 'events.subscribe',
        'params': {'subscriptions': subs},
    })
    while True:
        message = json.loads(reader.read())
        if message.get('id') == request_id:
            if 'error' in message:
                raise LaneError(json.dumps(message['error']))
            continue
        parsed = parse_push(message)
        if parsed:
            sock.close()
            return parsed


def run_socket(root, subs, *, once=False):
    sock_path = herdr_socket_path()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(TICK_SECONDS)
    sock.connect(sock_path)
    reader = LineReader(sock)
    request_id = f'lane-watch-{os.getpid()}'
    send_line(sock, {
        'id': request_id,
        'method': 'events.subscribe',
        'params': {'subscriptions': subs},
    })
    acked = False
    while True:
        try:
            raw = reader.read()
        except socket.timeout:
            catch_up(root)
            if once:
                sock.close()
                return
            if subscriptions_for(active_lanes(root)) != subs:
                sock.close()
                return
            continue
        except InterruptedError:
            sock.close()
            return
        if not raw.strip():
            continue
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if message.get('id') == request_id:
            if 'error' in message:
                raise LaneError(json.dumps(message['error']))
            acked = True
            continue
        if not acked:
            continue
        parsed = parse_push(message)
        if not parsed:
            continue
        found = task_for_pane(active_lanes(root), parsed.get('pane_id'))
        if found:
            lane_id, task = found
            if parsed['kind'] == 'exited':
                apply_observation(root, lane_id, task, 'gone', gone=True)
            elif parsed['kind'] == 'output':
                apply_observation(root, lane_id, task, None)
            else:
                apply_observation(root, lane_id, task, parsed.get('agent_status'))
        if once or subscriptions_for(active_lanes(root)) != subs:
            sock.close()
            return


def cmd_watch(root, argv):
    once = '--once' in argv
    hup = {'flag': False}

    def on_hup(signum, frame):
        hup['flag'] = True
        raise InterruptedError

    signal.signal(signal.SIGHUP, on_hup)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    watch_pid_path(root).parent.mkdir(parents=True, exist_ok=True)
    watch_pid_path(root).write_text(f'{os.getpid()}\n')
    try:
        while True:
            hup['flag'] = False
            try:
                if not active_lanes(root):
                    print('lane-watch: no active lanes', file=sys.stderr)
                    return
                catch_up(root)
                lanes = active_lanes(root)
                if not lanes:
                    print('lane-watch: no active lanes', file=sys.stderr)
                    return
                subs = subscriptions_for(lanes)
                if once and not subs:
                    return
                try:
                    if subs:
                        run_socket(root, subs, once=once)
                    else:
                        time.sleep(TICK_SECONDS)
                        catch_up(root)
                except (ConnectionError, FileNotFoundError, OSError, LaneError) as exc:
                    print(f'lane-watch: {exc}', file=sys.stderr)
                    if once:
                        return
                    time.sleep(TICK_SECONDS)
                if once:
                    return
            except InterruptedError:
                continue
    finally:
        path = watch_pid_path(root)
        try:
            if path.is_file() and path.read_text().strip() == str(os.getpid()):
                path.unlink()
        except OSError:
            pass


def main(argv):
    if os.environ.get('HERDR_ENV') != '1':
        die('Run Crew inside a herdr-managed pane (HERDR_ENV=1).')
    if len(argv) < 2 or argv[1] in ('-h', '--help'):
        die('Usage: bin/lane assign|cancel|watch|reconcile ...')
    command, rest = argv[1], argv[2:]
    if command == 'assign':
        cmd_assign(ROOT, rest)
    elif command == 'cancel':
        cmd_cancel(ROOT, rest)
    elif command == 'watch':
        cmd_watch(ROOT, rest)
    elif command == 'reconcile':
        cmd_reconcile(ROOT, rest)
    else:
        die(f'Unknown lane command: {command}')


if __name__ == '__main__':
    main(sys.argv)
