# Excluded files and distribution policy

Excluded directories include all `data/`, `raw/`, `cache/`, `logs/`, and `.git/` trees. Original `meta/` data, frozen source snapshots, acquisition responses, and unrelated source-project files are not copied. Only selected historical preregistration Markdown files from `meta/` are included under `preregistration_history/`. Manuscript DOCX files and older PDFs are excluded because only the latest PDFs were requested. Apple metadata, bytecode, archives, binary panels, credential-like files, and links are not distributed. Credential-like files, if encountered, are excluded by filename without opening their contents.

The source contains tables that are not aggregate results. The files below are excluded conservatively, even where a small reference or audit table might itself contain only public information. Files at or above 50,000,000 bytes are excluded before content reading. Per-security numeric source fixtures in two optional R3 validation scripts and the compiled R3 scanner are also excluded; scanner C++ sources remain included.

All source data needed to regenerate excluded intermediate/result panels must be acquired and staged locally by an authorized researcher. Frozen acquisition metadata is also needed to reproduce an identical vintage.

| Source-relative file | Bytes | Reason |
| --- | ---: | --- |
| `R2/tables/AH_historical_roster_unmatched.csv` | 5 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R2/tables/AH_listing_history.csv` | 63638 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R2/tables/frozen_features_by_event.csv` | 67290121 | file at least 50 MB |
| `R2/tables/futures_contract_selection.csv` | 189443 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R2/tables/futures_daily_volume.csv` | 535952 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R2/tables/matching_pairs.csv` | 19938709 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R2/tables/matching_pairs_without_industry.csv` | 9106926 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R2/tables/reopening_backlog_sample.csv` | 61143303 | file at least 50 MB |
| `R3/code/scan` | 122840 | compiled executable; source files are supplied |
| `R3/code/validate_native.py` | 1712 | optional validation contains source-derived per-security numeric fixtures |
| `R3/code/validate_parser_extension.py` | 4913 | optional validation contains a source-derived order example |
| `R3/tables/frozen_features.csv` | 20868172 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R3/tables/futures_contract_selection.csv` | 223113 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R3/tables/futures_daily_volume.csv` | 535952 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R3/tables/futures_tick_contract_selection.csv` | 5308 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R3/tables/futures_tick_daily_contract_volume.csv` | 7880 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R3/tables/futures_tick_prior_volume_rank_validation.csv` | 199 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R3/tables/matches.csv` | 2121202 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R3/tables/winsor_thresholds_daily.csv` | 397919111 | file at least 50 MB |
| `R3/tables/winsor_thresholds_flow.csv` | 3775056 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R3b/tables/futures_contract_selection.csv` | 189443 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R3b/tables/futures_daily_volume.csv` | 535952 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R4/tables/bshare_issuer_links.csv` | 2428 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R4/tables/first_holder_classified_records.csv` | 18972 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R4/tables/first_holder_freeze_audit.csv` | 38014 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R4/tables/frozen_features_by_event.csv` | 448481792 | file at least 50 MB |
| `R4/tables/global_index_inventory.csv` | 392 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R4/tables/hk_daily_index_sources.csv` | 321 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R4/tables/hk_etf_candidate_coverage.csv` | 497 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R4/tables/hk_etf_daily_choice.csv` | 264339 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R4/tables/international_annual_sources.csv` | 7308885 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R4/tables/minute_exposure_independent_checks.csv` | 3400 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R6/tables/exposure_by_event.csv` | 7179251 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R6/tables/exposure_event_latest.csv` | 17069742 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R6/tables/exposure_timing_sensitivity.csv` | 28492460 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R6/tables/exposure_window_freeze_by_event.csv` | 5911762 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R6/tables/futures_contract_selection.csv` | 189443 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R6/tables/futures_daily_volume.csv` | 535952 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R7/tables/US_AH_timing_audit.csv` | 730 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R7/tables/futures_contract_selection.csv` | 208407 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R7/tables/futures_daily_volume.csv` | 611708 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R7/tables/global_index_inventory.csv` | 492 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R7/tables/hk_daily_index_sources.csv` | 349 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R7/tables/hkex_north_turnover_available.csv` | 2134 | direct provider daily flow/turnover or market input series; not an aggregate research result |
| `R7/tables/qdc_field_regime_transition.csv` | 2115 | direct provider daily flow/turnover or market input series; not an aggregate research result |
| `R7/tables/qdc_hkex_recent_scale_validation.csv` | 4127 | direct provider daily flow/turnover or market input series; not an aggregate research result |
| `R7/tables/qdc_moneyflow_raw_window.csv` | 48219 | direct provider daily flow/turnover or market input series; not an aggregate research result |
| `R7/tables/us58_moneyflow_daily_windows.csv` | 54043 | direct provider daily flow/turnover or market input series; not an aggregate research result |
| `R8/tables/futures_contract_selection.csv` | 208407 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R8/tables/futures_daily_volume.csv` | 611708 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `R8/tables/market_daily_windows.csv` | 64128 | direct provider daily flow/turnover or market input series; not an aggregate research result |
| `R8/tables/sync_1min_four_coarse_missing_rows.csv` | 374 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `tables/exposure_by_event.csv` | 17668836 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `tables/futures_contract_selection.csv` | 189443 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
| `tables/futures_daily_volume.csv` | 535952 | nonaggregate security/contract-level observations, matching links, or source records (conservative exclusion) |
