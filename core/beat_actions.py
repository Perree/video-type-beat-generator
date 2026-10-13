"""Validate channel slugs and fail closed unless the Environment allows only master."""
import json
import os
import re
import urllib.request
from core.beat_notion import NoRedirect

TRUSTED_REPOSITORY = 'Perree/video-type-beat-generator'


def check_context(env=None):
    env = os.environ if env is None else env
    if (env.get('GITHUB_REPOSITORY') != TRUSTED_REPOSITORY
            or env.get('GITHUB_REF') != 'refs/heads/master'
            or env.get('GITHUB_EVENT_NAME') not in ('schedule', 'workflow_dispatch')):
        raise ValueError('untrusted_actions_context')


def bind_channel(channel, slug):
    matrix(json.dumps([slug]))
    if channel.get('actions_slug') != slug:
        raise ValueError('environment_channel_mismatch')


def matrix(raw):
    channels = json.loads(raw)
    if (type(channels) is not list or not 1 <= len(channels) <= 100
            or any(type(ch) is not str or not re.fullmatch('[a-z][a-z0-9-]{0,39}', ch) for ch in channels)
            or len(set(channels)) != len(channels)):
        raise ValueError('invalid_beats_matrix')
    return [{'channel': ch} for ch in channels]


def check_environment(env=None, opener=None):
    env = os.environ if env is None else env
    check_context(env)
    slug = matrix(json.dumps([env['BEAT_SLUG']]))[0]['channel']
    repo = env['GITHUB_REPOSITORY']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise ValueError('invalid_repository')
    base = f'https://api.github.com/repos/{repo}/environments/type-beats-{slug}'
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    def read(url):
        # Public repo: anonymous GET works without granting Actions read.
        # Private repo: fail closed rather than broadening contents: read.
        request = urllib.request.Request(url, headers={
            'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'})
        with opener.open(request, timeout=15) as response:
            if response.status != 200:
                raise ValueError('environment_unverified')
            return json.loads(response.read(1_000_001))
    policy = read(base).get('deployment_branch_policy')
    if policy != {'protected_branches': False, 'custom_branch_policies': True}:
        raise ValueError('environment_master_restriction_required')
    rules = read(base + '/deployment-branch-policies?per_page=100')
    rows = rules.get('branch_policies', [])
    if (rules.get('total_count') != 1 or len(rows) != 1 or rows[0].get('name') != 'master'
            or rows[0].get('type') != 'branch'):
        raise ValueError('environment_master_restriction_required')


def main():
    try:
        if os.environ.get('BEAT_ACTIONS_MODE') == 'matrix':
            check_context()
            print('matrix=' + json.dumps(matrix(os.environ['BEAT_CHANNELS']), separators=(',', ':')))
        else:
            check_environment()
        return 0
    except Exception:
        print('type_beats_actions_validation_failed')
        return 1
