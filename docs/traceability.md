# Acceptance traceability

Run `python -m pytest -m acceptance -q` for deterministic, offline AC1–AC11
checks. Live provider tests supplement this suite but do not replace it.

| Criterion | Tickets | Automated evidence |
| --- | --- | --- |
| AC1: text agent without tools | MRYX-203, 403 | `test_dogfood_text_agent` |
| AC2: built-in tool loop | MRYX-403, 702 | `test_dogfood_coding_agent_reads_and_edits_file` |
| AC3: custom `@tool` | MRYX-301–303, 403 | `test_dogfood_custom_tool_integration` |
| AC4: direct Pydantic result | MRYX-501, 502 | `test_structured_agent_call_returns_declared_model` |
| AC5: nested result | MRYX-202, 502 | `test_dogfood_nested_reviewer` |
| AC6: final text after tools | MRYX-403, 404 | `test_tool_result_is_sent_in_order_before_later_final_content` |
| AC7: model alias switch | MRYX-104, 203 | `test_dogfood_switches_provider_by_config_only` |
| AC8: slash in model ID | MRYX-104, 602, 801 | `test_resolve_preserves_provider_model_generation_and_options` |
| AC9: concurrent runs | MRYX-406 | `test_same_agent_keeps_messages_and_repair_counters_per_run` |
| AC10: no JSON-from-text fallback | MRYX-503 | `test_plain_markdown_json_is_never_parsed_as_the_result` |
| AC11: repair without guessing | MRYX-305–307, 403 | `test_dogfood_unknown_tool_requires_a_corrected_call`, `test_invalid_call_blocks_every_tool_before_side_effect` |

Cross-cutting checks cover eager construction, provider-neutral requests,
workspace path safety, independent retry budgets, cancellation, secret
redaction, and clean package builds. See the relevant unit tests and
[`06-quality-security-release.md`](06-quality-security-release.md).

Do not close release ticket MRYX-1107 if any AC row lacks a passing test or a
cross-cutting safety requirement is unverified.
