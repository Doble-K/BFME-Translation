# Packet 09: Asynchronous Gandalf I/O

Status: `blocked` until Packet 08 is done.

## Goal

Establish that catalog parsing and bounded log reads never block the Tk thread.

## Invariant

Farm status/catalog work and log filesystem reads execute in worker threads;
widget updates return through `root.after(0, ...)`.

## Allowed Context

- `gandalf.py`: lines 44-65, 1427-1505, 1556-1613.
- `tools/localization/watch_progress.py`: lines 53-102.
- `tests/test_localization_tools.py`: lines 889-952 and 2516-2536.
- Packet 08 Result, queue files, and this packet.

Relevant symbols: `refresh_farm_status`, `open_farm_logs`, `read_log_tail`,
`progress_snapshot`, `catalog_progress_snapshot`.

Do not launch Tk. Do not move widget access into a worker. A small injectable or
module-level helper is allowed when needed for direct testing.

## Focused Verification

Retain the existing bounded-tail test and add the smallest direct tests needed for
the worker boundary. Run only those tests plus:

```bash
python3 -m unittest \
tests.test_localization_tools.LocalizationToolTests.test_gandalf_reads_only_the_requested_log_tail \
tests.test_localization_tools.LocalizationToolTests.test_watch_progress_reports_effective_queue_percentage
python3 -m py_compile gandalf.py tools/localization/watch_progress.py
```

## Exit Criteria

- Catalog parsing and log reads are proven off the initiating Tk callback path.
- Each log read remains bounded to the configured 64 KiB maximum.
- No Tk method is called by worker code.
- Update Result and unlock Packet 10.

## Result

Pass. Farm status catalog work is dispatched through `start_gandalf_worker`,
and completion returns through `root.after(0, ...)` before touching widgets.
Log reads remain in the existing worker thread and use the bounded 64 KiB tail
reader. The direct worker-boundary test confirms work runs off the initiating
thread without launching Tk.

Focused verification passed:

```text
Ran 3 tests in 0.043s
OK
```

`python3 -m py_compile gandalf.py tools/localization/watch_progress.py` also
passed.
