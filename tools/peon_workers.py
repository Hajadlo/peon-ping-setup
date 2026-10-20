"""Identify automated CLI workers and their repositories using process metadata."""
from functools import lru_cache
from pathlib import Path


def headless_worker(args):
    if not args:
        return False
    executable = Path(args[0]).name
    return ((executable == 'codex' and len(args) > 1 and args[1] == 'exec') or
            (executable == 'claude' and any(arg in ('--print', '-p') for arg in args[1:])))


@lru_cache(maxsize=512)
def git_directory(directory):
    """A linked worktree and its main checkout share one Git common directory."""
    directory = Path(directory).resolve()
    for candidate in (directory, *directory.parents):
        git = candidate / '.git'
        try:
            if git.is_file():
                value = git.read_text().strip()
                if not value.startswith('gitdir: '):
                    return None
                git = (candidate / value[8:]).resolve()
            elif not git.is_dir():
                continue
            common = git / 'commondir'
            return (git / common.read_text().strip()).resolve() if common.exists() else git.resolve()
        except (OSError, ValueError):
            return None
    return None


def active_worker_repositories(proc_root=Path('/proc')):
    repositories = set()
    try:
        processes = list(proc_root.iterdir())
    except OSError:
        return repositories
    for proc in processes:
        if not proc.name.isdigit():
            continue
        try:
            args = proc.joinpath('cmdline').read_bytes().decode(errors='replace').split('\0')
            if not headless_worker(args):
                continue
            if Path(args[0]).name == 'claude':
                # T3 keeps its Claude protocol process alive between turns. Its
                # liveness is represented by run state, not by the daemon PID.
                try:
                    parent_id = next(line.split()[1] for line in proc.joinpath('status').read_text().splitlines()
                                     if line.startswith('PPid:'))
                    parent_args = (proc_root / parent_id / 'cmdline').read_bytes().decode(errors='replace').split('\0')
                    if Path(parent_args[0]).name in ('t3', 't3-code'):
                        continue
                except (OSError, StopIteration, IndexError):
                    pass
            # Short T3 title-generation jobs are not user work.
            if '--ephemeral' in args and '--output-schema' in args:
                schema = Path(args[args.index('--output-schema') + 1])
                if any(part.startswith('t3code-codex-schema-') for part in (schema.name, schema.parent.name)):
                    continue
            repository = git_directory(proc.joinpath('cwd').resolve(strict=True))
            if repository is not None:
                repositories.add(repository)
        except (OSError, ValueError, IndexError):
            # Processes can disappear during a snapshot; no command text is logged.
            continue
    return repositories
