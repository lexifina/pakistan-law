"""Print a Pakistani law, or one section or Article of it, as this repository has it on a date.

    python tools/in_force_on.py 2026-10-28 ordinances/1962/copyright-ordinance                 # the whole law
    python tools/in_force_on.py 2026-10-28 ordinances/1962/copyright-ordinance section-57      # one section
    python tools/in_force_on.py 2026-10-28 constitution/1973/constitution-of-the-islamic-republic-of-pakistan article-25A

Reads the `In-force:` trailer (falling back to `Consolidated:`). The Pakistan Code keeps only the current text, so a
date before a law's first commit has no version here: the record starts on the day the text was retrieved.
Standard library only.
"""
import subprocess
import sys


def git(*args: str) -> str:
    return subprocess.run(['git', *args], capture_output=True, text=True, encoding='utf-8', check=True).stdout


def commit_on(day: str, path: str) -> tuple[str | None, str | None]:
    """The last commit on or before `day` that touched `path`, and the earliest date known for it."""
    fmt = '%H%x1f%(trailers:key=In-force,valueonly,separator=)%x1f%(trailers:key=Consolidated,valueonly,separator=)'
    earliest = None
    for line in git('log', '--first-parent', f'--format={fmt}', 'main', '--', path).splitlines():
        h, inforce, consolidated = (line.split('\x1f') + ['', ''])[:3]
        d = (inforce or consolidated).strip()
        if not d:
            continue
        earliest = d
        if d <= day:
            return h, d
    return None, earliest


def main() -> None:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')  # the laws use dashes and quotes outside the console code page
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    day, law = sys.argv[1], sys.argv[2].strip('/')
    unit = sys.argv[3] if len(sys.argv) > 3 else None
    if unit and unit.endswith('.md'):
        unit = unit[:-3]
    path = f'{law}/{unit}.md' if unit else law
    h, earliest = commit_on(day, path)
    if not h:
        if earliest:
            sys.exit(f'{path}: no version on or before {day}; the record starts at {earliest}, the day the Pakistan '
                     'Code text was retrieved (the site keeps no earlier text)')
        sys.exit(f'{path}: not found')
    if unit:
        sys.stdout.write(git('show', f'{h}:{path}'))
        return
    try:
        names = [n for n in git('show', f'{h}:{law}/index.txt').splitlines() if n and n != 'notes.md']
    except subprocess.CalledProcessError:
        names = sorted(n.rsplit('/', 1)[-1] for n in git('ls-tree', '--name-only', h, f'{law}/').split())
    for n in names:
        sys.stdout.write(git('show', f'{h}:{law}/{n}') + '\n')


if __name__ == '__main__':
    main()
