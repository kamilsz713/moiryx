# Macierz śledzenia wymagań

Macierz wiąże kryteria akceptacji z pełnej specyfikacji z ticketami i
konkretnymi testami. Zestaw uruchamia się przez
`python -m pytest -m acceptance -q`; jest deterministyczny i nie wymaga sieci.

| Kryterium | Odpowiedzialne tickety | Minimalny dowód automatyczny |
|---|---|---|
| AC1 — tekstowy agent bez tooli | MRYX-203, MRYX-403 | `test_dogfood_text_agent` |
| AC2 — built-in tool loop | MRYX-403, MRYX-702 | `test_dogfood_coding_agent_reads_and_edits_file` |
| AC3 — custom `@tool` | MRYX-301–MRYX-303, MRYX-403 | `test_dogfood_custom_tool_integration` |
| AC4 — bezpośredni Pydantic output | MRYX-501, MRYX-502 | `test_structured_agent_call_returns_declared_model` |
| AC5 — nested output | MRYX-202, MRYX-502 | `test_dogfood_nested_reviewer`, `test_valid_final_call_returns_exact_nested_pydantic_model` |
| AC6 — ostatnia wiadomość tekstowa | MRYX-403, MRYX-404 | `test_tool_result_is_sent_in_order_before_later_final_content` |
| AC7 — alias modelu | MRYX-104, MRYX-203 | `test_dogfood_switches_provider_by_config_only` |
| AC8 — slash w model ID | MRYX-104, MRYX-602, MRYX-801 | `test_resolve_preserves_provider_model_generation_and_options` |
| AC9 — concurrency | MRYX-406 | `test_same_agent_keeps_messages_and_repair_counters_per_run` |
| AC10 — brak JSON-from-text | MRYX-503 | `test_plain_markdown_json_is_never_parsed_as_the_result` |
| AC11 — repair bez zgadywania | MRYX-305–MRYX-307, MRYX-403 | `test_dogfood_unknown_tool_requires_a_corrected_call`, `test_invalid_call_blocks_every_tool_before_side_effect` |

## Kontrakty przekrojowe

| Kontrakt | Tickety | Dowód |
|---|---|---|
| publiczne API ma tylko `Agent` i `tool` | MRYX-001, MRYX-203, MRYX-301 | test importów i publiczny przykład |
| konfiguracja używa nazw Moiryx | MRYX-101, MRYX-1104 | config discovery tests oraz repo-wide name check |
| eager validation | MRYX-103, MRYX-104, MRYX-201–MRYX-203, MRYX-504 | testy konstruktora bez model requestu |
| provider-agnostic core | MRYX-401, MRYX-601, MRYX-801, MRYX-901, MRYX-1001 | `test_request_mapping_is_minimal_and_preserves_message_protocol` + adapter contract suite |
| bezpieczne filesystem tools | MRYX-701–MRYX-706 | `test_workspace_guard_blocks_directory_symlink_escape`, `test_edit_replace_failure_keeps_original_and_cleans_temporary_file`, `test_shell_timeout_terminates_child_process` |
| retry budgets są niezależne | MRYX-307, MRYX-405, MRYX-503 | `test_provider_tool_and_structured_retry_budgets_are_independent` |
| cancellation | MRYX-303, MRYX-406 | anulowanie provider/tool/subprocess task |
| sekrety nie trafiają do diagnostyki | MRYX-103, MRYX-1103 | `test_raw_response_requires_explicit_debug_and_is_redacted` + `test_agent_applies_trace_configuration_and_secret_redaction` |
| build bez kluczy i sieci | MRYX-402, MRYX-603, MRYX-1105 | mock suite + `test_ci_matrix_runs_quality_build_and_clean_install_smoke` + jawnie pomijany `test_local_openai_compatible_text_smoke` |

## Coverage według dokumentów

- Kontrakt publiczny: [01-vision-and-contract.md](01-vision-and-contract.md),
  E0/E2/E4/E5.
- Granice architektury: [02-architecture.md](02-architecture.md),
  MRYX-004, MRYX-106, MRYX-401.
- Config i agent files:
  [03-configuration-and-agents.md](03-configuration-and-agents.md), E1/E2.
- Tools, repair, runtime i output:
  [04-tools-runtime-and-output.md](04-tools-runtime-and-output.md), E3/E4/E5/E7.
- Adaptery: [05-providers.md](05-providers.md), E6/E8/E9/E10.
- Jakość i release:
  [06-quality-security-release.md](06-quality-security-release.md), E11.

## Reguła zamknięcia v0.1

Release ticket MRYX-1107 nie może zostać zamknięty, jeżeli dowolny wiersz
AC1–AC11 nie ma przechodzącego testu lub jeżeli którykolwiek kontrakt
przekrojowy jest oznaczony jako niesprawdzony. Ręczny test live uzupełnia, ale
nie zastępuje deterministycznej suite na fake/mock providerach.
