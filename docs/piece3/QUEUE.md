# Piece 3 Queue

Only one packet may be `in_progress`. Packets are sequential because they share
the lifecycle implementation.

| Packet | Status | Depends on | Scope |
|---|---|---|---|
| [01](packet-01-runtime-locking.md) | done | none | Runtime anchoring and start serialization |
| [02](packet-02-process-identity.md) | done | 01 | Strong process identity and safe termination |
| [03](packet-03-lease-scope.md) | done | 02 | Frozen identity and exact lease cleanup |
| [04](packet-04-control-protocol.md) | done | 03 | Atomic drain/resume protocol |
| [05](packet-05-startup-rollback.md) | done | 04 | Transactional detached startup |
| [06](packet-06-status-recovery.md) | done | 05 | Status, fallback, and orphan recovery |
| [07](packet-07-lifecycle-acceptance.md) | done | 06 | End-to-end lifecycle acceptance |
| [08](packet-08-gui-policy.md) | done | 07 | Safe Gandalf button policy |
| [09](packet-09-async-io.md) | done | 08 | Asynchronous catalog and log I/O |
| [10](packet-10-final-verification.md) | done | 09 | Final verification and documentation audit |

Status values: `blocked`, `ready`, `in_progress`, `done`, `blocked_external`.

## Transition Rule

After a packet passes all required checks:

1. Set its status to `done`.
2. Set the immediately following packet to `ready`.
3. Do not start the following packet in the same session.

If a packet cannot finish safely, set it to `blocked_external`, fill its Result
with the exact blocker, and do not unlock later packets.
