# Access beyond ownership: Stock Connect closures and price delay in Chinese stocks

**Authors:** Sun, Kang (Han Sun and Hyoung-Goo Kang)  
**Status:** Working paper, not yet submitted

This private repository contains the working paper, its Online Appendix, research code, preregistrations, and aggregate results. The paper title is transcribed from the main PDF's first page. Both PDFs are the latest filename-dated versions available at packaging time: 8 November 2026, 07:00. The PDFs are unchanged.

## Repository layout

- `paper/`: main manuscript and Online Appendix PDFs.
- `replication/`: baseline code, `run_all.sh`, `REPRODUCE.md`, `PREREGISTRATION.md`, `requirements.lock`, aggregate `tables/`, `sample_by_event.csv`, `balance.csv`, and `data_scale.csv`.
- `replication/RESULTS_internal_zh.md`: the original baseline internal Chinese results memo, renamed for clarity; it is not the packaging report.
- `replication/R2/` through `replication/R8/`, including `R3b/`: each round's code, preregistration, aggregate tables, original runner, environment lock, and reproduction notes. Original `PREREGISTRATION_R*.md` filenames are retained, with identical `PREREGISTRATION.md` aliases. Available historical preregistrations and amendments are retained separately.
- `FILE_MANIFEST.csv`: relative filename, exact byte size, and SHA-256 for every supplied file except the manifest itself.
- `EXCLUDED_FILES.md`: exclusions and distribution policy.
- `push_to_github.sh`: manual authenticated creation/push to a **private** GitHub repository.

## Data access and local path conventions

QDC, L2, CCASS, and HKEX licensed or restricted data are **not distributed** with this repository. No security-level holdings, frozen feature panels, raw partitions, matching links, direct provider daily flow/turnover series, contract-level source series, archives, or caches are included. Aggregate estimates, distributions, coverage counts, and public event-calendar summaries are supplied. Data rights remain with the respective providers.

To reproduce the estimates:

1. Obtain the required access from QDC and the relevant CCASS/HKEX and market-data providers through your own institutional agreements. Obtain historical A-share minute/daily prices, point-in-time ownership/eligibility, valuation/ST/holder/analyst controls, and IF/IH contract minute records. R3 additionally requires authorized L2 orders/trades/queues. Later rounds require the auxiliary Hong Kong, holiday, weather, and fund-flow sources identified in their `REPRODUCE.md` and source-fetching scripts. Do not place account details in this repository.
2. Download the authorized historical partitions using the providers' supported export process. Preserve provider column names, exchange suffixes, historical timestamps, disclosure availability dates, and the input vintage. The original baseline notes freeze the observed market-data endpoint at 2026-10-30. Fetching a current replacement is not proof of an identical historical snapshot.
3. Make the original read-only mounts available, or adapt the path constants in a local copy of the code. The scripts retain these original data conventions:

   | Input | Original local convention |
   | --- | --- |
   | QDC tables | `/Volumes/Extreme SSD/QDC/data/QDCData/`, including `cn_daily_full/full`, `stocks_1m/full`, `cn_hsgt/hk_hold/full`, `cn_valuation_1d/full`, `cn_st/full`, and `cn_top_holders/top10/full` |
   | A-share minute annual archives | `/Volumes/Extreme SSD/T9/codex项目/A股分钟线+日频量价/A股分钟数据/1m_price_zip/{2017..2026}.zip` |
   | IF/IH minute archive | `/Volumes/T9/期货1分钟2004~2608/CFFEX.7z` (read only) |
   | L2 inputs | `/Volumes/Extreme SSD/QDC/L2/` and its `raw/` subdirectory, as requested by the round's code |
   | R3 supplemental futures ticks | `/Volumes/T9/FutureTickV3/2026-自然日/202609.7z` (read only) |
   | Per-round scratch | `/Volumes/Extreme SSD/T9/_tmp/266`, `272`, `277`, `282`, `283`, `284`, `285`, `287`, and `288` |

   Restricted inputs and derived panels must remain outside version control. Any local `data/`, `raw/`, `cache/`, and `meta/` folders and supported binary/archive formats are ignored. Write extracted/intermediate files to task-specific scratch on the writable T9 volume, not to `/Volumes/T9`.
4. Restore the matching local frozen `meta/` directories and original source snapshots from your authorized research archive before running. They are intentionally outside this distribution allowlist. The baseline entrypoint requires, among other files, `meta/literature_gate.json`, `meta/frozen_input_cutoff.json`, `meta/input_manifest.json`, and the official-source receipts/snapshots; other rounds also use local freeze records and may reuse baseline scratch. Do not fabricate a gate or update historical freezes to make a run pass. The included fetch scripts document official-source acquisition, but a fresh download cannot guarantee the original version. Some R3 diagnostics additionally reference locally held `l2_diag`/`l2_closestale` helper sources; see `EXCLUDED_FILES.md` for omitted source-derived validation fixtures.

## Reproduction commands

Prerequisites are Python 3.12, `uv`, `7zz`, and the dependencies pinned in the relevant `requirements.lock`. R3 also compiles C++17 code and uses the original macOS/Homebrew libarchive setup. Consult each round's reproduction notes for its platform and input requirements.

After staging licensed inputs and the matching frozen metadata, run the original baseline entrypoint from the repository root:

```bash
bash replication/run_all.sh
```

To run the baseline and all supplied rounds sequentially with the same prerequisites staged:

```bash
for round in . R2 R3 R3b R4 R5 R6 R7 R8; do
  bash "replication/${round}/run_all.sh" || exit "$?"
done
```

The scripts set numerical-library threads to one and retain their original process/memory controls. Large intermediates are cleaned by the original runners unless `KEEP_INTERMEDIATES=1` is set. Review the documented scratch dependencies before cleaning between rounds.

**Packaging validation only:** no regression, estimation, manuscript editing, or scientific review was performed for this delivery. The commands above are conditional reproduction instructions; a fresh clone alone cannot run the estimates without licensed inputs and the excluded frozen metadata. All supplied scientific code, preregistrations, results, and PDFs retain their original bytes. Original external-data and diagnostic-helper paths are documented rather than silently remapped.

## Private GitHub delivery

This package is intended only for a private repository. After GitHub CLI is available on M5, run `bash push_to_github.sh`. The script requests browser authentication when needed, then creates `connect-closed-replication` privately, or `connect-closed-replication-2026` if the first name exists. It checks visibility and prints the repository URL. A private URL is accessible only to collaborators who already have permission; the script does not grant access or publish a public link.
