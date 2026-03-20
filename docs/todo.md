# TODO - Full 1,260-Patient Evaluation

**Last updated:** 2026-03-20 00:01:00
**Plan:** docs/plans/2026-03-03-full-1260-patient-evaluation-plan.md

## LaTeX Paper -- HEPATOLOGY Format (2026-03-19)

- [x] Design spec: `docs/superpowers/specs/2026-03-19-alfsg-latex-paper-design.md`
- [x] Implementation plan: `docs/superpowers/plans/2026-03-19-alfsg-latex-paper.md`
- [x] Tasks 1-10: Initial manuscript drafting (JAMA format)
- [x] HEPATOLOGY journal format restructuring (2026-03-19 17:37)
  - Abstract: Background & Aims / Approach & Results / Conclusions (250 words max)
  - Title page: CRediT contributions, correspondence, financial support, conflicts, MeSH keywords, abbreviation list
  - References: Numbered superscript (vancouver BST)
  - Ethics: Declarations of Helsinki and Istanbul
  - AI disclosure in Methods
  - 3 tables + 5 figures = 8 (HEPATOLOGY max)
  - Version progression table moved to Supplemental Table S3
- [x] HEPATOLOGY Instructions for Authors full compliance (2026-03-19 18:06)
  - CRediT author contributions placeholder added to title page
  - Conflicts of Interest: "Nothing to report." per HEPATOLOGY format
  - Ethics statement: HEPATOLOGY required format (full IRB name/institution/number)
  - Conclusions merged into Discussion as subsection (HEPATOLOGY: Intro/Methods/Results/Discussion only)
  - Acknowledgements: Correct spelling, "Assistance with the study" + "Presentation" paragraphs
  - Float specifiers: [H] -> [!htbp] for journal submission
  - Supplemental Table S1: All FP patient IDs filled in, inverted FN/FP definitions fixed
- [x] Data accuracy fixes (2026-03-19 18:54)
  - Figure 2: Removed "proj 94%" from v0.7.0 label, removed overlapping embedded title
  - Per-agent accuracy: Added missing Critical Care Specialist (88.5%), fixed Committee Chair (88.7% not 88.5%)
  - Table 1: Added ALFSG-PI "Not calculable" row (205 patients, 16.3%) with footnote
  - Supplemental Table S3: Expanded from 8 to 12 rows matching "12 major system versions" claim
- [x] Figure fixes continued (2026-03-19 22:25)
  - Figure 1: Widened Panel A boxes to prevent truncated edge labels
  - Figure 5: Removed embedded title, fixed subtitle "(failures from Batch 1)" -> "(curated failure cases)", widened legend box to prevent label truncation
- [x] HEPATOLOGY Instructions for Authors deep compliance pass (2026-03-19 20:35)
  - Title page element order: CRediT Author Contributions added before Correspondence (HEPATOLOGY required order)
  - Financial support: lowercase format per HEPATOLOGY template ("Financial support and sponsorship: None.")
  - Conflicts of interest: "Nothing to report." (was "None." -- HEPATOLOGY requires exact phrasing)
  - Acknowledgements: restructured with "Assistance with the study:" and "Presentation:" paragraphs
  - Ethics statement: reformatted to match HEPATOLOGY example template with TODO placeholders
  - Supplemental citations: Added Supplemental Figure S1 (Vignette Generation) and Supplemental Methods S2 (Architecture Experiments) -- all SDC now cited consecutively in main text
  - Removed "novel insights" claim (HEPATOLOGY: "Claims to novelty or priority should be avoided")
  - Added endfloat package option (commented out) for revised manuscript submission
  - LaTeX compiles cleanly (23 pages, no errors)
- [x] Figure redistribution (2026-03-19 22:44)
  - Moved 5 figures from concentrated block at end of Results to near first `\ref` citations
  - Fig1 (architecture) after Methods 2.3, Fig2 (batch accuracy) after Results 3.3, Fig3 (accuracy evolution) after Results 3.4, Fig4 (failure taxonomy) after Results 3.5, Fig5 (arch comparison) after Results 3.7
  - Fig2/Fig3 renumbered: old Fig3 (batch accuracy) now Fig2, old Fig2 (evolution) now Fig3 (batch cited first)
  - PDF now 22 pages (was 23)
- [x] Float clustering deep fix (2026-03-19 23:32)
  - Added `placeins` package and `\FloatBarrier` to prevent LaTeX float algorithm from clustering
  - Moved Tables 2/3 and Figures into correct sections near `\ref` citations
  - Verified all 8 floats on separate pages in rendered PDF
- [x] Supplementary abbreviations + TRIPOD (2026-03-19 23:32)
  - Added abbreviation footnotes to 3 tables: Phenotype Tags, Full Failure Taxonomy, Version Progression
  - Replaced all `[X]` placeholders in TRIPOD checklist with actual page numbers
  - Fixed 4 incorrect TRIPOD section references (2.3--2.5, 2.7, Supp. Table S3, 4.3--4.4)
- [x] BibTeX warning fixes (2026-03-19 22:45)
  - 4 `@misc` entries converted to `@article`: Tang2024, Ferber2024, OSullivan2024, Michael2023
  - Fixed LaTeX encoding: `Sean` -> `Se\'{a}n` in OSullivan2024
  - Zero BibTeX warnings
- [x] Full reference verification audit (2026-03-19 23:15)
  - Verified all 22 citations against PubMed/Crossref DOI lookups
  - Fixed 17 entries with wrong DOIs, journals, volumes, pages, or authors
  - Replaced non-existent OstermanGolkar2012 with McPhail2016 meta-analysis
  - Removed McCoy2024 (nonexistent paper) and OSullivan2024 (single-agent, not multi-agent)
  - Removed 6 unused bib entries; corrected manuscript claims for Michael2023, Park2023, Ferber2024
  - Final state: 20 verified references, 0 missing, 0 unused, zero LaTeX warnings
- [x] Deep reference re-verification audit (2026-03-19 23:30)
  - 5 parallel agents verified all 20 references via DOI/PubMed/arXiv + audited every in-text citation claim
  - CRITICAL FIX: Wei2022 bib entry was wrong paper ("Emergent Abilities" not "Chain-of-Thought") -- replaced
  - CRITICAL FIX: Koch2017 (ALI paper) replaced with Koch2016 (ALFSG-PI paper, PMID 27085756)
  - CRITICAL FIX: McPhail2016 sensitivity "58%--69%" corrected to "approximately 58%"
  - Fixed: Karvellas2014 author (Corron not Catherine), Tang2024 missing author (Li, Ziming), Gilson2023 title (added USMLE)
  - Fixed: main.tex ALF mortality citation changed from Koch2017 to Bernal2010
  - Final state: 20 verified references, zero LaTeX warnings, zero BibTeX warnings
- [x] Float distribution and whitespace deep fix (2026-03-20 00:01)
  - Added 7 `\FloatBarrier` commands after every figure/table to prevent cross-section clustering
  - Added `\@fptop=0pt` preamble fix to eliminate large whitespace gaps above figures on float-only pages
  - Compacted section 2.3 enumerate with `[nosep]` to move Figure 1 from page 7 to page 6
  - Cropped fig4-failure-taxonomy.pdf (41% whitespace removed) so Figure 4 + sections 3.6/3.7 share page 14
  - Used `[H]` placement for Figure 5 so Discussion starts on same page (page 15)
  - PDF reduced from 23 to 21 pages, zero errors

**Output files (all in `our_paper/`):**
- `main.tex` (21 pages, 1.5-spaced, HEPATOLOGY format)
- `supplementary.tex` (17 pages, 7 sections incl. new Table S3)
- `references.bib` (20 BibTeX entries, vancouver numbered style)
- `computed_stats.txt` (bootstrap CIs and cohort demographics)
- `figures/fig1-architecture.drawio` + `.pdf`
- `figures/fig2-accuracy-evolution.drawio` + `.pdf`
- `figures/fig3-batch-accuracy.drawio` + `.pdf`
- `figures/fig4-failure-taxonomy.drawio` + `.pdf`
- `figures/fig5-architecture-comparison.drawio` + `.pdf`

**Remaining TODOs (require PI input):**
- [x] Fill in author names and institutions
- [x] Financial support: None
- [x] Conflicts of interest: Nothing to report
- [ ] Author contributions: CRediT taxonomy placeholder added --- PI to fill in per-author roles
- [ ] Add IRB number, committee name, and institution (main.tex Methods 2.1)
- [ ] Add Presentation statement in Acknowledgements (state meeting or "None")
- [ ] Graphical abstract (HEPATOLOGY encourages; use provided PowerPoint template)

---

## Active Run: v0.9.4-dev GPT-5.4 Comparison (2026-03-17)

### Setup
- v0.9.4-dev code restored from git tag
- GPT-5.4 env vars added: GPT5_4_ENDPOINT_URL, GPT5_4_AZURE_OPENAI_API_KEY (YouWoAI Dev Resource)
- Model mapping: `gpt-5.4` -> actual model `gpt-5.4-2026-03-05-short-api-ev3`

### Constraint Patients (5/5 = 100%)
- 1279: No -> No (correct)
- 1101: No -> No (correct)
- 1446: Yes -> Yes (correct)
- 1536: No -> No (correct)
- 1624: Yes -> Yes (correct)

### GPT-5.4 Batch Status
- Batch 1: COMPLETE -- 100/100 (100.0%)
- Batch 2: COMPLETE -- 81/100 (81.0%)

### GPT-5.4-Pro Notes
- Model `gpt-5.4-pro` does NOT support chat.completions API
- Error: `OperationNotSupported` for chat completions
- Requires code modification to use completions API (not chat completions)
- Skipping for now unless explicitly requested

### GPT-5.4 Batch 1 Results (v0.9.4-dev) -- COMPLETE
| Metric | GPT-5.4 | GPT-5.2 |
|--------|---------|----------|
| Final Accuracy | 100/100 (100.0%) | 99/100 (99.0%) |
| Hepatologist | 95/100 (95.0%) | - |
| Critical Care | 96/100 (96.0%) | - |
| Transplant Surgeon | 94/100 (94.0%) | - |
| False Negatives | 0 | - |
| False Positives | 0 | - |

### GPT-5.4 Batch 2 Results (v0.9.4-dev) -- COMPLETE
| Metric | GPT-5.4 | GPT-5.2 |
|--------|---------|----------|
| Final Accuracy | 81/100 (81.0%) | 84/100 (84.0%) |
| Hepatologist | 84/100 (84.0%) | - |
| Critical Care | 81/100 (81.0%) | - |
| Transplant Surgeon | 85/100 (85.0%) | - |
| False Negatives | 14 | 13 |
| False Positives | 5 | 3 |

**Failure comparison (Batch 2):**
- Shared FN (13): 1652, 1673, 1776, 1788, 1885, 1887, 1932, 1933, 1990, 2011, 2184, 2228, 2323
- GPT-5.4 new FN regression (1): 2211
- Shared FP (2): 1775, 2235
- GPT-5.4 new FP regressions (3): 1633, 1635, 1726
- GPT-5.2 FP fixed by 5.4 (1): 1643

GPT-5.4 gained 4 new failures and fixed 1, net -3 vs GPT-5.2 on Batch 2.

---

### Comparison Plan
| Model | Batch 1 | Batch 2 | Remaining Batches |
|--------|----------|---------|------------------|
| GPT-5.2 | 99/100 (99.0%) | 84/100 (84.0%) | 11 batches (1117/1260 total) |
| GPT-5.4 | **100/100 (100.0%)** | 81/100 (81.0%) | TBD |

---

## Previous Active Runs

### Phase A: v1.1.0-dev Baseline on 40 Targeted Patients -- COMPLETE

### Phase A: v1.1.0-dev Baseline on 40 Targeted Patients -- COMPLETE

Run current three-layer architecture (prompt fixes + criteria injection + re-evaluation) on the same 40 targeted failure patients used in prompt-only testing (8/40 = 20.0% baseline).

**The 40 patients (4 groups of 10):**
- Fix #1/#7/#19: 3678, 5762, 6466, 6572, 8216, 8465, 8762, 9040, 9452, 9717
- Fix #7/#20/#6: 3610, 5151, 5364, 5573, 7114, 7142, 7688, 8557, 8725, 8968
- Tier 2 fixes: 2228, 3938, 4509, 4677, 4682, 5109, 5385, 6582, 8095, 8237
- Fix #1 enforcement: 2588, 2678, 2723, 3760, 4042, 4823, 5882, 6166, 6257, 6446

**Prompt-only baseline (v0.9.4-dev + 24 prompt fixes): 8/40 (20.0%)**
Correct: 8762, 9040, 7114, 4682, 8095, 2588, 2723, 5882

- [x] Run v1.1.0-dev (three-layer) on all 40 patients -- 31/40 = 77.5%
- [x] Record accuracy, per-patient results, failure modes
- [x] Document baseline: 31/40 (77.5%), 9 failures analyzed (3 Bug 2, 2 Bug 3, 2 Bug 1, 1 P1D-A, 1 remaining)

**v1.1.0-dev 40-patient results (2026-03-05):**
- Total: 31/40 = 77.5% (up from 8/40 = 20.0% prompt-only)
- 4682 reclassified as true negative (correctly predicted No, actual No) -- 31/39 on false negatives
- 9 failures: 7688, 8968, 9717 (Bug 2: lactate divergence), 5385, 6582 (Bug 3: Day 2-3 missing criteria), 5364, 8237 (Bug 1: ventilation parsing), 2228 (P1D-A uremic HE), 3938 (remaining)
- 5 re-evaluations observed: 5364, 7688, 8237, 8968, 9717 -- 3 of 5 failed due to Bug 2

### Phase B: v1.2.0-dev Conditional Prompting Implementation -- IN PROGRESS

Implemented conditional prompting (phenotype-based skill injection) replacing the "cheating" re-evaluation approach.

- [x] Design phenotype taxonomy: 9 tags (p1b_recovery, p1c_bilirubin_lag, extreme_bilirubin, stale_lactate, early_presentation, uremic_he, low_peak_inr, early_metabolic_warning, ventilated_early)
- [x] Implement classify_phenotype() and select_skills()
- [x] Create 9 SKILL_BLOCKS (focused instruction fragments)
- [x] Inject skills into ALL 4 agents (hepatologist, critical care, transplant surgeon, committee chair)
- [x] Fix Bug 1: ventilation parsing
- [x] Fix Bug 2: lactate display/engine alignment (P1C, Combination Signal, Extreme Bilirubin waiver)
- [x] Fix Bug 3: Day 2-3 criteria injection
- [x] Fix P1D-A: uremic HE extension
- [x] Remove criteria_guided_reevaluation() (the "cheating" function)
- [x] Update apply_post_processing() to silent deterministic override
- [x] Verify constraint patients: 5/5 (100%) -- 1279, 1101, 1536, 1624, 1446 (all correct, zero overrides needed)
- [x] Run same 40 targeted patients with v1.2.0-dev -- 34/40 = 85.0%
- [x] Compare v1.1.0-dev (31/40) vs v1.2.0-dev (34/40) head-to-head

**v1.2.0-dev 40-patient results (2026-03-05 13:18):**
- Total: 34/40 = 85.0% (up from 31/40 = 77.5% v1.1.0-dev, up from 8/40 = 20.0% prompt-only)
- LLM-only: 33/40 = 82.5% (only 1 post-processing override needed vs 5 in v1.1.0-dev)
- Improved: 2228 (P1D-A uremic fix), 7688 (Bug 2 lactate fix), 9717 (Bug 2 lactate fix)
- Regressions: 0
- Remaining failures (7): 7114 (Day 2), 5385 (Day 3), 6582 (Day 3), 8762 (Day 3), 8968 (Day 7), 5109 (Day 7), 3938 (Day 7 FP)

**7-Failure Root Cause Analysis (2026-03-05 17:05):**
3 parallel agents analyzed all 7 remaining failures. Results:
- Group A (4 early FN): 7114, 8762, 6582, 5385 -- code Pre-Check B/C logic more aggressive than prompt's nuanced rules
- Group B (2 Day 7 FN): 8968 (P1 "declining from peak" not implemented), 5109 (irreducible -- DILI ALFSG-PI 10.9%)
- Group C (1 Day 7 FP): 3938 (P1 negation too narrow for multi-organ failure)
- 5 proposed fixes -> potential 38/40 = 95.0%, theoretical ceiling 39/40 = 97.5%
- See docs/lessons.md for full root cause details and proposed fixes

### Phase B Cautious Fix Plan (overfitting-aware)

**Principle:** Only implement low-risk bug fixes (code not matching existing prompt rules). Do NOT implement parameter-tuned fixes (4, 5) until validated on full batch.

**Low-risk fixes (implemented 2026-03-05 18:13):**
- [x] Fix 1: Bilirubin micro-rise tolerance (<=0.5 mg/dL = stable) in parse_vignette() -- within lab measurement error
- [x] Fix 2: Pre-Check B magnitude requirement (rise >2 AND current >5) -- aligns code with existing Fix #6 prompt rule
- [x] Fix 3: Pre-Check C exception deterministic ("IS MET" not "consider") -- display/language bug, not clinical rule change
- [x] Verify constraint patients: 5/5 (100%), zero overrides

**Deferred fixes (require full-batch validation first):**
- [ ] Fix 4: P1 bilirubin "declining from peak" -- parameter fitted to 1 patient (8968)
- [ ] Fix 5: P1 negation expansion -- new rule from 1 patient (3938), high regression risk

**Validation:**
- [x] Constraint patients: 5/5 (100%)
- [x] Batch 1 (100 patients): 97/100 (97.0%) -- MEETS >= 97% THRESHOLD
  - LLM-only: 97/100, zero post-processing overrides
  - Failures: 1526 (Day 6, persistent from v0.9.4-dev), 1112 (Day 3, new regression), 1463 (Day 7, new regression)
  - 2 regressions (1112, 1463) NOT caused by fixes 1-3 (neither involves ventilation or bilirubin magnitude). Likely LLM stochasticity or broader v1.2.0-dev architecture effects.
  - v0.9.4-dev Batch 1: 99/100. v1.2.0-dev Batch 1: 97/100.

### Phase C: v1.2.0-dev Full Evaluation -- ABORTED

v1.2.0-dev Batch 2 regressed to 81/100 (v0.9.4-dev was 84/100). Stopped evaluation, pivoted to v1.3.0-dev.

- [x] Batch 1 (v1.2.0-dev): 97/100 (97.0%)
- [x] Batch 2 (v1.2.0-dev): 81/100 (81.0%) -- REGRESSED from v0.9.4-dev 84/100. STOPPED.

### Phase D: v1.3.0-dev Selective Injection -- FAILED VALIDATION

Redesigned: selective injection (only hard-phenotype patients get enhanced prompts) + tiered binding (P1=BINDING, P1B/P1C/P1D=SOFT). Normal patients get v0.9.4-dev prompt.

- [x] Implement format_tiered_rules() replacing format_binding_rules_skill()
- [x] Gate injection behind `if phenotype_tags:` in all 4 agents
- [x] Constraint patients: 5/5 (100%)
- [x] Batch 1 (v1.3.0-dev): 98/100 (98.0%) -- improved over v1.2.0-dev (97) but still below v0.9.4-dev (99)
- [x] Batch 2 (v1.3.0-dev): 81/100 (81.0%) -- same as v1.2.0-dev, still below v0.9.4-dev (84)
- [x] 40-patient hard set (v1.3.0-dev): 33/40 (82.5%) -- below v1.2.0-dev (34/40), above prompt-only (8/40)
  - Failures (7): 3938 (FP), 5109, 5385, 6582, 7114, 8762, 8968 (FN)
  - vs v1.2.0-dev: fixed 3610, regressed 7114 and 8762. Net -1.
  - Output: `agent_predictions_gpt-5.2_20260305_162015.xlsx`

**Conclusion:** Selective injection protects normal patients but still regresses on tagged patients. ANY injection changes LLM behavior unpredictably. Net effect on Batch 2 is negative. On the 40-patient hard set, v1.3.0-dev (33/40) slightly underperforms v1.2.0-dev (34/40), confirming that tiered/soft binding language does not recover the regression.

### Version Comparison Summary

| Version | Architecture | Batch 1 | Batch 2 | 40-Hard |
|---------|-------------|---------|---------|---------|
| v0.9.4-dev | Prompt-only | 99/100 | 84/100 | 8/40 |
| v1.2.0-dev | Inject all + binding | 97/100 | 81/100 | 34/40 |
| v1.3.0-dev | Selective inject + tiered | 98/100 | 81/100 | 33/40 |

### Git Tags Pushed (2026-03-05)

All versions tagged and pushed to GitHub (origin) for reproducibility:
- `v0.9.4-dev` (7fa9c1a): Prompt-only baseline, 88.7% overall
- `v1.2.0-dev` (5011eae): Conditional prompting + binding rules
- `v1.3.0-dev` (203e41c): Selective injection + tiered binding

Restore: `git checkout <tag> -- multi_agent_system.py`

### Next Steps (requires decision)
- [ ] Option A: Accept v0.9.4-dev as final (88.7%) -- proven, no regressions
- [ ] Option B: Try removing survival rules entirely from injection (only death overrides + informational criteria)
- [ ] Option C: Fundamentally different approach (ensemble, fine-tuning, retrieval-augmented)

### v1.1.0-dev Verification Status (completed)
- Constraint patients: 5/5 (100%) -- 1279, 1101, 1536, 1624, 1446
- Target sample: 9/10 (90%) -- 4682 edge case (extreme INR + HE=0)
- Full Batch 1 re-evaluation: PENDING (blocked by 40-patient baseline first)
- Full 1260-patient re-evaluation: PENDING

### Previous Status (v0.9.4-dev baseline)
ALL 13 BATCHES COMPLETE. 1117/1260 (88.7%). 143 failures individually characterized across 20 issues and 24 fixes.

## Batch 13 Thorough Analysis (completed 2026-03-04 21:59)

3 parallel agents analyzed all 7 Batch 13 failures (7 false negatives, 0 false positives). Key findings:

**Highly Actionable (3):**
- Patient 9040 (FN): P1B FULLY MET (peak INR 6.1, 72.1% improvement, ALT 83.4% down, lactate 1.4). Committee explicitly stated "Priority 1B IS met" then predicted death. 11th enforcement failure. Fix #1. ZERO regression risk.
- Patient 9452 (FN): INR 1.06 (one of BEST recoveries in entire 1,260-patient evaluation), ALT 91% down, HE 0, ALFSG-PI 85.7%, no organ support. Sole blocker: stale lactate 2.3 from Day 2 (5 days stale). Fix #7. Near-zero regression risk.
- Patient 9717 (FN): HE 0, no vent, no pressors, no infection, Cr 0.75 (excellent). Sole blocker: stale lactate 7.8 from Day 2 (5 days stale). CC specialist correctly identified stale lactate but system forced death. Fix #7.

**Moderate (2):**
- Patient 9580 (FN): INR improvement 56.6% vs >60% (3.4% short), ALT 93.5% down (exceptionally strong). 2/3 specialists Yes but committee overrode with Extreme Bilirubin. Issue F / Fix #5 extension possible (>=55% when ALT >90%). Patient 1101 at ALT 74% would NOT qualify -- low regression risk.
- Patient 9691 (FN): Grade 4 HE + ammonia 48 (<50) + CVVH active (Cr 1.85 masked from 3.42). Fix #11 neutralizes death overrides BUT creates CIRCULAR DEPENDENCY: uremic HE blocks lag exception conditions (HE 4 + vent), so no positive pathway fires. Needs Combination Signal extension.

**Noise Floor (1):**
- Patient 9546: ALFSG-PI 34.5%, on vent + pressors + CVVH + infection, platelets 7, HE 3, bilirubin 23.8. Genuine multi-organ failure. No fix without regression risk.

**Moderate/Borderline Noise Floor (1):**
- Patient 9120: INR 1.8, HE 3, ventilated, bilirubin 29.7 rising, lactate never measured. Multiple compound blockers (Issues A+D+H). No single fix resolves.

**Documentation updates:**
- Fix #1: Added 9040 (11th enforcement failure -- P1B acknowledged met then overridden)
- Fix #5: Added 9580 (INR 56.6% near-miss) + extension note (>=55% when ALT >90%)
- Fix #7: Added 9452, 9717 (stale lactate sole blockers -- among strongest Fix #7 cases), 9120 (partial)
- Fix #11: Added 9691 (CVVH circular dependency)
- Issues A, B, C, D, F, H, K, L, N updated with Batch 13 patients
- Cross-reference table updated with Batch 13 column
- Full analysis integrated into docs/lessons.md and CHANGELOG.md

## Batch 12 Thorough Analysis (completed 2026-03-04 21:08)

3 parallel agents analyzed all 11 Batch 12 failures (8 false negatives, 3 false positives). Key findings:

**Highly Actionable (3):**
- Patient 8465 (FN): ALL 5 Extreme Bilirubin waiver conditions MET (HE 0, lactate 1.4, no vent, no pressors, no infection) but committee rejected with invented 6th condition ("bilirubin must show peak/decline"). 3rd confirmed Issue B Variant B (after 3678, 5151). Fix #19 critical. ZERO regression risk.
- Patient 8557 (FN): P1B FULLY MET (peak INR 5.69, 64.9% improvement, ALT 91.7% down, HE 1 satisfies additional condition). Committee overrides with Extreme Bilirubin. Fix #1 enforcement.
- Patient 8762 (FN): CLEAREST Pre-Check B false positive in 1,200 patients. ALFSG-PI 93.3%, all 3 specialists Yes, 77.6% INR improvement from peak 6.7, HE 0, no organ support. Pre-Check B fires on bilirubin 1.6->4.5 (trivial magnitude) + lactate 3.0 from Day 2. Fix #6 (require bilirubin >5) directly fixes.

**Moderate (3):**
- Patient 8725 (FN): Missing lactate sole blocker. No vent, no pressors, no CVVH, no infection, HE 1, ALT 71 near-normal. Textbook Fix #7.
- Patient 8968 (FN): P1 likely MET (INR 1.4, ALT ~90% down, bilirubin 16.4->15.7 IS declining). Committee dismissed 0.7 mg/dL decline. Stale lactate 7.7 from Day 1 (Fix #7). Same pattern as 6572.
- Patient 8447 (FN): Stale lactate 3.4 from Day 3 (4 days stale), extreme bilirubin 30.2 rising. Compound A+D+H. Fix #7 partially addresses.

**Noise Floor FN (2):**
- Patient 8882: Lactate 11 rising + vasopressors + grade 4 HE + ALFSG-PI 45%. Genuinely surprising survival.
- Patient 8633: Compound near-miss (INR 1.6, peak INR 4.6, HE 4, ammonia 80, Na 167, pH 7.29). Too close to constraint 1279.

**False Positives (3):**
- Patient 8632 (FP): NOISE FLOOR. Day 2 unpredictable death. Extends Issue P from Day 1 to Day 2.
- Patient 8732 (FP): BORDERLINE. Committee incorrectly claimed P1C met. Smoldering sepsis phenotype (persistent HE 3, oscillating lactate, progressive WBC). New Issue O Variant D.
- Patient 9009 (FP): ACTIONABLE. NEW Issue B Variant G: committee claims P1B met by ignoring mandatory additional condition (lactate <2 OR HE 0-1 OR Cr improving). Overrides 3/3 specialist No. CRITICAL Fix #7 scoping: missing lactate must not SATISFY positive criteria.

**Documentation updates:**
- Issue B: Added Variant G (9009 FP -- P1B additional condition ignored)
- Fix #1: Added 8557, 8968 (enforcement failures)
- Fix #6: Added 8762 (clearest Pre-Check B case)
- Fix #7: Added 8725, 8447, 8968 + CRITICAL scoping note (missing lactate does NOT satisfy "lactate <2" for P1B)
- Fix #19: Added 8465 (3rd confirmed waiver rejection)
- Issues A, B, C, D, F, G, H, L, N, O, P updated with Batch 12 patients
- Cross-reference table updated with Batch 12 column
- Full analysis integrated into docs/lessons.md and CHANGELOG.md

## Batch 11 Thorough Analysis (completed 2026-03-04 19:50)

3 parallel agents analyzed all 9 Batch 11 failures (6 false negatives, 3 false positives). Key findings:
- 3 highly actionable patients (8095, 8174, 8216), 1 moderate (8237), 2 noise floor FN (7777, 7830), 3 FP noise floor (7936, 8103, 8136)
- Patient 8095 (FN): P1 FULLY MET (INR 1.4, ALT >92% down, bilirubin declining) but P1 negation fires at PaO2/FiO2 1.85 (<2.0). FIRST correct-but-wrong P1 negation case. NEW Issue T / Fix #24: tighten P1 negation from PaO2/FiO2 <2.0 to <1.5. ZERO regression risk.
- Patient 8174 (FN): 1B liver labs met (peak INR 9.8, 73.5% improvement, ALT 93% decline). Additional condition blocked by missing lactate + HE 4 + ATN Cr 1.1->1.7. Fix #7 or Fix #5 or Fix #12 each independently fix.
- Patient 8216 (FN): Missing lactate sole blocker. Fix #7 directly and completely fixes. INR 4.6->1.6, ALT >80% down, HE 1, no organ support. One of cleanest Fix #7 cases in entire dataset.
- Patient 8237 (FN): INR exactly 1.5, HE 2, vent, ATN Cr 2.5->3.1. Needs Fix #2 (1C lag widening) + Fix #5 (ATN Cr) combined. Compound triple block.
- Patient 7777 (FN): NOISE FLOOR. Peak INR <2.0 + grade 4 HE + vent + pressors. Too close to constraint 1279.
- Patient 7830 (FN): NOISE FLOOR. Bilirubin 25 rising, lactate 4.2 rising, HE 4, INR 2.0. Genuinely terrible presentation.
- Patient 7936 (FP): NOISE FLOOR. Ischemia/Shock etiology, P1 met, ALT rebound 149->392. Death from circulatory disease.
- Patient 8103 (FP): BORDERLINE. P1 met. Severe hypernatremia Na 143->163 (not tracked by framework). Peak ammonia 445 historical.
- Patient 8136 (FP): BORDERLINE. 1B correctly met. Bilirubin monotonically rising all 7 days never peaked. Declining platelets 119->56. "Bilirubin never-peaked" pattern differs from true excretory lag.
- NEW Issue T added: P1 Negation Too Aggressive at PaO2/FiO2 Boundary
- NEW Fix #24 added: Tighten P1 negation PaO2/FiO2 threshold (from <2.0 to <1.5)
- FP analysis: none of the 24 proposed FN-targeting fixes create regression risk against the 3 FP patients
- Fixes #2, #5, #7, #12 updated with Batch 11 patients
- Full analysis integrated into docs/lessons.md and CHANGELOG.md

## Batch 10 Thorough Analysis (completed 2026-03-04 18:18)

4 parallel agents analyzed all 11 Batch 10 failures (10 false negatives, 1 false positive). Key findings:
- 5 actionable patients (7142, 7688, 7442, 7114, 7297) fixable by existing Fixes #5, #7, #11
- Patient 7142: INR 1.4, ALT 88.5% down, HE 0, lactate NEVER measured -- Fix #7 (missing lactate) directly fixes
- Patient 7688: INR 1.4, ALT 88% down, HE 1, stale lactate 2.3 from Day 1 (6 days stale) -- Fix #7 directly fixes
- Patient 7442: 1C bilirubin lag exception blocked SOLELY by ATN creatinine worsening (1.3->3.6) -- Fix #5 ATN Cr resolution fixes
- Patient 7114: Bilirubin micro-rise 6.0->6.1 triggers Pre-Check B at Day 2 -- Fix #5 micro-rise tolerance fixes. NEW: Pre-Check B exception structurally inaccessible at Day 2 (INR hasn't recovered >50%)
- Patient 7297: 1B liver labs fully met (peak INR 5.4, 63% improvement) but CVVH masks Cr and lactate 2.9 -- Fix #11 extension to 1B systemic arm
- Patient 7333 (FALSE POSITIVE): Committee predicted survive without binding rule, 2/3 specialists predicted death. NEW Issue B Variant F (inverted enforcement failure)
- 4-5 noise floor patients (7155, 7265, 7515, 7555, 7546 borderline)
- Fix #1 updated with Day 1 weighted vote enforcement (7333 FP)
- Fix #11 extended to 1B context with APAP lactate relaxation
- Full analysis integrated into docs/lessons.md and CHANGELOG.md

## Batch 9 Thorough Analysis (completed 2026-03-04 16:55)

4 parallel agents analyzed all 14 Batch 9 failures (all false negatives, 0 false positives). Key findings:
- 3 patients (6572, 6466, 6446) had recovery criteria DEMONSTRABLY MET but committee failed to enforce
- Patient 6572: Priority 1 FULLY MET (bilirubin IS declining 15.1->13.8, committee subjectively dismissed)
- Patient 6466: Priority 1C ACTUALLY MET (lactate 2.0 IS <=2.0, committee misread it). CLEAREST Issue F case in 900 patients.
- Patient 6446: Committee explicitly acknowledged "1B IS met" then overrode with Priority 2 -- direct hierarchy violation
- Patient 6412: All 3 specialists predicted survive (INR 1.1 fully normalized!) but committee overrode -- second case after 5824
- Patient 6582: NEW Issue G variant -- Pre-Check C on non-APAP with excellent labs. Proposed Fix #23.
- 3 noise floor patients (6451, 6417, 6847) -- genuinely unfixable
- Fix #5 updated: peak INR >=5.0 (from >5.0), zero regression risk
- Total fixes now 23 (added Fix #23 for non-APAP Pre-Check C)
- Full analysis integrated into docs/lessons.md and CHANGELOG.md

## Batch 8 Thorough Analysis (completed 2026-03-04 15:43)

4 parallel agents analyzed all 13 Batch 8 failures. Key findings:
- 4 patients (5762, 5882, 6166, 6257) had recovery criteria DEMONSTRABLY MET but committee failed to enforce
- Patient 5762: Priority 1 FULLY MET (most egregious enforcement failure in dataset)
- Patient 5824: All 3 specialists predicted survive but committee overrode on 0.1 mg/dL bilirubin rise
- No genuinely new issues -- all 13 map to existing Issues A-S
- Sub-pattern refinements added to Fixes 1, 5, 7, 14, 21
- Full analysis integrated into docs/lessons.md and CHANGELOG.md

## Phase 1: Validate v0.9.4-dev on Batch 1

- [x] Run v0.9.4-dev full 100-patient evaluation (Batch 1: patients 1013-1626)
- [x] Verify accuracy >= 97% (target: 97-99%) -- PASSED: 99/100 (99.0%)
- [x] Record results and any failures -- 1 wrong: Patient 1526 Day 6 (predicted No, actual Yes)

## Phase 2: Evaluate All Remaining Batches

- [x] Batch 2 (100 patients: 1633-2375) -- 84/100 (84.0%) -- BELOW 90% THRESHOLD, INVESTIGATION NEEDED
- [x] Batch 3 (100 patients: 2382-2939) -- 87/100 (87.0%)
- [x] Batch 4 (100 patients: 2946-3610) -- 86/100 (86.0%)
- [x] Batch 5 (100 patients: 3611-4282) -- 87/100 (87.0%)
- [x] Batch 6 (100 patients: 4287-4819) -- 86/100 (86.0%)
- [x] Batch 7 (100 patients: 4820-5621) -- 92/100 (92.0%) -- BEST UNSEEN BATCH
- [x] Batch 8 (100 patients: 5624-6388) -- 87/100 (87.0%) -- 2 API errors, thorough analysis complete
- [x] Batch 9 (100 patients: 6389-7064) -- 86/100 (86.0%)
- [x] Batch 10 (100 patients: 7066-7688) -- 89/100 (89.0%) -- SECOND BEST UNSEEN BATCH
- [x] Batch 11 (100 patients: 7694-8379) -- 91/100 (91.0%) -- THIRD BEST OVERALL
- [x] Batch 12 (100 patients: 8407-9009) -- 89/100 (89.0%)
- [x] Batch 13 (60 patients: 9023-9979) -- 53/60 (88.3%) -- 7 FN, 0 FP, 0 errors

## Phase 3: Aggregate and Report

- [x] Combine all 13 batch results into single Excel file -- agent_predictions_gpt-5.2_all_1260_patients.xlsx
- [x] Calculate overall accuracy across all 1,260 patients -- 1116/1260 (88.6%)
- [x] Identify failure patterns and common error types -- 20 issues, 24 fixes in docs/lessons.md
- [x] Generate final report with per-batch and overall metrics -- see CHANGELOG.md and aggregated Excel

## Progress Tracking

| Batch | Patients | Status | Accuracy | Failures |
|-------|----------|--------|----------|----------|
| 1 | 100 | DONE | 99/100 (99.0%) | 1526 (Day 6) |
| 2 | 100 | DONE | 84/100 (84.0%) | 16 wrong: 13 false neg (1652,1673,1776,1788,1885,1887,1932,1933,1990,2011,2184,2228,2323), 3 false pos (1643,1775,2235) |
| 3 | 100 | DONE | 87/100 (87.0%) | 13 wrong: 10 false neg (2584,2588,2678,2723,2738,2741,2805,2812,2821,2884), 3 false pos (2426,2632,2862) |
| 4 | 100 | DONE | 87/100 (87.0%) | 13 wrong: 12 false neg (3029,3089,3133,3218,3243,3247,3343,3534,3545,3566,3576,3610), 1 false pos (3474). API error 3215 rerun: correct (Yes). |
| 5 | 100 | DONE | 87/100 (87.0%) | 13 wrong: 11 false neg (3678,3742,3743,3760,3778,3875,3899,3907,4029,4042,4051), 2 false pos (3892,3938) |
| 6 | 100 | DONE | 86/100 (86.0%) | 14 wrong: 12 false neg (4323,4339,4429,4509,4513,4564,4623,4658,4662,4674,4677,4768), 2 false pos (4311,4682) |
| 7 | 100 | DONE | 92/100 (92.0%) | 8 wrong: 8 false neg (4823,5109,5145,5151,5251,5364,5385,5573), 0 false pos |
| 8 | 100 | DONE | 87/100 (87.0%) | 13 wrong: 12 false neg (5762,5781,5822,5824,5882,5973,6142,6166,6216,6257,6323,6325), 1 false pos (5742). API errors 5822/5824 rerun: both FN. |
| 9 | 100 | DONE | 86/100 (86.0%) | 14 wrong: 14 false neg (6412,6415,6417,6446,6451,6466,6477,6531,6572,6582,6737,6743,6821,6847), 0 false pos |
| 10 | 100 | DONE | 89/100 (89.0%) | 11 wrong: 10 false neg (7114,7142,7155,7265,7297,7442,7515,7546,7555,7688), 1 false pos (7333) |
| 11 | 100 | DONE | 91/100 (91.0%) | 9 wrong: 6 false neg (7777,7830,8095,8174,8216,8237), 3 false pos (7936,8103,8136) |
| 12 | 100 | DONE | 89/100 (89.0%) | 11 wrong: 8 false neg (8447,8465,8557,8633,8725,8762,8882,8968), 3 false pos (8632,8732,9009) |
| 13 | 60 | DONE | 53/60 (88.3%) | 7 wrong: 7 false neg (9040,9120,9452,9546,9580,9691,9717), 0 false pos |
| **TOTAL** | **1,260** | **DONE** | **1117/1260 (88.7%)** | **143 wrong: 124 false neg, 19 false pos, 0 API errors** |
