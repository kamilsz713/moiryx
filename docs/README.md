# Moiryx documentation

The documents here describe the current alpha contract and its implementation.
The [specification](specification.md) is a concise contract; focused chapters
carry the details. The previous, longer planning draft is available in Git
history but is not maintained as a second source of truth.

## Naming

| Purpose | Name |
| --- | --- |
| Package and Python import | `moiryx` |
| Configuration file | `moiryx.yaml` |
| Configuration path override | `MOIRYX_CONFIG` |
| Default trace directory | `.moiryx/runs` |
| Base exception | `MoiryxError` |
| Internal final tool | `__moiryx_submit_result` |
| Tool decorator metadata | `__moiryx_tool__` |

## Reading map

- [Vision and public contract](01-vision-and-contract.md)
- [Architecture](02-architecture.md)
- [Configuration and agent definitions](03-configuration-and-agents.md)
- [Tools, runtime, and structured output](04-tools-runtime-and-output.md)
- [Provider adapters](05-providers.md)
- [Quality, security, and release](06-quality-security-release.md)
- [Architecture decisions](decisions.md)
- [Roadmap](roadmap.md) and [ticket backlog](tickets/README.md)
- [Acceptance traceability](traceability.md) and [risks](risks.md)
- [Alpha release notes](release-notes-alpha.md)

For a contract change, update the specification and the relevant focused
chapter, add or supersede an ADR when the decision changes, and update tests.
A ticket can narrow implementation scope but cannot silently change the public
API or security behavior. `Done` requires implementation, relevant tests,
lint/type checks, and current documentation.
