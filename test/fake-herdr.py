#!/usr/bin/env python3
"""Test-only herdr boundary. Real Git handles all worktree operations."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

root = Path(os.environ['CREW_TEST_RUNTIME'])
args = sys.argv[1:]
with (root / 'calls.jsonl').open('a') as f:
    f.write(json.dumps(args) + '\n')

def option(flag):
    return args[args.index(flag) + 1]

def emit(result):
    print(json.dumps({'result': result}))

def fail(code):
    print(json.dumps({'error': {'code': code, 'message': code}}), file=sys.stderr)
    sys.exit(1)

def git(*words):
    return subprocess.check_output(['git', *words], text=True, stderr=subprocess.PIPE).strip()

def read_task(name):
    return json.loads((root / (name + '.json')).read_text())

def write_task(name, data):
    (root / (name + '.json')).write_text(json.dumps(data))

def response(data):
    return {'workspace': {'workspace_id': data['workspace'], 'worktree': {'checkout_path': data['path']}},
            'root_pane': {'pane_id': data['pane']}, 'worktree': {'path': data['path']}}

if args == ['integration', 'status']:
    for kind in ['claude', 'grok', 'codex', 'pi']:
        print(f'{kind}: {"outdated" if os.environ.get("CREW_TEST_OUTDATED") else "current"} (v1)')
elif args[:2] in (['worktree', 'create'], ['worktree', 'open']):
    name = option('--label')
    path, project = option('--path'), option('--cwd')
    if args[1] == 'create':
        if os.environ.get('CREW_TEST_CREATE_FAIL'):
            fail('create_failed')
        git('-C', project, 'worktree', 'add', '-b', option('--branch'), path, option('--base'))
    data = {'path': path, 'project': project, 'workspace': f'opaque-{name}', 'pane': f'opaque-{name}:pane-9', 'state': 'gone'}
    write_task(name, data)
    if os.environ.get('CREW_TEST_CREATE_CRASH'):
        fail('lost_response_after_creation')
    emit(response(data))
elif args[:2] == ['workspace', 'get']:
    name = args[2].removeprefix('opaque-')
    data = read_task(name)
    if os.environ.get('CREW_TEST_WRONG_WORKSPACE'):
        data['path'] = '/unrelated/checkout'
    emit(response(data))
elif args[:2] == ['pane', 'run']:
    name = args[2].split(':')[0].removeprefix('opaque-')
    data = read_task(name)
    data['shell_command'] = args[3]
    write_task(name, data)
    emit({})
elif args[:2] == ['agent', 'start']:
    name = args[2]
    data = read_task(name)
    data['state'] = 'blocked' if os.environ.get('CREW_TEST_START_BLOCKED') else 'idle'
    write_task(name, data)
    if data['state'] == 'blocked':
        fail('agent_not_ready')
    emit({})
elif args[:2] == ['agent', 'get']:
    try:
        data = read_task(args[2])
    except FileNotFoundError:
        fail('agent_not_found')
    if os.environ.get('CREW_TEST_SERVER_DOWN'):
        fail('connection_failed')
    if data['state'] == 'gone':
        fail('agent_not_found')
    emit({'agent': {'agent_status': data['state'], 'pane_id': data['pane'], 'workspace_id': data['workspace']}})
elif args[:2] == ['agent', 'prompt']:
    if '--wait' in args:
        fail('forbidden_wait')
    data = read_task(args[2])
    if os.environ.get('CREW_TEST_PROMPT_FAIL'):
        fail('transport_error')
    data['state'] = 'working'
    data.setdefault('prompts', []).append(args[3])
    write_task(args[2], data)
    emit({})
elif args[:2] == ['worktree', 'remove']:
    name = option('--workspace').removeprefix('opaque-')
    data = read_task(name)
    if os.environ.get('CREW_TEST_REMOVE_FAIL'):
        fail('remove_failed')
    words = ['-C', data['project'], 'worktree', 'remove']
    if '--force' in args:
        words.append('--force')
    git(*words, data['path'])
    (root / (name + '.json')).unlink()
    emit({'path': data['path']})
else:
    fail('unexpected_command')
