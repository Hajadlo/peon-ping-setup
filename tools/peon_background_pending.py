"""Exit 0 only for a Claude Stop with known unfinished background commands."""
import json
from pathlib import Path
import re
import sys


def background_pending(transcript):
    pending = set()
    cancellations = {}
    for line in transcript:
        row = json.loads(line)
        if row.get('subtype') == 'compact_boundary':
            # Compaction can remove completion records. Do not retain stale jobs.
            pending.clear()
            cancellations.clear()
        if row.get('isSidechain'):
            continue
        result = row.get('toolUseResult')
        if isinstance(result, dict) and result.get('backgroundTaskId'):
            pending.add(result['backgroundTaskId'])
        content = row.get('message', {}).get('content', [])
        blocks = [{'type': 'text', 'text': content}] if isinstance(content, str) else content
        for block in blocks:
            if block.get('type') == 'tool_use' and block.get('name') == 'TaskStop':
                cancellations[block['id']] = block.get('input', {}).get('task_id')
            if block.get('type') == 'tool_result' and not block.get('is_error'):
                pending.discard(cancellations.get(block.get('tool_use_id')))
            if row.get('type') == 'user' and block.get('type') == 'text':
                for notification in re.findall(r'<task-notification>(.*?)</task-notification>', block.get('text', ''), re.S):
                    task = re.search(r'<task-id>(.*?)</task-id>', notification)
                    status = re.search(r'<status>(.*?)</status>', notification)
                    if task and status and status[1].strip() in ('completed', 'failed', 'killed', 'stopped'):
                        pending.discard(task[1].strip())
    return bool(pending)


def main():
    try:
        event = json.load(sys.stdin)
        if event.get('hook_event_name') != 'Stop' or not event.get('transcript_path'):
            return 1
        with Path(event['transcript_path']).open() as transcript:
            return 0 if background_pending(transcript) else 1
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        # Unknown or incomplete transcripts must not mute a legitimate completion.
        return 1


if __name__ == '__main__':
    sys.exit(main())
