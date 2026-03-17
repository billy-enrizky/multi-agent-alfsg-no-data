# Lessons Learned

**Last updated:** 2026-03-17 16:55:00

## v1.2.0-dev: Conditional Prompting (Phenotype-Based Skill Injection)

### Core Insight: Re-evaluation is "Cheating"

The v1.1.0-dev `criteria_guided_reevaluation()` function told the LLM the correct answer and asked it to agree. This is not genuine reasoning -- it is prompt-guided compliance. For the paper, we need the LLM to reach the correct answer through its own reasoning, guided by focused context.

### Solution: Conditional Prompting (Not LLM Router)

Instead of adding an extra LLM router call, use DETERMINISTIC phenotype classification (`classify_phenotype()`) to select relevant skill blocks. Zero extra API calls, zero router error risk.

**Architecture:** parse_vignette() -> classify_phenotype() -> select_skills() -> inject into ALL 4 agents

**9 phenotype tags:**
- p1b_recovery, p1c_bilirubin_lag, extreme_bilirubin, stale_lactate
- early_presentation, uremic_he, low_peak_inr
- early_metabolic_warning, ventilated_early

**Key design decision:** Skills are injected into the USER PROMPT alongside the vignette and criteria. System prompts are UNCHANGED (too risky to modify -- deeply tested, regression-prone). This is additive, not destructive.

### Three Critical Bugs Found in v1.1.0-dev 40-Patient Evaluation

**Bug 1 (CRITICAL): Ventilation parsing never matched.**
- `parse_vignette()` checked for `'is on mechanical ventilation'` but vignettes use `'is receiving mechanical ventilation'`
- ALL 1,260 patients parsed as `on_ventilation=False`
- Directly caused patients 5364, 8237 to fail (Pre-Check C should have caught ventilation)
- Impact: every ventilation-dependent rule (P1C vent extension, Pre-Check C, Extreme Bilirubin vent check) was broken

**Bug 2 (HIGH): Lactate display/engine divergence.**
- `evaluate_binding_rules()` correctly used `lactate_not_blocking()` which treats stale lactate >72h as non-blocking
- `format_criteria_evaluation()` used simple `current_lactate <= 2.0` ignoring stale lactate
- LLM saw "Lactate OK? NO" in checklist but engine said P1C MET
- LLM rationally followed the wrong checklist, rejected the criteria override in re-evaluation
- Directly caused patients 7688, 8968, 9717 to fail (3 of the 5 re-evaluation failures)

**Bug 3 (MODERATE): No Day 2-3 criteria injection.**
- `format_criteria_evaluation()` returned "" for Day <5
- Pre-Check B/C exceptions existed in prompt text but LLM rationalizes around them without explicit values
- Patients 5385, 6582 met all exception criteria but LLM rejected

### Lesson: Engine/Display Alignment is Non-Negotiable

When a deterministic engine and an LLM display layer disagree, the LLM rationally follows what it sees (the display), not what the engine computed. Every check in `format_criteria_evaluation()` must use the EXACT same logic as `evaluate_binding_rules()`. This is not a "nice to have" -- it directly caused 3 of 9 failures.

### v1.2.0-dev Evaluation Results (2026-03-05 13:18)

- **34/40 = 85.0%** (up from 31/40 = 77.5% v1.1.0-dev)
- LLM-only: 33/40 = 82.5% (only 1 post-processing override needed)
- Improved: 2228 (P1D-A uremic fix), 7688 (Bug 2 lactate fix), 9717 (Bug 2 lactate fix)
- Regressions: 0
- Constraint patients: 5/5 (100%), zero overrides needed

**Key observation:** Conditional prompting reduced post-processing overrides from 5 to 1. The LLM reaches the correct answer on its own when given focused, phenotype-relevant instructions instead of the monolithic 5000+ word prompt combined with a "cheating" re-evaluation.

### 7-Failure Root Cause Analysis (2026-03-05 17:05)

3 parallel agents analyzed the 7 remaining failures (7114, 8762, 6582, 5385, 8968, 5109, 3938). Root causes fall into 3 groups.

**Group A: Early FN -- Code Pre-Check B/C Logic Too Aggressive (4 patients)**

- **7114 (Day 2):** Bilirubin micro-rise 6.0->6.1 (+0.1 mg/dL) triggers Pre-Check B. Code has no magnitude tolerance. Fix: treat bilirubin rise <=0.5 mg/dL as "stable" in `parse_vignette()`.
- **8762 (Day 3):** Bilirubin 1.6->4.5 triggers Pre-Check B. Rise is +2.9 but current value only 4.5 (below clinically significant 5.0). Code doesn't implement magnitude requirement (rise >2 AND current >5). Fix: add magnitude check to Pre-Check B trigger logic.
- **6582 (Day 3):** Bilirubin micro-rise +0.2 mg/dL. Non-APAP ventilated patient. Pre-Check C exception is too narrow -- requires "HE improving" but patient has HE 0 (which is better than "improving"). Fix: widen exception to include HE 0-1 (inherently stable/good).
- **5385 (Day 3):** Pre-Check C exception criteria ALL met (ALFSG-PI 89.7%, no pressors, no infection, ALT declining) but code says "consider" instead of deterministic "IS MET". LLM interprets "consider" as optional and rejects. Fix: change Pre-Check C exception output from "consider" to "Exception IS MET -- BINDING".

**Root cause pattern:** The deterministic code in `format_criteria_evaluation()` is more aggressive (triggers pre-checks more easily) than the prompt's nuanced clinical rules (which have magnitude requirements and exception logic). The code lacks micro-rise tolerance and deterministic exception language.

**Group B: Day 7 FN -- P1 Logic Gaps (2 patients)**

- **8968 (Day 7):** Strong APAP recovery (INR 1.4, ALT ~90% down). Bilirubin stable at 15.7 (down from peak 16.4) but classified as "not declining" because code requires strict Day 7 < Day 6 comparison rather than "declining from peak". Fix: count "declining from peak by >=0.5 mg/dL" as declining in P1 bilirubin check.
- **5109 (Day 7):** DILI etiology with ALFSG-PI 10.9%, grade 4 HE, ventilated, on pressors, active infection. **Irreducible error** -- genuinely surprising survival. No fix without regression risk against constraint patients.

**Group C: Day 7 FP -- P1 Negation Too Narrow (1 patient)**

- **3938 (Day 7 FP):** P1 fires (INR 1.1, ALT 94% down, bilirubin declining) but patient dies from multi-organ failure (grade 4 HE, ventilated, CVVH, rising creatinine). P1 negation currently requires PaO2/FiO2 <2.0 AND active infection -- patient has neither. Fix: expand P1 negation to include "grade 4 HE + ventilation + CVVH + rising creatinine" as independent negation trigger. Also: ammonia parsing may have a bug (ammonia 113 present but not parsed).

**5 Proposed Fixes to Reach 38/40 (95.0%):**

1. **Bilirubin micro-rise tolerance:** In `parse_vignette()`, treat bilirubin rise <=0.5 mg/dL as "stable" (not rising). Fixes 7114, 6582.
2. **Pre-Check B magnitude requirement:** Require bilirubin rise >2 mg/dL AND current >5 mg/dL to trigger. Fixes 8762.
3. **Pre-Check C exception deterministic:** Change "consider" to "Exception IS MET -- BINDING". Fixes 5385.
4. **P1 bilirubin "declining from peak":** Count declining from peak (>=0.5 drop) as satisfying "declining" even if Day 7 = Day 6. Fixes 8968.
5. **P1 negation expansion:** Add grade 4 HE + ventilation + CVVH + rising creatinine as independent death override. Fixes 3938.

Irreducible: 5109 (1 patient) = noise floor.
Theoretical ceiling: 39/40 = 97.5%.

### Overfitting Risk Assessment (2026-03-05 18:14)

The 40 patients are a DEVELOPMENT set (hand-picked hardest failures). Tuning to them without validating on the full 1,260 is textbook overfitting.

**Risk classification:**
- **Low risk (bug fixes -- code not matching existing rules):** Fixes 1-3. These align code behavior with prompt rules that were already validated across 1,260 patients. Not parameter fitting.
- **Moderate risk (logic gap):** Fix 4 (declining from peak). The concept is clinically sound but the >=0.5 threshold is fitted to one patient.
- **High risk (new rule from single patient):** Fix 5 (P1 negation expansion). Based entirely on patient 3938. Could create false negatives across 1,220 untested patients.

**Cautious approach adopted:**
1. Implement only fixes 1-3 (low risk)
2. Validate on full Batch 1 (100 patients, 60 NOT in the 40-patient dev set)
3. Defer fixes 4-5 until full-batch validation confirms no regressions
4. Never declare accuracy improvements based only on the 40-patient dev set

### Batch 1 Validation Results (2026-03-05 19:54)

- v1.2.0-dev + 3 low-risk fixes: **97/100 (97.0%)** -- meets >= 97% threshold
- v0.9.4-dev baseline: 99/100 (99.0%)
- Delta: -2 patients on Batch 1 (easy set), but +26 on 40-patient hard set (8 -> 34)
- 2 new regressions (1112 Day 3, 1463 Day 7) are NOT caused by fixes 1-3 -- neither patient involves ventilation or bilirubin magnitude. Likely LLM stochasticity or effects of broader architectural changes (skill injection, binding rules).
- Persistent failure: 1526 (Day 6) -- same as v0.9.4-dev

### v1.2.0-dev Batch 2 Regression Analysis (2026-03-05 20:53)

- v1.2.0-dev Batch 2: **81/100** vs v0.9.4-dev **84/100** -- 3-point regression
- 6 regressions, 3 improvements, net -3
- 2 FP regressions (1633, 1726): binding rules said "P1B IS MET -- predict SURVIVAL" but patients died. P1B is not 100% specific.
- 4 FN regressions: injection added noise to patients that v0.9.4-dev handled correctly
- **Root cause:** BINDING language for P1B/P1C/P1D forces LLM to override its clinical judgment on edge cases where recovery criteria are met but patient dies anyway

### v1.3.0-dev: Selective Injection with Tiered Binding (2026-03-05 23:53)

**Design:** Only inject into hard-phenotype patients. Normal patients get v0.9.4-dev prompt (zero injection). P1B/P1C/P1D use SOFT language ("strongly suggests") not BINDING.

**Results:**
- Batch 1: **98/100** (v0.9.4-dev 99, v1.2.0-dev 97) -- recovered 1 regression (1463)
- Batch 2: **81/100** (v0.9.4-dev 84, v1.2.0-dev 81) -- same as v1.2.0-dev, still -3 vs baseline
- 5 regressions (all tagged patients): 1633, 1726 (FP -- even soft P1B language flips LLM), 1866, 2211, 2346 (FN)
- 3 improvements: 1885, 2011, 2323

**Key lesson: ANY injection into the prompt changes LLM behavior unpredictably.** Even "informational" criteria and "soft" language cause regressions on some patients while improving others. The net effect on Batch 2 is negative. Selective injection protects normal patients (Batch 1 improved) but does not solve the regression problem on tagged patients.

**Implication:** The v0.9.4-dev prompt-only approach may be a local optimum. Beating 88.7% requires either: (a) finding injection language that is net-positive across ALL batches, (b) a fundamentally different approach (e.g., ensemble, retrieval-augmented, or model fine-tuning), or (c) accepting that 88.7% is near the ceiling for this architecture.

### Git Version Control (2026-03-17)

All versions tagged and pushed to GitHub for reproducibility:
- `v0.9.4-dev` (7fa9c1a): Prompt-only baseline, 88.7% overall (1117/1260)
- `v1.2.0-dev` (5011eae): Conditional prompting + binding rules
- `v1.3.0-dev` (203e41c): Selective injection + tiered binding

Can restore any version with `git checkout <tag> -- multi_agent_system.py`. Current HEAD is v1.3.0-dev.

### Evaluation Strategy

Run v1.1.0-dev and v1.2.0-dev on the same 40 targeted failure patients head-to-head.

**The 40 patients (from previous prompt-only test, 8/40 = 20.0% baseline):**
- Fix #1/#7/#19: 3678, 5762, 6466, 6572, 8216, 8465, 8762, 9040, 9452, 9717
- Fix #7/#20/#6: 3610, 5151, 5364, 5573, 7114, 7142, 7688, 8557, 8725, 8968
- Tier 2 fixes: 2228, 3938, 4509, 4677, 4682, 5109, 5385, 6582, 8095, 8237
- Fix #1 enforcement: 2588, 2678, 2723, 3760, 4042, 4823, 5882, 6166, 6257, 6446

Metrics:
- Raw accuracy (correct/40) -- baseline: 8/40 (20.0%) with prompt-only
- Rule adherence (did the LLM follow binding rules when criteria were met?)
- Failure mode distribution (same failures? different failures? fewer enforcement failures?)
- Regression check on 5 constraint patients (1279, 1101, 1536, 1624, 1446)

## v1.1.0-dev: Three-Layer Fix Architecture

### Architectural Insight: Why Prompt-Only Fixes Are Insufficient

After implementing all 24 prompt fixes, testing showed only 8/40 target patients corrected. Root cause: the LLM reads negative signals (rising bilirubin, high creatinine) and emotionally overrides binding recovery rules despite explicit prompt instructions. The ~5000 word Committee Chair prompt has diminishing returns.

### Solution: Pre-Computed Criteria Injection

Instead of post-processing overrides (which "cheat" by silently replacing LLM predictions), inject structured data INTO the prompt:

1. **parse_vignette()**: Extract exact values from vignette text (INR improvement %, ALT decline %, peak values, trends)
2. **format_criteria_evaluation()**: Format as "CRITERIA CHECKLIST" showing each criterion as MET/NOT MET
3. **criteria_guided_reevaluation()**: If deterministic criteria disagree with LLM, second LLM call with explicit criteria guidance

This preserves LLM reasoning for the paper while eliminating calculation errors.

### Key Design Decisions

- **Pre-processing (criteria injection) over post-processing (silent override)**: User requirement for paper -- LLM reasoning must be genuine
- **Safety gates in evaluate_binding_rules()**: P1B not enforced when HE>=4 non-uremic (57.9% precision), near-recovery 5B not enforced (60% precision)
- **Extreme Bilirubin discordance blocks P1D**: Prevents regression on Patient 1536 (bilirubin >15 + HE>=2 + rising = death signal)
- **Combination Signal explicitly shown in criteria**: Prevents regression on Patient 1624 (P1C liver criteria + uremic HE = BINDING SURVIVAL)
- **Precision analysis across 1260 patients**: P1C 97.1%, P1D 97.5%, P1 93.2%, P1B 86.2% (with HE<=3 gate: 91.3%)

## v0.9.4-dev Full Evaluation: Batch 1-13 Failure Analysis (COMPLETE)

### Summary

| Batch | Accuracy | False Neg | False Pos | Errors | Total Wrong |
|-------|----------|-----------|-----------|--------|-------------|
| 1 (tuning set) | 99/100 (99.0%) | 1 | 0 | 0 | 1 |
| 2 (unseen) | 84/100 (84.0%) | 13 | 3 | 0 | 16 |
| 3 (unseen) | 87/100 (87.0%) | 10 | 3 | 0 | 13 |
| 4 (unseen) | 87/100 (87.0%) | 12 | 1 | 0 | 13 |
| 5 (unseen) | 87/100 (87.0%) | 11 | 2 | 0 | 13 |
| 6 (unseen) | 86/100 (86.0%) | 12 | 2 | 0 | 14 |
| 7 (unseen) | 92/100 (92.0%) | 8 | 0 | 0 | 8 |
| 8 (unseen) | 87/100 (87.0%) | 12 | 1 | 0 | 13 |
| 9 (unseen) | 86/100 (86.0%) | 14 | 0 | 0 | 14 |
| 10 (unseen) | 89/100 (89.0%) | 10 | 1 | 0 | 11 |
| 11 (unseen) | 91/100 (91.0%) | 6 | 3 | 0 | 9 |
| 12 (unseen) | 89/100 (89.0%) | 8 | 3 | 0 | 11 |
| 13 (unseen) | 53/60 (88.3%) | 7 | 0 | 0 | 7 |
| **FINAL TOTAL** | **1117/1260 (88.7%)** | **124** | **19** | **0** | **143** |

The dominant failure mode is **false negatives** (predicting death when patient survived): 124/143 total errors (86.7%). ALL 1,260 patients evaluated. Batch 8 originally had 2 API errors (5822, 5824) which were re-run successfully -- both were false negatives. Batch 7 was a positive outlier at 92%. Batch 8 thorough analysis revealed 4 patients (5762, 5882, 6166, 6257) where recovery criteria were DEMONSTRABLY MET but the committee failed to enforce them. Batch 9 thorough analysis revealed 3 more enforcement failures: Patient 6572 (P1 fully met -- bilirubin IS declining 15.1->13.8, committee subjectively dismissed decline as "not robust enough"), Patient 6466 (P1C actually met -- lactate 2.0 IS <=2.0, committee misread it), and Patient 6446 (committee explicitly acknowledged "1B IS met" then overrode it with Priority 2). Batch 9 also had 0 false positives (all 14 errors were false negatives) and introduced a new Issue G variant: Pre-Check C firing on non-APAP patients with excellent labs (Patient 6582). Batch 10 thorough analysis: 5 actionable patients (7142, 7688, 7442, 7114, 7297) fixable by existing Fixes #5/#7/#11, 1 false positive enforcement failure (7333 -- committee invented survival without binding rule), 5 noise floor (7155, 7265, 7515, 7546, 7555). New finding: Pre-Check B bilirubin exception structurally inaccessible at Day 2 (Patient 7114 -- INR hasn't had time to recover >50% from peak). New Issue B Variant F: committee invents survival prediction at Day 1 when no binding survival rule applies (INVERTED enforcement failure). Batch 11 thorough analysis: 3 highly actionable patients (8095, 8174, 8216), 1 moderate (8237), 2 noise floor FN (7777, 7830), 3 FP (7936, 8103, 8136). NEW Issue T: P1 negation too aggressive at PaO2/FiO2 boundary -- Patient 8095 is the first case where P1 negation correctly fires on its criteria (grade 4 HE + PaO2/FiO2 1.85) and produces a wrong answer. NEW Fix #24: tighten P1 negation from PaO2/FiO2 <2.0 to <1.5. FP analysis: 3 FPs represent framework noise floor -- patients died from signals not tracked (hypernatremia Na 163, bilirubin never-peaked pattern, ischemia recurrence). Batch 12 thorough analysis: 3 highly actionable (8465, 8557, 8762), 3 moderate (8447, 8725, 8968), 2 noise floor FN (8633, 8882), 3 FP (8632, 8732, 9009). Patient 8465: Extreme Bilirubin waiver ALL 5 conditions MET but committee rejected with invented 6th condition (3rd confirmed Issue B Variant B, after 3678/5151). Patient 8557: P1B FULLY MET but committee overrides with Extreme Bilirubin (Issue B / Fix #1). Patient 8762: CLEAREST Pre-Check B false positive in 1,200 patients -- ALFSG-PI 93.3%, all 3 specialists Yes, 77.6% INR improvement, HE 0, blocked solely by lactate 3.0 from Day 2 (Fix #6). NEW Issue B Variant G (Patient 9009 FP): committee claims P1B met by ignoring mandatory additional condition (lactate <2 OR HE 0-1 OR Cr improving), overrides 3/3 specialist No votes. Critical Fix #7 scoping: missing lactate must not SATISFY positive criteria, only remove blockers for waivers/exceptions. Batch 13 thorough analysis: 3 highly actionable (9040, 9452, 9717), 2 moderate (9580, 9691), 1 noise floor (9546), 1 borderline noise floor (9120), 0 FP. Patient 9040: P1B FULLY MET (peak INR 6.1, 72.1% improvement, ALT 83.4% down, lactate 1.4) -- committee explicitly stated "Priority 1B IS met" then predicted death anyway (Issue B enforcement failure, Fix #1). Patients 9452 and 9717: stale lactate sole blocker (Fix #7) -- 9452 has INR 1.06 (one of best recoveries in entire evaluation), 9717 has HE 0 + no organ support. Patient 9580: INR improvement 56.6% vs >60% threshold (3.4% short), ALT 93.5% down, 2/3 specialists Yes overridden by Extreme Bilirubin (Issue F near-miss). Patient 9691: CVVH masks creatinine for uremic HE determination -- ammonia 48 (<50), grade 4 HE, CVVH active (Issue K / Fix #11).

### Root Cause: The "Recovering But Still Looks Sick" APAP Phenotype

The archetypal false-negative patient:
- APAP etiology (favorable prognosis)
- Day 7 evaluation
- ALT dramatically down (>80-96% from peak -- necrosis clearly resolving)
- INR significantly improved from peak (often <2.0, sometimes near-normal)
- Bilirubin STILL RISING (excretory lag -- normal in APAP recovery)
- Grade 3-4 HE persisting (neurological recovery lags liver recovery)
- Often on mechanical ventilation (airway protection, not respiratory failure)
- No documented infection

The liver has recovered (INR + ALT prove it), but the system predicts death because bilirubin blocks all formal recovery criteria.

---

### Consolidated Issues (20 distinct patterns)

Issues deduplicated from 24 raw findings across Batches 2-9. Each issue lists all affected patients across all batches.

#### A. Rising Bilirubin Blocks All Recovery Pathways (~30+ patients)

*Merged from: original Issues 1, 16*

The single highest-impact issue. Rising bilirubin (excretory lag) disqualifies patients from every recovery pathway:
- **Priority 1** requires "bilirubin declining" -- rising bilirubin disqualifies
- **Priority 1B** has no bilirubin requirement BUT the LLM overrides 1B with Extreme Bilirubin rules
- **Priority 1C** bilirubin lag exception requires HE 0-1 AND no ventilation -- excludes ventilated patients
- Result: patients with near-normal INR and ALT >80% down have ZERO recovery pathways when bilirubin rises

**APAP variant** (most patients): Bilirubin lag is normal in APAP recovery and does not indicate failed regeneration.
**Non-APAP variant** (Patient 3247): Bilirubin lag exception is APAP-only. Non-APAP patients with rising bilirubin have no pathway even with ALT 86% down and lactate 1.8.

Affected patients: 1652, 1673, 1776, 1788, 1885, 1887, 1932, 1933, 1990, 2011, 2184, 2323, 2584, 2741, 2812, 2821, 2884, 3089, 3247, 3678, 3742, 3899, 3907, 4051, 4323, 4339, 4429, 4509, 4513, 4564, 4623, 4658, 4662, 4674, 4677, 4768, 4823, 5109, 5151, 5251, 5364, 5573, 5762, 5781, 5822, 5824, 5882, 5973, 6166, 6216, 6257, 6323, 6325, 6412, 6415, 6417, 6446, 6451, 6466, 6477, 6531, 6572, 6737, 6743, 6821, 6847, 7142, 7155, 7265, 7297, 7442, 7515, 7555, 7688, 7830, 8174, 8216, 8237, 8447, 8465, 8557, 8725, 8968, 9040, 9120, 9452, 9546, 9580, 9691, 9717

#### B. Priority Hierarchy Not Enforced: 1B/Waiver Overridden by Death Rules (~13 patients)

*Merged from: original Issues 2, 21, 22*

The LLM overrides BINDING Priority 1B or the Extreme Bilirubin 5-condition waiver with lower-priority death rules (Rule 5B, Extreme Bilirubin). The prompt says these death rules apply "ONLY if NO recovery criteria met," but the LLM loses track of the priority ordering. Five manifestations:

**Variant A -- 1B met but death rule applied anyway:**
- Patient 2588: 1B clearly met (peak INR 5.5, current 1.2, 78% improvement, ALT down 96.5%) but Extreme Bilirubin override applied
- Patient 2678: 1B met (peak INR 6.1, current 1.74, 71.5% improvement, creatinine improving) but Rule 5B applied
- Patient 2723: 1B met (peak INR 12.0, current 2.8, 76.7% improvement, creatinine improving) but dismissed
- Patient 3760: 1B met (peak INR 5.3, current 1.6, 69.8% improvement, ALT 88.7% down) but Extreme Bilirubin override applied

**Variant B -- Committee invents extra non-framework conditions for waiver:**
- Patient 3678: ALL 5 Extreme Bilirubin waiver conditions met (HE 0, lactate 1.1, no vent, no pressors, no infection) but committee denied waiver claiming INR "never improved" -- the framework does not require INR improvement for the waiver
- Patient 5151: ALL 5 Extreme Bilirubin waiver conditions met (HE 0, lactate 1.4, no vent, no pressors, no infection) but committee rejected waiver claiming bilirubin 27.1 is "far beyond expected lag" and "signals catastrophic excretory failure rather than benign lag." The framework has BINARY waiver conditions -- it does NOT distinguish bilirubin 16 vs 27 vs 40 mg/dL. Committee invented a hidden 6th condition: "magnitude must be typical APAP lag."

**Variant C -- Missing data blocks waiver, allowing death rule to override met 1B:**
- Patient 4042: Committee acknowledged 1B fully met (peak INR 5.2, 69.2% improvement, ALT 89.3% down, HE 0, creatinine improving) but applied Extreme Bilirubin because lactate was not reported -- missing data should not allow Priority 2 to override met Priority 1B

**Variant D -- 1B met but "extrahepatic deterioration" reasoning overrides it:**
- Patient 4823: Committee explicitly acknowledged "Priority 1B IS met biochemically: peak INR 6.6, 77% improvement, ALT >80% down" but then wrote "Priority 1B does not immunize against major ongoing non-hepatic mortality drivers" and cited ventilation + grade 4 HE + PaO2/FiO2 1.29. However: ventilation was for airway protection (no pressors, no infection, creatinine 1.0), not respiratory failure. This represents misclassifying airway-protection ventilation as multi-organ failure.

**Variant E -- Committee conflates "vent for airway protection" with "respiratory failure":**
- Patient 4823 (overlap with Variant D): PaO2/FiO2 1.29 is mild-moderate, no pressors, no infection, creatinine 1.0 (normal). Only true organ dysfunction is neurologic (grade 4 HE), which is hepatic. Committee treated this as "multi-organ failure phenotype" -- but ventilation for airway protection during HE is standard ICU practice, not an independent organ system failure.

**Batch 8 enforcement failures (most actionable finding):** Four Batch 8 patients had recovery criteria DEMONSTRABLY MET but the committee failed to enforce them:
- Patient 5762: **Priority 1 FULLY MET** (INR 1.4 <1.5, ALT 98.4% down, bilirubin 4.9->4.1 DECLINING). Committee wrote "Priority 1/1B/1C recovery criteria are met only partially" -- factually incorrect. P1 negation requires grade 4 HE (patient has grade 3) AND PaO2/FiO2 <2.0 (patient has 2.5). Negation does NOT apply. The prompt explicitly says "vent, grade 3 HE, AKI do NOT negate Priority 1." Most egregious enforcement failure in the dataset.
- Patient 5882: **Priority 1B MET** (peak INR 5.9, 76% improvement, ALT 89% down, creatinine improving 7.1->4.5). Committee denied 1B claiming creatinine "not clearly documented as improving" -- a 36.6% one-day creatinine drop from 7.1 to 4.5 is unambiguously improving. Issue F (creatinine "improving" not defined) is the root cause.
- Patient 6166: **Priority 1B MET** (peak INR 5.4 >5, 72.2% improvement >60%, ALT 89.1% >80%, HE grade 1 satisfies additional condition). Negation requires ALL THREE of rising lactate + worsening creatinine + infection; only lactate rising (1/3). Committee overrode with ammonia 165 rebound and extrahepatic concerns -- violating the binding priority hierarchy.
- Patient 6257: **Priority 1B MET** (peak INR 6.7 >5, 75.1% improvement >60%, ALT 89.8% >80%, lactate 1.5 <2 satisfies additional condition). Committee never evaluated 1B -- instead applied 1C bilirubin lag requirements (HE 0-1, no vent) which are irrelevant to 1B. Conflation of 1B and 1C criteria.

**Patient 5824 -- unanimous specialist override:** All 3 specialists predicted SURVIVE (Hep=Yes 0.74, CC=Yes 0.66, TS=Yes 0.72) but committee overrode to death because bilirubin 18.8->18.9 (+0.1 mg/dL) blocks P1, peak INR 2.0 blocks 1B, and HE grade 2 + ventilation blocks 1C bilirubin lag exception. This is the worst committee-override-of-correct-specialist-vote case in the entire dataset.

**Batch 9 enforcement failures (3 more patients with criteria demonstrably met):**
- Patient 6572: **Priority 1 FULLY MET** (INR 1.4 <1.5, ALT 93.9% >80%, bilirubin 15.1->14.0->13.8 IS declining). Committee subjectively dismissed the decline as "not robust enough." HE grade 3, P1 negation requires grade 4 HE AND PaO2/FiO2 <2.0 -- negation does NOT apply. Pure enforcement failure identical to 5762.
- Patient 6466: **Priority 1C ACTUALLY MET** (peak INR 2.2 in 2-5 range, ALT 94% down, bilirubin declining 22.3->18.5, lactate 2.0 IS <=2.0). Committee misread lactate as failing the <=2.0 condition. Also INR exactly 1.5 blocks P1 (Issue F). Triple near-miss: INR exactly 1.5, ammonia 59 (just above 50 for uremic HE), lactate exactly 2.0. CLEAREST Issue F case in entire 900-patient evaluation.
- Patient 6446: Committee **explicitly acknowledged** "Priority 1B IS met" (peak INR exactly 5.0, 78% improvement, ALT 89.3% down) then wrote that it "does not supersede Priority 2" -- a **direct violation** of the binding priority hierarchy. Stale lactate 22.6 identical all 7 days. Zero regression risk from changing >5.0 to >=5.0 (Fix #5).

**Patient 6412 -- second unanimous specialist override:** All 3 specialists predicted SURVIVE (INR 1.1 fully normalized!, lactate 0.8, ammonia 29) but committee overrode because no formal pathway met (bilirubin 15.9 rising blocks P1, HE grade 3 + vent blocks 1C exception). Third case of 3/3 specialist survive vote overridden by committee (after 5824 in Batch 8).

**Variant F -- INVERTED: Committee invents survival without binding rule (Batch 10 FP):**
- Patient 7333 (FALSE POSITIVE -- Day 1): Committee predicted SURVIVE when only 1/3 specialists predicted survive, ALFSG-PI 82.5% (below 85% Favorable Override threshold), and NO binding survival rule applied. Ammonia 211 was non-binding per Day 1 exception (HE 1, no vent, no pressors). 2/3 specialists predicted death. Committee overrode toward survive without any framework justification -- the inverse of the typical Issue B pattern where committee overrides survival rules toward death. Fix: enforce weighted specialist vote at Day 1 when no binding override fires.

**Variant G -- Committee claims P1B met by ignoring mandatory additional condition (Batch 12 FP):**
- Patient 9009 (FALSE POSITIVE -- Day 7): Committee overrode 3/3 specialist No votes by claiming P1B was met (peak INR 6.49, 63% improvement, ALT 86% down). However, P1B requires a mandatory additional condition: lactate <2 OR HE 0-1 OR creatinine improving. NONE met (lactate not provided, HE grade 4, creatinine worsening 0.9->1.7). Committee explicitly acknowledged missing additional conditions but treated them as optional. The Committee Chair prompt's P1B wording ("INR >60% improved + ALT >80% down + lactate <2 or HE 0-1 or creatinine improving") is ambiguous -- LLM parsed the third element as optional rather than required. Fix: clarify P1B prompt to make three-component conjunction unambiguous.

**Batch 12 enforcement failures:**
- Patient 8465: **ALL 5 Extreme Bilirubin waiver conditions MET** (HE 0, lactate 1.4, no vent, no pressors, no infection) but committee rejected waiver claiming "bilirubin is rising with no peak/decline at all by Day 7" -- INVENTED 6th condition. The waiver is BINARY and exists PRECISELY for when bilirubin is still rising. 3rd confirmed Issue B Variant B (after 3678, 5151). Strongest evidence Fix #19 is critical.
- Patient 8557: **P1B FULLY MET** (peak INR 5.69, 64.9% improvement, ALT 91.7% down, HE grade 1 satisfies additional condition). Committee overrides with Extreme Bilirubin despite P1B taking priority. Infection present complicates negation analysis (requires ALL THREE: rising lactate + worsening Cr + infection), but committee did not properly evaluate negation.
- Patient 8968: **P1 likely MET** (INR 1.4, ALT ~90% down, bilirubin 16.4->15.7 IS declining). Committee dismissed 0.7 mg/dL decline as "not clearly declining." HE grade 2 = P1 negation does NOT fire (requires grade 4). Same pattern as 6572 (bilirubin decline subjectively dismissed).

**Batch 13 enforcement failures:**
- Patient 9040: **P1B FULLY MET** (peak INR 6.1, 72.1% improvement, ALT 83.4% down, lactate 1.4 satisfies additional condition). Committee EXPLICITLY STATED "Priority 1B IS met" then overrode with extrahepatic concerns (ventilation + HE grade 3 + PaO2/FiO2 1.98 + Cr 4.3). P1B negation requires ALL THREE: rising lactate + worsening Cr + new infection -- lactate 1.4 is NOT rising, so negation impossible. Same pattern as 4823 (Variant D) and 6446 (acknowledged met then overridden). 11th confirmed enforcement failure across Batches 8-13.

Affected patients: 2588, 2678, 2723, 3760, 3678, 4042, 4513, 4677, 4768, 4823, 5151, 5762, 5824, 5882, 6166, 6257, 6412, 6446, 6466, 6572, 7333 (FP), 8465, 8557, 8968, 9009 (FP), 9040

#### C. Rule 5B (Grade 4 HE Death Override) Too Aggressive (~9 patients)

Rule 5B mandates death when: grade 4 HE + not uremic + no formal recovery criteria met. But because bilirubin blocks formal recovery recognition, Rule 5B captures patients whose livers have clearly recovered (INR <1.5, ALT >80% down).

Affected patients: 2678, 2723, 3089, 3218, 4029 (partial), 4429, 4564, 4623, 5781, 5822, 6417, 6466, 6477, 6531, 6821, 7265, 7297, 7555, 7777, 7830, 8633, 9691 (grade 4 HE + CVVH + ammonia 48)

#### D. 1C Bilirubin Lag Exception Too Restrictive (~11 patients)

Requires HE 0-1 AND no ventilation. Excludes patients ventilated for airway protection during HE (standard ICU practice). These patients can have fully recovered livers while still intubated.

**HE grade 2 near-miss sub-pattern:** Patient 4662 has HE grade 2 (just above 0-1 cutoff), INR 1.4 (improving from 2.9), ALT 93% down, APAP. The 1C exception requires HE 0-1, and grade 2 represents improving neurological function that just misses the threshold. Expanding to HE 0-2 when trajectory is improving would capture these cases.

Affected patients: 1885, 1887, 1932, 1990, 2011, 2584, 2741, 3742, 3743, 3875, 4662, 5109, 5781, 5824, 5973, 6323, 6412, 6415, 6417, 6446, 6466, 6477, 6743, 6821, 6847, 7155, 7442, 7515, 7555, 8237, 8447, 9120 (HE 3 + vent blocks lag exception), 9546 (HE 3 + vent + pressors + infection), 9691 (HE 4 + vent blocks lag exception -- uremic HE if CVVH-aware)

#### E. Recovery Pathway Coverage Gaps

**Peak INR <2.0 gap (~3 patients):** Patients with initially moderate INR (<2.0) who normalize quickly have NO recovery pathway. Priority 1B requires peak INR >5.0, Priority 1C requires peak INR 2.0-5.0, only Priority 1 applies which requires bilirubin declining.
- Patient 2228: peak INR 1.5, current INR 1.4 (near-normal), ALT >80% down, but ZERO pathways available.
- Patient 4674: peak INR 2.0 (boundary), current INR 1.7, ALT 90% down, bilirubin rising -- falls between 1C (needs peak >2.0) and 1B (needs peak >5.0).

**Non-APAP bilirubin lag gap (1 patient):** Patient 4623 has indeterminate (non-APAP) etiology, INR 1.27 (low), lactate 0.9, ALT declining, but bilirubin rising 8.3->12.2. The bilirubin lag exception is APAP-only. Non-APAP patients with low INR and low lactate and rising bilirubin have NO survival pathway. Proposed: non-APAP bilirubin lag exception when INR <=1.5 AND lactate <=2.0.

**Day 4 gap (~2 patients):** Priority 1/1B/1C are Day 5+ only. Day 4 patients with rapidly normalizing INR (<1.5) have no mechanism for survival prediction unless the Day 4 binding rule fires (requires grade 4 HE + PaO2/FiO2 <2.0).

**Day 1 ALFSG-PI threshold too strict (1 patient):** Day 1 Favorable Override requires ALFSG-PI >85%. Patient 2805 at 80.9% with no organ support predicted to die.

**Completely missing lactate blocks ALL pathways (1 patient):** Patient 6325 has NO lactate measurement across all 6 days. Missing lactate blocks both the 1C lactate <=2 condition and the Extreme Bilirubin waiver. Combined with worsening creatinine, ZERO pathway opens despite INR 1.3, ALT 90% down, HE grade 1, no vent, no pressors, ALFSG-PI 85.9%. When lactate was never measured AND there is no hemodynamic instability (no pressors, no acidosis), missing lactate should not block recovery pathways.

**Non-APAP Pre-Check C gap (1 patient):** Patient 6582 has indeterminate etiology at Day 3 with excellent labs (INR 1.3, bilirubin 1.5, ALFSG-PI 88.4%, no pressors, no infection, HE improving 3->2). Pre-Check C mandates death for all ventilated Day 1-3 patients regardless of etiology. Fix #21 variants are APAP-only. Non-APAP patients with preserved liver function caught by Pre-Check C need a separate exception (see Fix #23).

**Day 1 Favorable Override too narrowly coupled (1 patient):** Patient 7546 has ALFSG-PI 88.4% (>85%), INR 1.3 (low), HE grade 4, no organ support at Day 1. Day 1 Favorable Override exists but is coupled to Pre-Check B exception context, making it inaccessible when Pre-Check B doesn't fire. Possible Fix #24 (ALFSG-PI >=88% + APAP + no organ support + INR <2.0 override) but regression risk with Patient 3892 (ALFSG-PI 86.7%, died). Borderline noise floor.

Affected patients: 2228, 2805, 4623, 6325, 6582, 7546, 7777 (peak INR 1.9 gap + INR 1.8 above threshold) + Day 4 patients

#### F. Threshold Near-Miss / Boundary Issues (~9 patients)

*Merged from: original Issues 7, 8, 18, 20*

Patients miss recovery criteria by clinically meaningless margins:

**INR <=1.5 boundary:** Patient 2738 has INR exactly 1.50, misses Priority 1 which requires strictly <1.5. Should be <=1.5. Patient 4029 has INR 1.6 (misses by 0.1).

**ALT 77-80% near-miss:** ALT declining 77-79% is below strict >80% threshold, blocking 1B and 1C.
- Patient 3566: INR fully normalized to 1.0 with HE grade 0 but ALT 78.7% blocks all pathways
- Patient 3534: 66.7% INR improvement but ALT 77.2% blocks 1B
- Patient 3343: ALT 69.8% blocks recovery
- Patient 3899: INR improvement 57.1% (just below >60% threshold for 1B)
- Patient 3907: ALT 73.2% blocks recovery

**Compound boundary near-miss:** Patient 4429 has peak INR 4.9 (misses 1B >5.0 by 0.1) AND current INR 1.5 (misses P1 <1.5 by 0.0). Patient 4674 has bilirubin 10.9 exceeding own peak of 10.8 by 0.1 mg/dL, treated as "rising" and blocking all pathways.

**"Creatinine improving" not defined:** LLM dismisses obvious creatinine improvement (7.3 to 6.8, 0.8 to 0.7) as insufficient. Needs precise definition: "most recent creatinine lower than prior value."
- Affected: 2678, 2723

**ATN creatinine inconsistency between 1B and 1C:** Prompts say "isolated creatinine worsening is ATN lag in APAP, NOT multi-organ deterioration" for 1B negation. But 1C bilirubin lag exception requires creatinine "stable or improving." Creatinine is dismissed as ATN in one context but treated as a blocker in another.
- Affected: 3576, 6325 (creatinine 2.5->7.0 monotonically worsening blocks 1C bilirubin lag exception despite being isolated ATN in APAP with no other organ failure)

**Bilirubin micro-rise treated as "rising":** Bilirubin increase of 0.1 mg/dL (within measurement error) is treated identically to a 5 mg/dL rise. Patient 5824: bilirubin 18.8->18.9 (+0.1) blocks Priority 1. Patient 5882: bilirubin 7.1->7.2 (+0.1) blocks Priority 1. Patient 6323: bilirubin 18.5->18.6 (+0.1) blocks Priority 1. A tolerance of +/-0.5 mg/dL for bilirubin "stable/declining" would fix all three.
- Affected: 5824, 5882, 6323

**Normal creatinine at baseline doesn't satisfy "creatinine improving":** Patient 6216 has creatinine 0.7 mg/dL (completely normal) throughout admission. There is nothing to "improve" from. The 1B additional condition requires "creatinine improving" but a normal creatinine at baseline should automatically satisfy this. Proposed: "creatinine improving OR creatinine at normal baseline (<1.2 mg/dL)."
- Affected: 6216

**Peak INR exactly 5.0 boundary (1B):** Patient 6446 has peak INR exactly 5.0. Priority 1B requires peak INR >5.0. The committee explicitly acknowledged "1B IS met" but the strict >5.0 condition technically excludes 5.0 exactly. Changing to >=5.0 has ZERO regression risk (no Batch 1 death had peak INR exactly 5.0).
- Affected: 6446

**Compound near-miss escalation in Batch 9:**
- Patient 6466: TRIPLE near-miss -- INR exactly 1.5 (blocks P1 <1.5), ammonia 59 (just above 50 for uremic HE), lactate exactly 2.0 (P1C requires <=2.0 which IS met but committee misread it)
- Patient 6737: DOUBLE near-miss for 1B -- INR improvement 56.5% vs 60% threshold (3.5% short) AND ALT 79.6% vs 80% threshold (0.4% short)
- Patient 6743: TRIPLE near-miss -- ALT 79.0% vs 80% + HE grade 2 vs 0-1 (for Extreme Bilirubin waiver) + INR 1.6 vs <1.5
- Patient 6531: DOUBLE boundary -- INR exactly 1.5 (blocks P1) + bilirubin micro-rise +0.1 mg/dL. Also infection documented, which complicates fixes.
- Patient 6821: COMPOUND near-miss -- peak INR 4.7 vs >5.0 (blocks 1B) + lactate 2.3 vs <=2.0 (blocks 1C)
- Patient 6415: ALT 78% (below 80% by 2%), pressors active all 7 days (fundamental blocker for all pathways)

**Batch 10 boundary/threshold patterns:**
- Patient 7114: Bilirubin micro-rise 6.0->6.1 (+0.1) triggers Pre-Check B binding death at Day 2. 5th confirmed micro-rise case (after 5824, 5882, 6323, 6531). Fix #5 micro-rise tolerance directly fixes.
- Patient 7155: INR 1.6 (genuine above threshold, not boundary). Multi-criterion genuine failure, noise floor.
- Patient 7442: ATN creatinine inconsistency. 1C bilirubin lag exception blocked SOLELY by creatinine worsening 1.3->2.4->3.6 (ATN in APAP). ALL other conditions met: HE 1, lactate 1.4, no vent, no pressors, ammonia 21. Fix #5 ATN Cr resolution directly fixes. VERY HIGH fixability.
- Patient 7297: Lactate 2.9 vs <=2.0 boundary for 1B additional condition. 1B liver labs fully met (peak INR 5.4, 63% improvement, ALT >80%). APAP mitochondrial lactate context applies.
- Patient 7688: Stale lactate 2.3 from Day 1 (6 days stale) blocks Extreme Bilirubin waiver. Fix #7 directly fixes.

**Batch 11 boundary/threshold patterns:**
- Patient 8095: PaO2/FiO2 1.85 vs 2.0 threshold for P1 negation. P1 FULLY MET (INR 1.4, ALT >92% down, bilirubin declining) but negation fires at PaO2/FiO2 just 7.5% below threshold. First correct-but-wrong P1 negation case. NEW Issue T / Fix #24.
- Patient 8237: INR exactly 1.5 (blocks P1 <1.5) + HE grade 2 (blocks 1C lag exception HE 0-1) + vent (blocks 1C lag exception) + ATN Cr 2.5->3.1 (blocks 1C Cr condition). Compound triple block. Fix #2 + Fix #5 combined.
- Patient 8174: 1B liver labs met (73.5% INR improvement, ALT 93% down) but additional condition blocked by: missing lactate, HE 4, Cr 1.1->1.7 (ATN). Fix #7 or Fix #5 either sufficient.

**Batch 12 boundary/threshold patterns:**
- Patient 8633: Peak INR 4.6 (misses 1B >5.0 by 0.4), current INR 1.6 (misses P1 <1.5 by 0.1). Compound near-miss similar to 4429 (peak INR 4.9). Grade 4 HE + ammonia 80 + Na 167 + pH 7.29 -- too close to constraint 1279.
- Patient 8762: Lactate 3.0 vs <=2.0 boundary for Pre-Check B exception. Pre-Check B fires on bilirubin rising (1.6->4.5) but the exception requires lactate <=2.0. Lactate 3.0 is from Day 2 (5 days stale). Fix #6 (bilirubin magnitude threshold) would bypass this entirely.

**Batch 13 boundary/threshold patterns:**
- Patient 9580: INR improvement 56.6% vs >60% threshold (3.4% short). Peak INR 5.3, ALT 93.5% down (exceptionally strong). 2/3 specialists predicted survive but committee overrode with Extreme Bilirubin (bilirubin 16.2 rising). Same pattern as 3899 (57.1%) and 6737 (56.5%). Possible Fix #5 extension: P1B INR improvement >=55% when ALT >90% down. Patient 1101 (constraint) had ALT 74% -- would NOT qualify. Low regression risk.
- Patient 9691: Bilirubin 15.43 -- just barely above 15 threshold for Extreme Bilirubin (by only 0.43 mg/dL). Combined with CVVH masking Cr for uremic HE determination.

#### G. Pre-Check B/C Too Sensitive / Aggressive (~5 patients)

*Merged from: original Issues 19, 24*

Pre-Check B and C fire inappropriately in several scenarios:

**Trivial value changes:** Bilirubin 1.4 -> 2.2 (+0.8, both very low values) at Day 2 triggers BINDING death prediction. No magnitude threshold -- ANY rise triggers it. Sub-3 mg/dL bilirubin with 0.8 mg/dL increase is clinically meaningless.
- Patient 3610

**Stale data without trend:** Pre-Check B requires "lactate >4 not declining" at Day 2-3. Patient 3778 at Day 2 only has a Day 1 lactate of 14 with NO Day 2 measurement. Cannot determine decline without a second data point. Patient is otherwise well (HE 0, no organ support, INR 1.2 normal).
- Patient 3778

**Pre-Check C too aggressive for rapidly recovering APAP Day 3:** Pre-Check C mandates death for all ventilated Day 1-3 patients. Patient 5385 at Day 3 has INR 10.0->1.8 (82% improvement) and ALT 91.5% down -- one of the most dramatic recoveries in the dataset -- but is ventilated so pre-check mandates death. Patient 5145 has Day 3 ammonia 363 and lactate 8.7 (alarming but APAP patients can survive extreme early values).
- Patient 5145 (Day 3, ammonia 363, lactate 8.7, ventilated -- genuinely extreme values, may represent noise floor)
- Patient 5385 (Day 3, INR 82% improved, ALT 91.5% down, bilirubin DECLINING, ventilated)
  - KEY DETAIL: Patient 5385 was EXTUBATED on Day 2 then RE-INTUBATED on Day 3. The extubation attempt proves the ICU team judged the patient stable enough for extubation trial -- fundamentally inconsistent with "severe multi-organ failure" narrative. Reintubation on Day 3 was likely for airway protection during improving HE (grade 3->2), not progressive respiratory failure.
- Patient 6142 (Day 3, INR improving 2.3->1.7, HE dramatically improving grade 3->1, ventilated, no pressors, no infection, ammonia 58, pH 7.44, PaO2/FiO2 4.76). Pre-Check C mandates death but HE trajectory (3->1) proves neurological recovery -- ventilation is for airway protection, not respiratory failure. Fix #21 is too narrow for this case (requires INR >75% improved, ALT >90% down -- patient has only 26% INR improvement and 21% ALT decline at Day 3). Needs HE-trajectory variant: Pre-Check C exception when HE improved from grade 3-4 to grade 0-1 between consecutive days AND APAP AND no pressors AND no infection AND ammonia <=150.
- Patient 6582 (Day 3, **indeterminate etiology** -- NOT APAP, INR 1.3, bilirubin 1.5, ALFSG-PI 88.4%, no pressors, no infection, HE improving 3->2, ventilated). Pre-Check C mandates death. Fix #21 variants are APAP-only and would NOT cover this patient. Labs are excellent: INR near-normal, bilirubin trivial, high ALFSG-PI. **NEW PATTERN: Non-APAP Pre-Check C gap.** Proposed Fix #23: Pre-Check C exception for non-APAP with preserved liver function (INR <=1.5 + bilirubin <=3 + ALFSG-PI >=80% + no pressors + no infection + HE improving).
- Patient 7114 (Day 2, APAP, bilirubin micro-rise 6.0->6.1 (+0.1) triggers Pre-Check B binding death, INR 8.43 not yet recovered). **NEW PATTERN: Pre-Check B bilirubin exception structurally inaccessible at Day 2** -- the exception requires INR >50% recovered from peak, but at Day 2 INR has not had enough time to recover from peak of 8.43. Fix #5 micro-rise tolerance (<=0.5 mg/dL = "stable") would resolve this by preventing Pre-Check B from firing on trivial bilirubin changes. 2 of 3 specialists predicted survive.
- Patient 8762 (Day 7, APAP, bilirubin 1.6->4.5 rising triggers Pre-Check B, lactate 3.0 from Day 2 blocks exception). **CLEAREST Pre-Check B false positive in 1,200 patients.** ALFSG-PI 93.3%, ALL 3 specialists Yes, 77.6% INR improvement from peak 6.7, HE 0, no organ support. Bilirubin magnitude is trivial (4.5 is very low). Fix #6 (require bilirubin >5 for Pre-Check B trigger) directly and completely fixes. Near-zero regression risk.

#### H. Stale / Missing Data Blocks Pathways (~7 patients)

**Stale HIGH lactate blocks Extreme Bilirubin waiver:** Waiver requires lactate <=2.0. Only available lactate is stale (e.g., Day 2 value of 4.3 for a Day 7 patient). Stale Lactate Provision only covers stale LOW lactates (<=2.0). A 5-day-old high lactate denies the waiver despite patient being clinically benign.
- Patient 3243 (stale 4.3), Patient 3875 (stale 4.9), Patient 4051 (stale 9.6)

**Stale lactate detection via identical values across days:** When lactate is reported as the EXACT SAME value across 3+ consecutive days, it is almost certainly a data artifact (EHR carry-forward, not re-measured). These should be treated as stale.
- Patient 5364: Lactate 7.0 identical Days 1-7 (7 consecutive days). Patient is off vent/pressors on Day 7 with pH 7.42, HCO3 24. Stale lactate blocks Extreme Bilirubin waiver.
- Patient 5573: Lactate 6.4 identical Days 2-7 (6 consecutive days). Patient has no vent, no pressors, HE 0. Physiologically implausible.

**Missing lactate blocks pathways:** When lactate is not reported at all, the system treats it as failing the condition rather than as missing data.
- Patient 4042 (covered under Issue B above)
- Patient 4823: No lactate reported any day. Blocks Extreme Bilirubin waiver despite 1B being met.
- Patient 6325: NO lactate across all 6 days. Blocks both 1C lactate <=2 and Extreme Bilirubin waiver. (Also see Issue E)

**Batch 8 stale data patterns:**
- Patient 5762: Lactate 26.0 from Day 3 (4 days stale). APAP Type B lactic acidosis context applies. Biased all 3 specialists toward death despite P1 being met.
- Patient 5822: Lactate 21.9 from Day 1 (6 days stale, identical all 7 days). Ammonia 49 from Day 1 (6 days stale). Both block pathways.
- Patient 5973: Lactate 6.2 from Day 2 (5 days stale, carried forward). Patient on no pressors since Day 1, pH 7.45 -- stale lactate is clinically irrelevant.
- Patient 6216: Lactate 5.5 from Day 1 (6 days stale, identical all 7 days). Classic stale data artifact per Fix #20.
- Patient 6323: Lactate 2.9 from Day 1 (6 days stale, identical all 7 days).

**Batch 9 stale data patterns:**
- Patient 6446: Lactate 22.6 identical all 7 days (classic stale artifact). Committee used this stale value to override 1B despite acknowledging 1B was met.
- Patient 6477: Bilirubin monotonically rising 9.7->22.6 over 7 days (NEVER peaked). This is not stale data but a case where bilirubin never showed any decline -- makes "declining" threshold impossible to meet.
- Patient 6531: Stale data contributing to compound boundary failure.
- Patient 6737: Stale high lactate blocks Extreme Bilirubin waiver. Fix #7 would allow waiver when lactate is stale and no hemodynamic instability.
- Patient 6821: Ammonia NEVER reported across all 7 days + creatinine 5.7 >5.0. Missing ammonia blocks uremic HE determination. Fix #12 (presume uremic when ammonia missing + Cr >5) would fix.
- Patient 6415: Stale data contributing to pathway blockage.

**Batch 10 stale/missing data patterns:**
- Patient 7142: Lactate NEVER reported across all days. Missing lactate blocks Extreme Bilirubin waiver despite INR 1.4 (<1.5), ALT 88.5% down, HE 0, no organ support. Fix #7 (missing lactate provision) directly fixes.
- Patient 7688: Stale lactate 2.3 from Day 1 (6 days stale) at Day 7 assessment. Fix #7 (stale lactate >72h) directly fixes. INR 1.4, ALT 88% down, HE 1, no organ support.
- Patient 7265: Ammonia NEVER reported, creatinine 5.9. Fix #12 (presume uremic when ammonia missing + Cr >5) would apply but patient is noise floor regardless.

**Batch 11 stale/missing data patterns:**
- Patient 8216: Lactate NEVER reported. Missing lactate blocks both 1C bilirubin lag exception and Extreme Bilirubin waiver. Dramatic INR recovery 4.6->1.6, ALT >80% down, HE 1, no vent/pressors/infection. Fix #7 directly fixes. One of the cleanest Fix #7 cases in the evaluation.
- Patient 8174: Lactate not reported at assessment day. Blocks 1B additional condition (lactate <2 arm). 1B liver labs unambiguously met (peak INR 9.8, 73.5% improvement, ALT 93% down). Fix #7 directly fixes. Ammonia also not reported (Issue L overlap).

**Batch 12 stale/missing data patterns:**
- Patient 8725: Lactate NEVER reported. Missing lactate sole blocker. No vent, no pressors, no CVVH, no infection, HE 1, ALT 71 (near-normal). Textbook Fix #7 case -- 20+ total affected patients across evaluation.
- Patient 8447: Stale lactate 3.4 from Day 3 (4 days stale). Extreme bilirubin 30.2 rising. Stale high lactate blocks Extreme Bilirubin waiver (requires <=2.0). Fix #7 stale high lactate provision directly addresses.
- Patient 8968: Stale lactate 7.7 from Day 1 (6 days stale). P1 likely met (INR 1.4, bilirubin 16.4->15.7 declining) but stale lactate biases specialists toward death. Fix #7 staleness detection would neutralize this bias.

**Batch 13 stale/missing data patterns:**
- Patient 9452: Stale lactate 2.3 from Day 2 (5 days stale). SOLE BLOCKER for both Extreme Bilirubin waiver and 1C lag exception. INR 1.06 (one of BEST recoveries in 1,260 patients), ALT 91% down, HE 0, ALFSG-PI 85.7%, no organ support. Meets 4 of 5 waiver conditions (HE 0, no vent, no pressors, no infection). Fix #7 directly and completely fixes.
- Patient 9717: Stale lactate 7.8 from Day 2 (5 days stale). SOLE BLOCKER for both Extreme Bilirubin waiver and 1C lag exception. HE 0, no vent, no pressors, no infection, Cr 0.75 (excellent). Meets 4 of 5 waiver/exception conditions. Fix #7 directly fixes. CC specialist correctly identified "lactate from Day 2 not reliable for Day 7" but system still forced death prediction.
- Patient 9120: Lactate NEVER reported. Missing lactate contributes to pathway blockage but NOT sole blocker (HE 3 + ventilation also block). Fix #7 partially addresses but compound blockers remain.

#### I. APAP Lactate Context Not Applied (~2 patients)

Prompt has explicit Type B lactic acidosis language but specialists override with "persistent extreme hyperlactatemia." Oscillating lactate pattern (3.44 -> 19 -> 11 -> 14 -> 12) with no vasopressors should trigger the APAP lactate context clause.

- Patient 3029 (also has Issue J below), Patient 3778 (partial)

#### J. Priority 1 Bilirubin <3 Alternative Not Recognized (1 patient)

Priority 1 says "bilirubin declining (or near-normal <3 mg/dL)" but committee only checks declining trend, not the <3 fallback. Patient 3029: bilirubin 2.3 (<3) satisfies Priority 1, but committee wrote "declining trend not provided" without checking the alternative.

#### K. CVVH Masks Creatinine for Uremic HE Determination (~2 patients)

Pre-Check A requires creatinine >5 for uremic HE determination. CVVH artificially lowers creatinine to 1.0. Patient 3133 has ammonia 17 (<50) + grade 4 HE -- strongly suggests uremic/non-hepatic coma -- but CVVH-lowered creatinine blocks the determination. No rule exists for "if CVVH active, creatinine cannot be used to EXCLUDE uremic HE."

**CVVH discontinuation creatinine rebound variant:** Patient 4677 was on CVVH Days 2-5 (creatinine 1.2), CVVH stopped Day 6, creatinine rebounds to 2.9 by Day 7. The creatinine rise is a predictable CVVH discontinuation artifact, NOT new organ deterioration. System interprets the 1.2->2.9 rise as "creatinine worsening" and blocks recovery pathways. Proposed: creatinine rise within 48h of CVVH discontinuation should be flagged as CVVH rebound, not true deterioration.

**CVVH blocks uremic HE determination (ongoing variant):** Patient 5973 has ammonia 45 (<50), HE grade 3, but creatinine only 3.4 WHILE ON CVVH (active all 7 days). True native creatinine would be much higher. Uremic HE check requires Cr >5 -- impossible to meet while on CVVH. The dramatic ammonia decline (429->45) is one of the strongest recovery signals in the dataset but contributes nothing because CVVH masks the creatinine. Fix #11 directly addresses this.

**CVVH masks creatinine for 1B systemic arm (Batch 10):** Patient 7297 has 1B liver labs fully met (peak INR 5.4, 63% improvement, ALT >80%) but needs at least one "additional condition" met for 1B survival: lactate <=2 (has 2.9), HE 0-2 (has HE 4), or creatinine improving (on CVVH so creatinine unreliable). CVVH makes creatinine improvement unassessable, and APAP mitochondrial lactate context (lactate 2.9 is mildly elevated, not shock-level) is not recognized. Fix #11 extension to 1B context + APAP lactate relaxation (<3 for 1B additional condition).

**CVVH masks creatinine for uremic HE -- circular dependency (Batch 13):** Patient 9691 has grade 4 HE + ammonia 48 (<50) + CVVH active (Cr 1.85 artificially lowered from presenting Cr 3.42). Pre-Check A requires Cr >5 which is impossible to meet while on CVVH. Ammonia trajectory 184->48 (dramatic decline) proves liver clearing ammonia effectively yet patient remains in grade 4 coma -- strongly suggests non-hepatic (uremic) coma. Fix #11 would enable uremic HE determination, neutralizing Rule 5B and Extreme Bilirubin death overrides. However, this creates a CIRCULAR DEPENDENCY: uremic HE neutralizes death overrides, but the uremic coma itself (grade 4 HE + ventilation) also blocks 1C lag exception conditions. No positive pathway fires, so weighted vote (1/3 Yes) still predicts death. Needs Combination Signal extension for CVVH-uremic HE cases.

#### L. Persistent Coma with Recovered Liver + Missing Ammonia (~5 patients)

Grade 4 HE persisting while liver markers near-normal. No ammonia reported. System defaults to "non-uremic" and fires Rule 5B, but recovered liver + persistent coma strongly suggests the coma is NOT hepatic.

- Patient 3218 (INR 1.51, bilirubin 2.6, ALT 82.8% down, HE 4 for 7 days)
- Patient 3907 (INR 1.7, ALT 73.2% down, HE 4, ammonia not reported)
- Patient 4429 (HE 4, creatinine 2.95, ammonia not reported)
- Patient 4564 (HE 4, creatinine 2.8, ammonia not reported)
- Patient 4623 (HE 4, creatinine 2.9, ammonia not reported)
- Patient 5781 (INR 2.27, ALT 92.7% down, HE 4 for 6 days, ammonia NEVER reported, creatinine 1.5)
- Patient 5822 (INR 1.9, ALT 91% down, HE 4 for 4 days, ammonia 49 STALE from Day 1, creatinine 5.2)
- Patient 6216 (INR 1.83, ALT 83% down, HE 4 for 7 days, ammonia 90 -- in "no man's land" between uremic threshold <50 and danger threshold >150 despite recovered liver)
- Patient 6257 (INR 1.67, ALT 90% down, HE 4 for 7 days, ammonia NEVER measured, creatinine 2.9)
- Patient 6417 (INR 1.9, ALT 89 WITHIN NORMAL RANGE, HE grade 4 all 7 days, pressors all 7 days, ARDS -- genuinely hard, possible noise floor)
- Patient 6477 (INR 1.2 fully normalized 4+ days, ALT 94% down, HE grade 3, bilirubin rising 9.7->22.6 monotonically)
- Patient 6821 (Peak INR 4.7, lactate 2.3, ammonia NEVER reported, creatinine 5.7, HE grade 3)
- Patient 7265 (INR 2.77, bilirubin 23.2, HE 4, Cr 5.9, ammonia NEVER reported, indeterminate etiology, ALFSG-PI 2.5% -- noise floor)
- Patient 7555 (Peak INR 3.8, bilirubin ~20.5, HE 4, vent, pressors -- noise floor, too similar to constraint Patient 1279)
- Patient 8174 (Peak INR 9.8, 73.5% improved to 2.6, ALT 93% down, HE grade 4, ammonia not reported, Cr 1.1->1.7. 1B liver labs met but additional condition blocked by missing lactate + HE 4 + Cr worsening)
- Patient 7830 (INR 2.0, bilirubin 25 rising, HE 4, lactate 4.2 rising, ammonia not reported -- noise floor)
- Patient 8633 (Peak INR 4.6, current 1.6, ALT >80% down, HE grade 4, ammonia 80, Na 167, pH 7.29. Recovered liver + persistent coma. Too close to constraint 1279 -- noise floor)
- Patient 9691 (Peak INR 4.6, current 3.2, ALT 91.8% down, HE grade 4, ammonia 48 (<50), Cr 1.85 on CVVH. Ammonia trajectory 184->48 proves liver clearing. Uremic HE if CVVH-aware -- Fix #11)

#### M. HE Trajectory Improvement Not Recognized (2 patients)

System only evaluates static HE grade at assessment day, not trajectory of improvement. Patient 3545 improved from HE 4 + ventilated (Days 2-6) to HE 2 + not ventilated (Day 7). Patient 3566 improved HE 4 -> 0. Patient 5824 improved from HE 4 (Days 1-6) to HE 2 (Day 7) -- dramatic neurological recovery the system ignores. Patient 6142 improved from HE 3 to HE 1 between consecutive days (Day 2->3). Patient 6412 improved to INR 1.1 (fully normalized) with lactate 0.8 and ammonia 29 -- all 3 specialists predicted survive but committee overrode. Patient 6743 has HE grade 2 (near-miss for 0-1 waiver) with bilirubin 29.5 (possibly highest in entire dataset).

#### N. All Three Specialist Agents Share Death Bias (systemic)

In the majority of false-negative cases, ALL THREE specialists predicted death. The bias is not just in the Committee Chair -- it's in every specialist prompt. Any fix must address specialist prompts too.

**Specialist arithmetic errors:** In Patient 4682 (FP), the CC specialist claimed ALT declined ">80%" when actual decline was 69.9% (2044->615). Incorrect specialist math can cascade into committee decisions. This suggests specialists may need explicit arithmetic verification or the committee needs to independently verify specialist claims.

Confirmed in Batches 2-10: 3742, 3899, 3907, 4051, 4339, 4429, 4509, 4564, 4623, 4658, 4674, 4677, 4768, and many Batch 2-3 patients had unanimous 3/3 death predictions. Batch 8: 11 of 12 false-negative patients had unanimous 3/3 specialist death votes. Batch 9: systemic death bias confirmed across all 14 false negatives. Batch 10: death bias confirmed in all 10 false negatives. Notable exceptions (specialist override cases): Patient 5824 (Batch 8) had ALL 3 specialists predict SURVIVE but committee overrode on 0.1 mg/dL bilirubin technicality. Patient 6412 (Batch 9) had ALL 3 specialists predict SURVIVE (INR 1.1 fully normalized, lactate 0.8, ammonia 29) but committee overrode because no formal pathway met. Patient 7114 (Batch 10) had 2/3 specialists predict survive but committee overrode. Patient 7333 (Batch 10 FP) is an INVERTED case: committee predicted survive when 2/3 specialists predicted death and no binding survival rule applied. Batch 11: all 6 FN had unanimous 3/3 specialist death votes. The 3 FPs had unanimous 3/3 specialist survive votes -- the framework was correct on the FP predictions (P1/1B met) but patients died from causes not captured (hypernatremia, ischemia recurrence, bilirubin never-peaked). Batch 12: all 8 FN had 3/3 or 2/3 specialist death votes. Notable: Patient 8762 had ALL 3 specialists predict SURVIVE (ALFSG-PI 93.3%, 77.6% INR improvement, HE 0) -- committee should have enforced survival. Patient 9009 (FP): committee overrode 3/3 specialist No votes by incorrectly claiming P1B met. Batch 13: all 7 FN had 3/3 or 2/3 specialist death votes. Notable: Patient 9580 had 2/3 specialists predict SURVIVE (Hep Yes 0.74, TS Yes 0.68) but committee overrode with Extreme Bilirubin. Zero false positives.

#### O. Priority 1/1B Met but Extrahepatic Deterioration (2 false positives)

When Priority 1 or 1B is met but extrahepatic organs are actively failing, the system has no mechanism to override the binding survival prediction.

**Variant A -- CVVH + phosphate + coma (3938):** Priority 1 met (INR 1.0, ALT 91% down, bilirubin 1.0 declining) but creatinine sharply worsening despite CVVH (0.65 to 2.31), phosphate 7.8, persistent grade 4 coma at Day 7, severe anemia (Hgb 6.8).

**Variant B -- Progressive AKI without RRT (4311):** APAP Day 5, INR 4.0->1.5 (62.5%), ALT 86.5% down, bilirubin declining, HE grade 4 but ammonia 36 (low), no vent, no vasopressors -- BUT creatinine progressively worsening 3.3->5.4->6.2->6.5->6.8 over 5 days without RRT. All 3 specialists predicted survive. Patient died. The unchecked progressive renal failure (no CVVH initiated despite creatinine approaching 7) is the death signal the framework missed.

- Patient 3938 (false positive: predicted survive, actually died)
- Patient 4311 (false positive: predicted survive, actually died)
- Patient 5742 (false positive: predicted survive, actually died. Priority 1B legitimately met. Progressive AKI: creatinine 1.3->2.5->3.0->3.3->4.7 over 5 days. CVVH started Days 2-3 then DISCONTINUED Day 4 despite rising creatinine -- suggests clinical futility determination. Fix 14 needs refinement: current threshold Cr >5.0 would miss this patient at 4.7. Consider: "monotonically rising creatinine over 4+ days AND RRT discontinued despite worsening renal function.")

**Batch 11 FP variants (3 patients -- highest FP count in any single batch):**
- Patient 7936 (FP, Day 6, Ischemia/Shock etiology): P1 clearly met (INR 1.2, ALT ~80% down, bilirubin declining). HE 0, no organ support, Cr 0.5. Subtle missed signals: ALT rebound 149->392 on Day 4 (suggests recurrent ischemic insult), lactate re-elevation 1.3->2.1 over Days 4-6. Death likely from underlying circulatory disease, not liver failure. NOISE FLOOR -- no fix warranted.
- Patient 8103 (FP, Day 6, APAP): P1 clearly met (INR 1.4, ALT 90% down, bilirubin declining 12.9->5.3). HE 0, lactate 1.1, no organ support. ALFSG-PI 93.1%. Missed signals: severe progressive hypernatremia (Na 143->163 over 6 days -- not tracked by framework), extreme historical ammonia peak of 445 (Day 2, now 88 -- framework only evaluates current value), oscillating INR (rebounded Day 4). BORDERLINE -- framework lacks sodium tracking.
- Patient 8136 (FP, Day 7, APAP): 1B met (peak INR 6.6, 70% improvement, ALT 91% down, lactate 1.7 <2). No organ support, HE 2. Missed signals: bilirubin MONOTONICALLY RISING all 7 days (4.2->10.0, never peaked), monotonically declining platelets (119->56 all 7 days), INR stalled at 2.0. The "bilirubin never peaked" pattern differs from true excretory lag (which peaks then declines by Day 5-7). BORDERLINE -- partially learnable but defer until more data.

**Batch 12 FP variants (3 patients):**
- Patient 8632 (FP, Day 2, APAP): Day 2 unpredictable death. All indicators favorable at assessment. NOISE FLOOR -- extends Issue P from Day 1 to Day 2. Zero regression risk from any fix.
- Patient 8732 (FP, Day 7, APAP): BORDERLINE. Committee incorrectly claimed P1C was met (it was NOT -- lactate 3.5, HE 3, bilirubin rising). Even corrected, weighted specialist vote produces Yes. Smoldering sepsis phenotype: persistent HE 3 all 7 days, oscillating lactate (1.8->4.1->2.1->3.5), progressive WBC rise (7.6->24.5). New Issue O sub-variant D: formal criteria not met but underlying pattern of unresolved sepsis not captured by framework.
- Patient 9009 (FP, Day 7, APAP): Committee claims P1B met by ignoring mandatory additional condition (see Issue B Variant G). Overrides 3/3 specialist No votes. Fix: clarify P1B prompt to make three-component conjunction unambiguous. CRITICAL Fix #7 scoping: missing lactate must NOT satisfy "lactate <2" arm of P1B additional condition.

**FP implications for proposed fixes:** None of the 24 proposed FN-targeting fixes create regression risk against the Batch 11-12 FP patients. FN fixes widen survival access for patients who DO survive.

#### P. Unpredictable Early Deaths (noise floor)

Some patients die despite having no available signal at Day 1-2. No prompt fix would help without better early data.

- Patient 3892 (Day 1, HE 0, no organ support, ALFSG-PI 86.7%, no lactate reported)
- Patient 8632 (Day 2, APAP, all indicators favorable at assessment -- extends pattern from Day 1 to Day 2)

#### Q. Low Peak ALT Blocks Percentage Recovery Criteria (1 patient)

Priority 1B requires "ALT >80% down from peak." Patient 4509 has peak ALT 197, current ALT 61. Mathematically 197->61 = 69% decline, which fails >80%. However, ALT 61 is within normal range (<100 U/L). The percentage-based criterion penalizes patients whose peak ALT was never dramatically elevated -- an ALT of 61 represents a recovered liver regardless of percentage decline from a modest peak of 197.

Proposed fix: "ALT >80% down from peak OR current ALT <100 U/L" -- absolute normal ALT should satisfy the ALT recovery criterion regardless of percentage decline.

- Patient 4509 (APAP, peak ALT 197, current ALT 61, INR improving, bilirubin rising)
- Patient 6451 (ALT never dramatically elevated -- 100-144 range all 7 days. Genuinely sick: pressors 5 days, WBC 36, HE grade 4 all 7 days. Noise floor / unfixable.)

#### R. Extreme Persistent INR Without Trajectory Data (1 patient, FP)

Patient 4682 (false positive): INR 8.05 at Day 7, but NO prior INR data available to determine trajectory. Current death rules require grade 4 HE for Rule 5B or bilirubin >15 for Extreme Bilirubin. Patient has HE grade 3 (not 4) and bilirubin 12.3 (not >15). No death rule fires despite INR 8.05 being an extreme coagulopathy signal. All 3 specialists predicted survive. Patient died.

Additional finding: the Critical Care specialist made an ALT math error, claiming ALT declined ">80%" when the actual decline was 69.9% (2044->615). This kind of specialist arithmetic error can cascade into the committee's decision.

Proposed fix: new death rule for INR >6.5 at Day 5+ without demonstrated improvement AND without met recovery criteria = death prediction. Must be carefully conditioned to avoid regressing patients with INR >6.5 who are on trajectory to survive.

- Patient 4682 (false positive: predicted survive, actually died. INR 8.05 Day 7, HE 3, no prior INR)

#### S. ALT-Dominant Recovery with INR Lag / Coverage Gap (1 patient)

Patient 5573: APAP Day 7, ALT 94.9% down (3872->199, near-normal), but INR remains at 5.3 (0% improvement from Day 2 peak 4.2; trajectory: 2.5->4.2->3.6->3.4->3.1->4.2->5.3). HE grade 0 (resolved from grade 2), no vent, no pressors, no infection, ammonia 76. Creatinine 5.4, lactate 6.4 (STALE -- identical value Days 2-7, clear data artifact).

This is better explained as a **combination of existing issues** rather than a genuinely new pattern:
- **Issue A**: Bilirubin 13.8 rising blocks Priority 1
- **Issue H**: Lactate 6.4 stale (identical 6 days) is a data artifact, not current
- **Issue Q**: ALT 199 is near-normal but just above <100 threshold
- **Issue F**: Peak INR 5.3 vs 5.0 boundary for Priority 1C eligibility

The key coverage gap: no pathway exists for "ALT normalized + HE resolved + hemodynamically stable = survival" when INR remains elevated. In APAP recovery, ALT falls FIRST (necrosis stops), then INR improves over days/weeks. This patient was caught mid-lag. Proposed fix: Priority 1D pathway for ALT-dominant APAP recovery (ALT >90% down + ALT <250 + HE 0-1 + no organ support) even with persistent INR elevation.

- Patient 5573 (APAP, ALT 94.9% down to 199, INR 5.3 oscillating, HE 0, no organ support, stale lactate 6.4)

#### T. P1 Negation Too Aggressive at PaO2/FiO2 Boundary (1 patient, Batch 11)

Patient 8095 is the **first case in 1,100 patients** where the P1 negation rule fires on its correct criteria (grade 4 HE + PaO2/FiO2 <2.0) and produces a wrong answer. Prior P1-related false negatives (5762, 6572) were enforcement failures where the committee applied negation when criteria were NOT met (grade 3 HE in both). This is a genuine rule design issue.

P1 is FULLY MET: INR 1.4 (<1.5), ALT 11028->857 (>92% down), bilirubin 8.7->8.6 (declining). But the negation fires because: grade 4 HE (non-uremic, ammonia 78, Cr 1.2) + PaO2/FiO2 1.85 (<2.0) + infection with leukocytosis. The PaO2/FiO2 is only 7.5% below the threshold. The liver recovery is unambiguous.

The P1 negation threshold of <2.0 was set to capture moderate-to-severe ARDS. But 1.85 is borderline moderate ARDS, and the liver recovery signal (INR 1.4, ALT >92% down) is exceptionally strong. The rule has no mechanism to weigh liver recovery strength against ARDS severity. Proposed Fix #24: tighten to <1.5 (severe ARDS only).

- Patient 8095 (APAP Day 7, INR 1.4, ALT >92% down, bilirubin declining, grade 4 HE, PaO2/FiO2 1.85, infection)

---

### Cross-Reference: Issue by Batch

| Issue | Batch 2 | Batch 3 | Batch 4 | Batch 5 | Batch 6 | Batch 7 | Batch 8 | Batch 9 | Batch 10 | Batch 11 | Batch 12 | Batch 13 |
|-------|---------|---------|---------|---------|---------|---------|---------|---------|----------|----------|----------|----------|
| A. Rising bilirubin | ~10 | ~5 | 3089 | 3678, 3742, 3899, 3907, 4051 | 4323, 4339, 4429, 4509, 4513, 4564, 4623, 4658, 4662, 4674, 4677, 4768 | 4823, 5109, 5151, 5251, 5364, 5573 | 5762, 5781, 5822, 5824, 5882, 5973, 6166, 6216, 6257, 6323, 6325 | 6412, 6415, 6417, 6446, 6451, 6466, 6477, 6531, 6572, 6737, 6743, 6821, 6847 | 7142, 7155, 7265, 7297, 7442, 7515, 7555, 7688 | 7830, 8174, 8216, 8237 | 8447, 8465, 8557, 8725, 8968 | 9040, 9120, 9452, 9546, 9580, 9691, 9717 |
| B. Priority hierarchy | -- | 2588, 2678, 2723 | -- | 3760, 3678, 4042 | 4513, 4677, 4768 | 4823, 5151 | **5762, 5882, 6166, 6257** (P1/1B met) | **6446, 6466, 6572** (P1/1B/1C met); 6412 (3/3 survive override) | **7333** (FP: inverted -- survive without binding rule) | -- | **8465** (waiver Variant B), **8557** (P1B met), **8968** (P1 decline dismissed); **9009** (FP: Variant G -- P1B additional condition ignored) | **9040** (P1B acknowledged met then overridden -- 11th enforcement failure) |
| C. Rule 5B too aggressive | -- | 2678, 2723 | 3089, 3218 | 4029 (partial) | 4429, 4564, 4623 | 5109 | 5781, 5822 | 6417, 6466, 6477, 6531, 6821 | 7265, 7297, 7555 | 7777, 7830 | 8633 | 9691 |
| D. 1C too restrictive | ~5 | 2584, 2741 | -- | 3742, 3743, 3875 | 4662 | 5109 | 5781, 5824, 5973, 6323 | 6412, 6415, 6417, 6446, 6466, 6477, 6743, 6821, 6847 | 7155, 7442, 7515, 7555 | 8237 | 8447 | 9120, 9546, 9691 |
| E. Coverage gaps | 2228 | 2805 | -- | -- | 4623, 4674 | 5109 | 6325 (missing lactate) | 6582 (non-APAP Pre-Check C) | 7546 (Day 1 override too narrow) | 7777 (peak INR <2.0) | -- | -- |
| F. Threshold near-miss | -- | 2738 | 3343, 3534, 3566, 3576 | 3899, 3907, 4029 | 4323, 4429, 4674 | 4823, 5251 | 5824, 5882, 6166, 6216, 6323, 6325 | 6415, 6446, 6466, 6531, 6737, 6743, 6821 | 7114 (micro-rise), 7155, 7297 (lactate 2.9), 7442 (ATN Cr), 7688 (stale 2.3) | 8095 (P/F 1.85), 8174 (ATN Cr), 8237 (INR =1.5 + ATN Cr) | 8633 (peak INR 4.6 + INR 1.6), 8762 (lactate 3.0 boundary) | 9580 (INR 56.6% vs >60%), 9691 (bilirubin 15.43 boundary) |
| G. Pre-Check B/C sensitive | -- | -- | 3610 | 3778 | -- | 5145, 5385 | 6142 | 6582 (non-APAP) | 7114 (Day 2 exception inaccessible) | -- | 8762 (Pre-Check B on bilirubin 4.5 -- low magnitude) | -- |
| H. Stale/missing data | -- | -- | 3243 | 3875, 4051 | -- | 4823, 5364, 5573 | 5762, 5822, 5973, 6216, 6323, 6325 | 6415, 6446, 6531, 6737, 6821 | 7142 (missing lactate), 7688 (stale 2.3), 7265 (missing ammonia) | 8216 (missing lactate), 8174 (missing lactate for 1B) | 8725 (missing lactate), 8447 (stale 3.4), 8968 (stale 7.7) | 9452 (stale 2.3 from Day 2), 9717 (stale 7.8 from Day 2), 9120 (missing lactate) |
| I. APAP lactate context | -- | -- | 3029 | 3778 (partial) | -- | -- | 6166 (partial) | -- | -- | -- | -- | -- |
| J. Bilirubin <3 alt | -- | -- | 3029 | -- | -- | -- | -- | -- | -- | -- | -- | -- |
| K. CVVH masks creatinine | -- | -- | 3133 | -- | 4677 | -- | 5973 | -- | 7297 (1B systemic arm) | -- | -- | 9691 (CVVH Cr 1.85 masked from 3.42) |
| L. Coma + recovered liver | -- | -- | 3218 | 3907 | 4429, 4564, 4623 | -- | 5781, 5822, 6216, 6257 | 6417, 6477, 6821 | 7265, 7555 | 8174, 7830 | 8633 | 9691 |
| M. HE trajectory | -- | -- | 3545, 3566 | -- | -- | -- | 5824, 6142 | 6412, 6743 | -- | -- | -- | -- |
| N. Specialist death bias | many | many | many | 3742, 3899, 3907, 4051 | 4339, 4429, 4509, 4564, 4623, 4658, 4674, 4677, 4768 | all 8 (3/3) | 11/12 FN (3/3); 5824 opposite (3/3 survive overridden) | all 14 FN (systemic); 6412 (3/3 survive overridden) | all 10 FN; 7333 FP (inverted: 2/3 death overridden to survive) | all 6 FN (3/3); 3 FP also 3/3 survive | all 8 FN; 8762 (3/3 survive not enforced); 9009 FP (3/3 No overridden) | all 7 FN; 9580 (2/3 Yes overridden) |
| O. P1 met + extrahepatic | -- | -- | -- | 3938 (FP) | 4311 (FP) | -- | 5742 (FP) | -- (0 FP in Batch 9) | -- | 7936, 8103, 8136 (3 FP: subtle extrahepatic) | 8632 (FP: Day 2 death), 8732 (FP: smoldering sepsis), 9009 (FP: P1B incorrectly applied) | -- (0 FP) |
| P. Unpredictable early death | -- | -- | -- | 3892 (FP) | -- | -- | -- | -- | -- | -- | 8632 (Day 2) | -- |
| Q. Low peak ALT | -- | -- | -- | -- | 4509 | -- | -- | 6451 (ALT never elevated) | -- | -- | -- | -- |
| R. Extreme INR no trajectory | -- | -- | -- | -- | 4682 (FP) | -- | -- | -- | -- | -- | -- | -- |
| S. ALT recovered but INR stuck | -- | -- | -- | -- | -- | 5573 | -- | -- | -- | -- | -- | -- |
| **T. P1 negation too aggressive** | -- | -- | -- | -- | -- | -- | -- | -- | -- | **8095** (P/F 1.85 negates met P1) | -- | -- |

---

### CRITICAL: Regression Risk from CHANGELOG History

Any fix MUST NOT regress Batch 1. The CHANGELOG documents why each rule exists:

**Rule 5B was strengthened because:**
- v0.9.2-dev: Patient 1279 (DIED) was incorrectly predicted to survive because committee bypassed Rule 5B via "free-form clinical reasoning about dominant physiologic recovery"
- v0.9.4-dev: Added MANDATORY SEQUENCE enforcement -- if P1/1B/1C all fail, MUST check Rule 5B before any prediction
- v0.9.4-dev: Banned citing "improving trajectory," "favorable labs," "ALFSG-PI prognosis" to bypass Rule 5B
- RISK: Weakening Rule 5B would let Patient 1279 regress (grade 4 HE + ammonia 73.5 + infection, died)

**Extreme Bilirubin was strengthened because:**
- v0.9.3-dev: Patient 1101 (DIED) had committee treat 54%/74% as "near recovery" -- added "NEAR-MISS DOES NOT COUNT"
- v0.9.3-dev: Strengthened Rule 6 to say "even if all 3 specialists predict Yes and INR is clearly improving, if formal thresholds are not reached and bilirubin >15 with discordance, Extreme Bilirubin DEATH override takes precedence"
- RISK: Weakening Extreme Bilirubin would let 1101/1536 regress

**Anti-rationalization was added because:**
- v0.9.4-dev: Patient 1279 committee invented "dominant physiologic recovery" to skip Rule 5B
- v0.9.3-dev: Patient 1624 committee invented "severe uncontrolled extrahepatic organ failure" to reject combination signal
- v0.9.4-dev: Patient 1446 committee invented "current-value rule" to reject stale lactate
- RISK: Removing anti-rationalization language opens the door to new invented bypass terms

### Key Constraint: All Fixes Must Be Regression-Safe

The Batch 1 patients that forced the current strict rules were:
- **1279** (died): Grade 4 HE + ammonia 73.5 + infection -- committee bypassed Rule 5B
- **1101** (died): INR 54% improved (not >60%) + ALT 74% down (not >80%) + bilirubin 18 rising -- committee treated near-miss as recovery
- **1536** (died): Bilirubin >15 rising in APAP -- Extreme Bilirubin override was needed
- **1624** (died): Committee invented "severe uncontrolled extrahepatic organ failure" to reject combination signal
- **1446** (survived): Committee invented "current-value rule" to reject stale lactate

Every proposed fix must be checked against these 5 constraint patients to confirm no regression.

---

### Recommended Fixes (ADDITIVE, Not Subtractive)

Fixes must be NEW EXCEPTIONS with precise conditions, NOT weakening of existing rules. Each fix specifies the exact conditions that distinguish it from the Batch 1 cases that the current rules protect.

1. **Enforce Priority 1/1B supremacy over Priority 2 rules** (fixes Issue B)
   - Add explicit language: "If Priority 1 OR Priority 1B criteria ARE met, Rule 5B and Rule 6 DO NOT APPLY. Check P1/1B FIRST."
   - Also: missing data for a waiver condition does NOT allow overriding a met Priority 1 or 1B
   - Add worked example: "P1 met with vent + pressors + AKI + grade 3 HE: all non-negating per prompt rules. MUST predict survival."
   - Safe because: Batch 1 failures (1279, 1101) did NOT meet P1 or 1B criteria. 1279 had grade 4 HE + ammonia 73.5 + infection (1B negated). 1101 had only 54% INR improvement (1B requires >60%).
   - Also: at Day 1 when no binding survival override fires, enforce weighted specialist vote (2/3 death = death). Prevents committee from inventing survival predictions without framework justification.
   - Fixes: 2588, 2678, 2723, 3760, 3678, 4042, 4823, 5762 (P1 met), 5882 (1B met), 6166 (1B met), 6257 (1B met), 6446 (1B acknowledged met), 6466 (1C met), 6572 (P1 met), 7333 (FP: committee invented survive at Day 1 without binding rule), 8557 (P1B fully met but committee overrides with Extreme Bilirubin), 8968 (P1 bilirubin decline dismissed as "not clearly declining"), 9040 (P1B FULLY MET -- peak INR 6.1, 72.1% improvement, ALT 83.4% down, lactate 1.4 -- committee explicitly stated "Priority 1B IS met" then predicted death. 11th enforcement failure, ZERO regression risk)

2. **Widen 1C bilirubin lag exception for ventilated APAP patients** (fixes Issue D)
   - Add condition: "OR [HE grade 2-4 AND mechanical ventilation AND PaO2/FiO2 >= 2.0 AND no vasopressors AND no documented infection AND APAP etiology]"
   - Also expand HE 0-1 to HE 0-2 when HE trajectory is improving (e.g., grade 4 -> grade 2) -- Patients 4662, 6743
   - Also expand Extreme Bilirubin waiver HE from 0-1 to 0-2 when trajectory improving (Patient 6743: bilirubin 29.5, HE grade 2, ALT 79%, INR 1.6 -- triple near-miss). MUST verify against Patient 1536 before implementing.
   - Safe because: strictly additive. No Batch 1 patient who died had this exact profile.
   - Fixes: ~16 patients with airway-protection ventilation, HE grade 2 near-miss, or Extreme Bilirubin waiver HE near-miss; 8237 (INR exactly 1.5, HE 2, vent, needs 1C lag + ATN Cr combined)

3. **Add "near-recovery exception" to Rule 5B** (fixes Issue C)
   - When INR <=1.5 AND ALT >80% down AND APAP AND no infection AND no rising lactate, Rule 5B does not mandate death even with grade 4 HE
   - Safe because: Patient 1279 (Batch 1 death) had infection AND ammonia concerns -- would NOT qualify
   - Fixes: patients with grade 4 HE + unambiguous liver recovery + no infection

4. **Create Priority 1D for peak INR <2.0 patients** (fixes Issue E, peak INR gap)
   - New pathway: peak INR <2.0 + current INR normalized to <=1.5 + ALT >80% down + APAP = survival (even with rising bilirubin)
   - Safe because: entirely new pathway covering a gap, no existing rule modified
   - Fixes: 2228

5. **Fix threshold boundary issues** (fixes Issue F)
   - Change Priority 1 INR <1.5 to INR <=1.5
   - Change Priority 1B peak INR >5.0 to peak INR >=5.0 (Patient 6446 has peak exactly 5.0; committee explicitly acknowledged "1B IS met" -- ZERO regression risk)
   - Define "creatinine improving" as "most recent creatinine value is lower than the immediately preceding value, OR creatinine at normal baseline (<1.2 mg/dL)"
   - Add bilirubin micro-rise tolerance: bilirubin change of <=0.5 mg/dL treated as "stable/declining" (not "rising")
   - Resolve ATN creatinine inconsistency between 1B and 1C (worsening creatinine = ATN in both contexts for APAP)
   - Consider ALT >=75% (from >80%) for 1B when INR is fully normalized (<=1.2) -- narrowly conditioned
   - Safe because: boundary changes are clinically meaningless; no Batch 1 death had INR exactly 1.50 or peak INR exactly 5.0
   - Consider ALT >=75% extension note: Patient 9580 has INR improvement 56.6% (3.4% below >60%) but ALT 93.5% down. Possible P1B extension: INR >=55% when ALT >90%. Patient 1101 (Batch 1 constraint) at ALT 74% would NOT qualify -- low regression risk.
   - Fixes: 2738, 2678, 2723, 3566, 3576, 4029, 4823, 5251, 5824 (micro-rise), 5882 (Cr definition), 6166 (INR =1.5), 6216 (normal Cr baseline), 6323 (micro-rise), 6325 (ATN Cr inconsistency), 6446 (peak INR =5.0), 6466 (INR =1.5), 6531 (INR =1.5 + micro-rise), 6737 (double near-miss), 6743 (triple near-miss), 7114 (micro-rise Pre-Check B), 7442 (ATN Cr in 1C lag exception), 8095 (PaO2/FiO2 1.85 boundary -- see also Fix #24), 8174 (ATN Cr 1.1->1.7 blocks 1B additional condition), 8237 (INR exactly 1.5 + ATN Cr 2.5->3.1 compound block), 9580 (INR improvement 56.6% vs >60% -- 3.4% short, ALT 93.5% down, 2/3 specialists Yes but committee overrode with Extreme Bilirubin)

6. **Add Pre-Check B magnitude and data requirements** (fixes Issue G)
   - Require bilirubin rise >2 mg/dL AND bilirubin >5 mg/dL for binding death (ignore trivial sub-3 rises)
   - Require at least 2 data points to assess "not declining" -- cannot fire on a single stale measurement
   - Safe because: narrowly additive exceptions, no existing death protection weakened
   - Fixes: 3610, 3778, 8762 (Pre-Check B fires on bilirubin 1.6->4.5 -- trivial magnitude. Clearest Pre-Check B FP in 1,200 patients. Bilirubin >5 threshold would prevent trigger entirely.)

7. **Handle stale/missing lactate** (fixes Issue H)
   - Stale lactate >72h old should not be used to DENY the Extreme Bilirubin waiver unless corroborated by current hemodynamic instability (vasopressors, acidosis)
   - Also: if lactate identical across 3+ consecutive days, treat as stale data artifact (see Fix #20)
   - Also: if lactate was NEVER measured across all days AND no hemodynamic instability (no pressors, no acidosis, pH >=7.35), missing lactate should not block recovery pathways or waivers
   - Safe because: Patient 1446 constraint is about stale LOW lactate being honored, not stale high lactate being rejected
   - **CRITICAL SCOPING NOTE (driven by Patient 9009 FP):** Fix #7 (missing/stale lactate) must NOT allow missing lactate to SATISFY positive criteria. Missing lactate should only REMOVE BLOCKERS for waivers and exceptions. Specifically: missing lactate does NOT count as "lactate <2" for P1B's mandatory additional condition. If lactate is missing AND HE grade 4 AND creatinine worsening, P1B additional condition is NOT met. This prevents false positive regression like Patient 9009 where committee incorrectly treated absent lactate as satisfying "lactate <2."
   - Fixes: 3243, 3875, 4051, 5364, 5573, 5762 (stale 26.0), 5822 (stale 21.9), 5973 (stale 6.2), 6216 (stale 5.5 identical 7 days), 6323 (stale 2.9), 6325 (never measured), 6446 (stale 22.6 identical 7 days), 6737 (stale high lactate blocks waiver), 6821 (ammonia never measured + Cr >5), 7142 (lactate never measured), 7688 (stale lactate 2.3 from Day 1, 6 days stale), 8216 (lactate never measured -- sole blocker, INR 4.6->1.6, ALT >80% down, HE 1), 8174 (missing lactate blocks 1B additional condition despite 73.5% INR improvement + 93% ALT decline), 8725 (missing lactate -- sole blocker, no organ support, HE 1, ALT 71 near-normal), 8447 (stale 3.4 from Day 3, 4 days stale, extreme bilirubin 30.2), 8968 (stale 7.7 from Day 1, 6 days stale, biases specialists), 9452 (stale 2.3 from Day 2, 5 days stale -- INR 1.06, one of BEST recoveries in entire 1,260-patient evaluation, ALT 91% down, HE 0, ALFSG-PI 85.7%, no organ support. Sole blocker. Near-zero regression risk), 9717 (stale 7.8 from Day 2, 5 days stale -- HE 0, no vent, no pressors, no infection, Cr 0.75 excellent. Sole blocker. CC specialist correctly identified stale lactate but system forced death), 9120 (lactate never measured -- partial, compound with HE 3 + vent + bilirubin 29.7 rising)

8. **Add Day 4 rapid recovery pathway** (fixes Issue E, Day 4 gap)
   - INR normalized to <=1.5 from initially elevated (>2.0) within 4 days in APAP = survival signal
   - UNSAFE AS WRITTEN: Patient 1148 (DIED, Batch 1) has INR 2.2->1.0 by Day 4 in APAP but died with persistent grade 4 HE, ventilation all 4 days, vasopressors Days 2-3, ammonia 128
   - Would need: HE grade 0-2 AND no vasopressor history AND no ventilation -- likely too narrow to be useful
   - RECOMMENDATION: Do not implement without very restrictive conditions or skip entirely

9. **Lower Day 1 ALFSG-PI threshold from 85% to 80%** (fixes Issue E, ALFSG-PI)
   - Only for APAP + no organ support (no vent, no pressors, no CVVH)
   - Safe because: narrowly conditioned on no organ support
   - Fixes: 2805

10. **Strengthen 1B enforcement in specialist prompts** (fixes Issue N)
    - Add "If Priority 1B is met, you MUST predict survival" to Hepatologist, CC, and TS prompts
    - Safe because: 1B criteria are unchanged, just making enforcement explicit in all agents

11. **Add CVVH-aware creatinine rule** (fixes Issue K)
    - "If CVVH active, creatinine cannot be used to EXCLUDE uremic HE"
    - Also extend to 1B context: if CVVH active, creatinine improving/stable cannot be assessed -- treat as "not assessable" rather than "not met" for 1B additional conditions
    - Also: for APAP patients on CVVH where 1B liver labs are met (peak INR >5, >60% improvement, ALT >80%), consider lactate <3.0 (not just <=2.0) as satisfying the additional condition, since APAP mitochondrial lactate can mildly elevate lactate independently of shock
    - Fixes: 3133, 7297 (1B liver labs fully met, CVVH masks Cr, lactate 2.9 in APAP context), 9691 (grade 4 HE + ammonia 48 <50 + CVVH active, Cr 1.85 masked from 3.42. Fix #11 neutralizes death overrides via uremic HE BUT creates CIRCULAR DEPENDENCY: uremic HE blocks lag exception conditions -- HE grade 4 + vent still present -- so no positive pathway fires. Needs Combination Signal extension or additional positive pathway for uremic HE patients with recovered liver)

12. **Add "recovered liver + persistent coma + missing ammonia" pathway** (fixes Issue L)
    - When liver markers near-normal (INR <=1.5, ALT >80% down) + persistent HE 4 + ammonia not reported, default to "possibly non-hepatic coma" rather than "non-uremic therefore Rule 5B"
    - Also: when ammonia NEVER reported AND creatinine >5.0, presume uremic HE (Patient 6821: ammonia never measured, Cr 5.7 -- uremic HE should be presumed)
    - Fixes: 3218, 3907, 6821, 8174 (1B liver labs met -- peak INR 9.8, 73.5% improvement, 93% ALT decline -- but HE 4 + missing ammonia + Cr 1.1->1.7 ATN blocks additional condition)

13. **Add HE trajectory as a recovery signal** (fixes Issue M)
    - HE improving from grade 4 to grade 0-2 between prior days and assessment day = recovery signal
    - Fixes: 3545, 3566

14. **Add Priority 1/1B negation for extrahepatic deterioration** (fixes Issue O)
    - When Priority 1 or 1B is met but extrahepatic organs are progressively failing, add a negation condition
    - Variant A (3938): creatinine worsening despite CVVH + phosphate extremely elevated + persistent deep coma
    - Variant B (4311): creatinine progressively worsening over 5 days (3.3->6.8) WITHOUT RRT initiation despite meeting criteria -- suggests care limitation or futility determination
    - Variant C (5742): CVVH started then DISCONTINUED despite rising creatinine (1.3->4.7 over 5 days). Creatinine 4.7 is below the >5.0 threshold in Variant B. Proposed refinement: "monotonically rising creatinine over 4+ days AND RRT discontinued or never initiated despite creatinine >3.5" as a futility signal.
    - CAUTION: Must be very narrowly defined to avoid regressing correct survive predictions
    - Possible signal: progressive creatinine rise without RRT AND (grade 4 HE OR RRT discontinued despite worsening) = death override even if liver criteria met
    - Fixes: 3938, 4311, 5742

15. **Add absolute ALT normal alternative to percentage decline** (fixes Issue Q)
    - Change ALT criterion from "ALT >80% down from peak" to "ALT >80% down from peak OR current ALT <100 U/L"
    - Rationale: ALT <100 is within normal range and indicates recovered hepatocellular function regardless of percentage decline from a modest peak
    - Safe because: all Batch 1 constraint patients had high current ALT values -- none had ALT <100 at assessment
    - Fixes: 4509

16. **Add extreme INR death rule without trajectory data** (fixes Issue R)
    - New death rule: INR >6.5 at Day 5+ WITHOUT demonstrated improvement (no prior INR data or prior INR also extreme) AND no met recovery criteria = death prediction
    - Must be conditioned on: no met Priority 1/1B/1C criteria AND HE grade >=2 AND bilirubin >5
    - Safe because: patients with met recovery criteria are excluded; patients with improving INR trajectory are excluded
    - CAUTION: also add specialist arithmetic verification -- CC specialist in Patient 4682 claimed ALT ">80%" when actual was 69.9%
    - Fixes: 4682

17. **Add CVVH discontinuation creatinine rebound rule** (fixes Issue K variant)
    - Creatinine rise within 48h of CVVH discontinuation should be flagged as predictable CVVH rebound, NOT new organ deterioration
    - System should not use post-CVVH creatinine rebound to block recovery pathways
    - Safe because: strictly additive exception for a specific clinical scenario
    - Fixes: 4677

18. **Add non-APAP bilirubin lag exception** (fixes Issue E, non-APAP gap)
    - Non-APAP bilirubin lag exception when: INR <=1.5 AND lactate <=2.0 AND ALT declining AND no vasopressors AND no infection
    - Rationale: bilirubin lag can occur in any etiology during liver recovery, not just APAP
    - Safe because: very narrowly conditioned on excellent synthetic function (INR <=1.5) and hemodynamic stability (lactate <=2.0)
    - CAUTION: Patient 1101 (Batch 1 death) had INR 54% improved (not <=1.5) and bilirubin 18 -- would NOT qualify
    - Fixes: 4623 (partial -- also has Issue L), 5109 (DILI)

19. **Strengthen Extreme Bilirubin waiver as BINARY** (fixes Issue B Variant B, Batch 7)
    - Add explicit language: "The 5-condition waiver has BINARY conditions. If ALL FIVE are satisfied (HE 0-1, lactate <=2.0, no vent, no pressors, no infection), the waiver APPLIES regardless of the absolute magnitude of bilirubin or the steepness of its rise. Do NOT distinguish bilirubin 16 vs 27 vs 40 mg/dL. Do NOT invent hidden conditions like 'bilirubin must be within typical lag range.'"
    - Safe because: Patient 1536 (Batch 1 death) had bilirubin >15 rising -- need to verify 1536 did NOT meet all 5 waiver conditions. If 1536 had pressors/infection/HE grade 2-4, waiver would not have applied.
    - Fixes: 5151 (bilirubin 27.1, all 5 waiver conditions met but committee rejected waiver), 3678 (1st confirmed Variant B), 8465 (3rd confirmed Variant B: HE 0, lactate 1.4, no vent, no pressors, no infection -- ALL 5 met but committee invented "bilirubin must show peak/decline." Strongest evidence Fix #19 is critical.)

20. **Add stale lactate detection via identical values** (strengthens Fix #7, Issue H)
    - If lactate value is identical across 3+ consecutive days, flag as stale data artifact
    - Stale high lactate does NOT block pathways unless corroborated by: vasopressors active OR pH <7.30 OR HCO3 <18
    - Safe because: strictly additive data quality rule
    - Fixes: 5364 (lactate 7.0 x7 days), 5573 (lactate 6.4 x6 days)

21. **Add Pre-Check C exception for hyperacute APAP recovery** (fixes Issue G, Batch 7-8)
    - **Variant A (lab-based):** Pre-Check C does NOT apply when ALL of: APAP + INR >75% improved + ALT >90% down + bilirubin declining + no pressors + PaO2/FiO2 >=1.9
    - **Variant B (HE-trajectory-based):** Pre-Check C does NOT apply when ALL of: APAP + HE improved from grade 3-4 to grade 0-1 between consecutive days + no pressors + no infection + ammonia <=150 + pH >=7.35. Rationale: rapid HE improvement proves ventilation is for transient airway protection, not progressive respiratory failure.
    - Safe because: Patient 1148 (Batch 1 death) was on vasopressors Days 2-3 AND HE remained grade 4 all days -- neither variant applies. Patient 1446 (Day 3 constraint) was not ventilated.
    - Note: Patient 5145 (Day 3, ammonia 363, lactate 8.7) would NOT qualify for either variant (HE grade 3->3, no improvement; only 25% INR improvement)
    - Fixes Variant A: 5385 (INR 82% improved, ALT 91.5% down, bilirubin declining)
    - Fixes Variant B: 6142 (HE improving 3->1, no pressors, ammonia 58, pH 7.44)

22. **Add Priority 1D for ALT-dominant APAP recovery** (fixes Issue S coverage gap)
    - New pathway: ALT >90% down + current ALT <250 + HE 0-1 + no organ support + APAP + ammonia <100 (if reported) = survival
    - Even with: INR not improved, bilirubin rising, creatinine elevated (if no RRT suggests expectant management)
    - Safe because: Patient 1101 (Batch 1 death) had ALT only 74% down -- would NOT qualify
    - Fixes: 5573 (ALT 94.9% down, 199 U/L, HE 0, no organ support)

23. **Add Pre-Check C exception for non-APAP with preserved liver function** (fixes Issue G non-APAP variant, Batch 9)
    - Pre-Check C does NOT apply when ALL of: non-APAP etiology + INR <=1.5 + bilirubin <=3.0 + ALFSG-PI >=80% + no vasopressors + no documented infection + HE improving (e.g., grade 3->2 or better)
    - Rationale: Pre-Check C was designed for severely ill ventilated patients. Non-APAP patients with near-normal liver function (INR <=1.5, bilirubin <=3) who are ventilated for transient airway protection should not be forced to death prediction.
    - Safe because: no Batch 1 constraint patient had non-APAP + INR <=1.5 + bilirubin <=3 at Days 1-3. Very narrowly conditioned.
    - Fixes: 6582 (indeterminate etiology, Day 3, INR 1.3, bilirubin 1.5, ALFSG-PI 88.4%, HE improving 3->2)

24. **Tighten P1 negation PaO2/FiO2 threshold** (fixes Issue T)
    - Change P1 negation from "non-uremic grade 4 HE + PaO2/FiO2 <2.0" to "non-uremic grade 4 HE + PaO2/FiO2 <1.5"
    - Alternative: add liver recovery strength override -- if P1 is met with INR <1.5 AND ALT >90% down AND bilirubin declining, P1 negation does NOT apply regardless of PaO2/FiO2
    - Rationale: Patient 8095 is the first case where P1 negation correctly fires on its criteria (grade 4 HE + PaO2/FiO2 1.85) but produces a wrong answer. P1 was FULLY MET (INR 1.4, ALT >92% down, bilirubin declining). The PaO2/FiO2 2.0 threshold is too aggressive -- captures borderline respiratory cases that are not truly failing.
    - Safe because: ZERO regression risk. Patient 1279 (constraint) had ammonia 73.5 + infection -- P1 was NOT met for 1279. P1 negation never applied to any Batch 1 constraint patient because none met P1 in the first place.
    - Fixes: 8095 (PaO2/FiO2 1.85, P1 fully met, grade 4 HE, first correct-but-wrong P1 negation case)

---

### Key Insight: Tuning Set vs Generalization

**EVALUATION COMPLETE: 1,260 patients across 13 batches. API errors rerun -- 0 remaining.** Batch 1 (99%) was the tuning/development set. Batches 2-13 (unseen): 1018/1160 (87.8%). Final: 1117/1260 (88.7%). Batch 7 (92%) was the best unseen batch; Batch 11 (91%) third-best overall; Batch 13 (88.3%, 60 patients) consistent with the 84-92% unseen range. Error counts: 16, 13, 13, 13, 14, 8, 13, 14, 11, 9, 11, 7 in Batches 2-13. The false-negative dominance is consistent across all 13 batches: 124/143 total errors (86.7%) are false negatives. Batch 13 had 0 false positives (7th batch with 0 FP).

**Enforcement failures are the single most actionable issue (Fix #1).** Across all unseen batches, 11+ patients had recovery criteria DEMONSTRABLY MET but committee failed to enforce. Batch 13 added Patient 9040: P1B FULLY MET (peak INR 6.1, 72.1% improvement, ALT 83.4% down, lactate 1.4) and committee explicitly stated "Priority 1B IS met" then predicted death -- the 11th enforcement failure and one of the most clear-cut in the entire dataset. Also: 5762 (P1 met), 5882/6166/6257 (P1B met), 6572 (P1 met), 6466 (P1C met), 6446 (1B acknowledged met then overridden), 8557 (P1B met), 8968 (P1 decline dismissed). Additionally, 2 patients (5824, 6412) had all 3 specialists correctly predict survive but committee overrode them. Batch 10 added an INVERTED enforcement failure: Patient 7333 (FP).

**Stale/missing data (Fix #7) is the highest-impact single fix.** Now affects 24+ patients across all batches. Batch 13 added 3 more: 9452 (stale 2.3 from Day 2, 5 days stale -- INR 1.06, one of BEST recoveries in entire evaluation, sole blocker), 9717 (stale 7.8 from Day 2, 5 days stale -- HE 0, no organ support, sole blocker), 9120 (missing lactate -- partial, compound). CRITICAL: Fix #7 scoping must distinguish between REMOVING BLOCKERS (stale/missing lactate should not block waivers) and SATISFYING POSITIVE CRITERIA (missing lactate does NOT count as "lactate <2" for P1B additional condition). Patient 9009 (Batch 12 FP) demonstrates regression risk if scoping is wrong.

**Threshold near-misses (Fix #5) continue accumulating.** Batch 13 added: 9580 (INR improvement 56.6% vs >60% -- 3.4% short, ALT 93.5% exceptionally strong, 2/3 specialists Yes overridden). Possible P1B extension: INR >=55% when ALT >90% (Patient 1101 at ALT 74% would NOT qualify -- low regression risk). Fix #5 boundary changes have zero regression risk.

**Extreme Bilirubin waiver rejection (Fix #19) confirmed critical.** Patient 8465 is the 3rd confirmed Issue B Variant B (after 3678, 5151): ALL 5 waiver conditions MET (HE 0, lactate 1.4, no vent, no pressors, no infection) but committee rejected with invented 6th condition ("bilirubin must show peak/decline"). Three independent patients across three batches prove the LLM systematically invents non-framework conditions for the BINARY waiver.

**Pre-Check B magnitude (Fix #6) has clearest case yet.** Patient 8762: ALFSG-PI 93.3%, all 3 specialists Yes, 77.6% INR improvement, HE 0, no organ support. Pre-Check B fires on bilirubin 1.6->4.5 (trivial magnitude, both values low). Fix #6 (require bilirubin >5 for trigger) directly fixes. Near-zero regression risk.

**Fix #7 scoping critical for FP prevention.** Patient 9009 (Batch 12 FP) demonstrates that missing lactate must NOT satisfy positive criteria. Committee claimed P1B met by treating absent lactate as satisfying "lactate <2" arm of the mandatory additional condition. Fix #7 must be scoped: missing/stale lactate REMOVES BLOCKERS (does not deny waivers/exceptions) but does NOT SATISFY POSITIVE CRITERIA (does not count as meeting lactate <2 for P1B).

**P1 negation too aggressive (Fix #24).** Patient 8095 is the FIRST case where P1 negation correctly fires on its criteria (grade 4 HE + PaO2/FiO2 1.85 <2.0) but produces a wrong answer. P1 was FULLY MET (INR 1.4, ALT >92% down, bilirubin declining). Tightening threshold from <2.0 to <1.5 has zero regression risk.

**CVVH masking (Fix #11) needs 1B extension + circular dependency resolution.** Patient 7297 has 1B liver labs fully met but CVVH makes creatinine unassessable and APAP lactate 2.9 is treated as failing the <=2.0 threshold. Batch 13 added Patient 9691: CVVH active (Cr 1.85 masked from 3.42, ammonia 48 <50) -- Fix #11 would neutralize death overrides via uremic HE but creates CIRCULAR DEPENDENCY: uremic HE classification blocks lag exception conditions (HE grade 4 + vent still present), so no positive pathway fires. Needs Combination Signal extension or additional pathway for uremic HE patients with recovered liver.

**Noise floor patients:** Batch 12 FN: 8882 (lactate 11 rising + vasopressors + grade 4 HE + ALFSG-PI 45%), 8633 (compound near-miss too close to constraint 1279). Batch 12 FP: 8632 (Day 2 death), 8732 (smoldering sepsis). Batch 13 FN: 9546 (ALFSG-PI 34.5%, vent + pressors + CVVH + infection, platelets 7 -- genuine multi-organ failure), 9120 (moderate -- compound multiple blockers). None of the 24 proposed FN-targeting fixes create regression risk against the FP patients across Batches 11-13.

---

## Operational Lessons

### Always Check for Running Processes Before Launching Batches

- Previous session's background task survived session change
- Launching a duplicate wasted ~15 API calls before being caught
- Rule: always run `ps aux | grep multi_agent_system` before any batch launch
- Track active run info (task ID, PID) in docs/todo.md

### Background Task Monitoring

- Background tasks can run for 65-75 minutes per 100-patient batch
- TaskOutput has a ~10 minute timeout -- need repeated checks
- Track progress by counting `grep -c "Final Prediction:" <output_file>`
- Output Excel files follow pattern: `agent_predictions_gpt-5.2_YYYYMMDD_HHMMSS.xlsx`
