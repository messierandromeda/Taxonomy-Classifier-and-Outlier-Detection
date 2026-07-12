# Evaluating an LLM land-cover classifier for herbarium records

This documents how the classifier was tested, why each test was built the way it was, and what we concluded. It is written for someone who did not run the experiments and who needs to know how much weight the numbers can carry.

The short version: the classifier is stable, cheap and well-behaved, but we still cannot tell how right it is. The reason for that is the most important finding in the project, and most of this document exists to explain it.

## 1. What is being tested

Herbarium specimen records carry free-text locality and habitat notes (`Locality`, `FundortUNdOeko`) written by collectors, often in German, often decades or a century ago. The classifier asks an LLM to read that text and return a CORINE Land Cover (CLC) code, a confidence score, and a short reason.

Downstream, a resolver combines this with a coordinate-based CLC lookup from GEE. The intended routing rule is: low LLM confidence, trust the map; high LLM confidence, trust the text. That rule is why calibration rather than raw accuracy is the metric that matters. A confidence score that does not track correctness makes the resolver worse than either input alone.

### The reference, and the theory we started with

The reference labels come from the CLC raster at the specimen's coordinates. CLC has a 25 ha minimum mapping unit (MMU). So the hypothesis we carried in from the start was this:

> A collector writing "Arabis next to a shore path" is describing a microhabitat far smaller than 25 ha. The map cannot see it. It reports back the dominant cover of the surrounding pixel. So a model that reads the habitat text correctly will disagree with the map, and a model that ignores the text and guesses the regional dominant cover will agree with it. If that is true, agreement with CLC is anti-correlated with the behaviour we want, and using it to rank prompts or models would actively select for the wrong thing.

We did not assume this. The experiments were designed so the data could confirm or deny it, which is why every experiment reports `agree_L1` but none of them decides on it.

## 2. The data, and why it is split the way it is

From a 500-row sample:

1. De-duplicated near-identical `Locality` + `FundortUNdOeko` text (476 survived). Many rows from the same collector team share exact locality strings; without this we would have been testing the same sentence repeatedly under different specimen IDs and calling it 500 samples.
2. Difficulty-tagged by keyword-scanning the habitat text for German/Latin habitat groups (forest, grassland, wetland, heath, water, urban, agri, rock):

   | tag | definition | what it is for |
   |---|---|---|
   | `unambiguous_candidate` | exactly one habitat group in the text | should be easy, and is where the sub-MMU inversion shows up |
   | `boundary_candidate` | two or more groups | genuine ambiguity (bog/heath edges), where a top-3 flag should fire |
   | `thin` | short text, no habitat keyword, has coords | no signal; tests whether the model hallucinates confidently |
   | `edge_no_signal` | no coords and no habitat keyword | nothing to classify from at all |
   | `edge_cultivated` | `Anmerkungen` contains `cult`/`Kult` | garden specimens, where the habitat text describes a place the plant never grew in |

3. Capped collector dominance (no stratum more than a third from one team) and favoured rare families, so the sample is not secretly a test of one collector's prose style.
4. Split roughly 200 rows into `working100` (102 rows) and `heldout` (98 rows), matched on tag proportions and collection-date buckets.

The tags are heuristic guesses, not ground truth. They are keyword matches and a row tagged unambiguous may still sit on a real map boundary. They should be treated as an hierarchy that lets us slice results by the expected difficulty.

Working vs heldout is the test that makes the final number mean anything. Every configuration is made on `working100`. The heldout rows are looked at once at the end and never tuned against. This is done to test for overfitting on `working100`.

## 3. How a run is measured

Each row is run n times (mostly 5), so we can separate the model being unsure from the model being unlucky. `analysis.cells_of()` collapses reps into one cell per row:

| field | meaning | why it exists |
|---|---|---|
| `modal_code` | most common code across reps | the answer |
| `consistency` | modal share (1.0 = same answer 5/5) | self-agreement on identical input |
| `mean_conf` | mean self-reported confidence | the thing the resolver routes on |
| `agree_L1` / `agree_L3` | modal code's first digit / full code vs the CLC reference | reported, never decided on |
| `parse_fail`, `unknown_code` | invalid JSON, or a code outside the taxonomy | validity gate: a model that emits codes that don't exist is not a candidate, whatever else it scores |
| `flip_rate` | share of codes that change between two prompt versions | robustness to trivial prompt edits |
| `calibration()` | mean agreement per confidence band | does high confidence mean more likely right? |
| `topn_signals()` | `conf_gap` (top1 - top2), `l1_spread` (distinct L1 families in top-3) | can the model flag its own ambiguity? |

Confidence bands come from the rubric in the system prompt (`prompt_builder.py`), not from quartile cuts: 0.00 / 0.01-0.09 / 0.10-0.39 / 0.40-0.69 / 0.70-0.89 / 0.90-1.00. The model maps hard onto these (lands on values like 0.28, 0.78, 0.96 rather than spreading
continuously), so binning anywhere else produces artefacts. `plots.py` draws these edges on every confidence plot.

## 4. The experiments

Each experiment freezes everything except one thing. There is no single blended score anywhere (variable meant to improve calibration
is judged on calibration).

### Experiment 1: Prompt A/B

Frozen: model, data, reps. \
Varied: the base prompt (two arms, `a` and `b`).

The reasoning: before comparing six prompt structures, settle the base wording, so the staircase isn't built on a bad foundation.

What we found is that the two arms produced nearly identical codes. This means agreement did not impact our decision and instead, we relied on calibration and consistency.

#### Results
- **Thin-row confidence:** A = 0.391 -> B = 0.190
- **Thin-row consistency:** A = 0.886 -> B = 0.829
- **Rich rows:** Stayed roughly similar across arms. A has a slight edge.
- **Codes moved:** 2 / 20 codes changed across versions.

Codes did not move much. We decided to go with B, as it met our expectations well (lower thin-row confidence, comparable when rich)

Carried forward: prompt `b`, as the base of the staircase.

### Experiment 2: Prompt-structure staircase (v0 -> v5)

Frozen: model (gpt-5.4-nano), texts (`working100`, 102 rows), reps (5), base prompt (b, the exp-1
winner). \
Varied: prompt structure, cumulatively.

Each rung adds one thing and is judged on the axis that thing was supposed to affect, against the rung before it instead of against v0. Bundling all six together does not show us what helped accomplish what.

| rung | change | intended to affect | judged by |
|---|---|---|---|
| v0 | baseline | --- | reference |
| v1 | reason before code | calibration | confidence and consistency; codes should barely move |
| v2 | + taxon (GBIF species, family) | accuracy on thin text | should help disproportionately where text is sparse |
| v3 | + structured labelled fields | nothing specific | expect null |
| v4 | + species guardrail and cultivation flag | cultivated rows | qualitative pass/fail |
| v5 | + top-3 matches | ambiguity detection | is the extra signal usable? |

A guard asserts that prompt tokens are strictly non-decreasing across rungs (v0 = v1 < v2 ≤ v3 < v4 = v5). 

#### Results

| rung | effect | evidence | 
|---|---|---|
| v1 reason-first | slight increase in confidence | conf 0.395 -> 0.490 |
| v2 taxon | slight increase in confidence | conf 0.490 -> 0.563 | 
| v3 structure | no real change |  |
| v4 guardrail | recognizes some cultivated plants |  |
| v5 top-3 | adds signals| 68 references recovered in the top 3 |

agree_L1:  0.343 -> 0.293 -> 0.313 -> 0.354 -> 0.333 -> 0.333     flat; +/-0.05 is ~5 rows, i.e. noise

No real accuracy improvements, but the model got increasingly more confident. We could not answer whether the rising confidence was good (again due to missing expert knowledge). On one hand it could point towards decalibration (confidence loses meaning), which would be a bad thing, as our resolver makes decisions based on the confidence. On the other hand it might just mean the model is more certain about their code assignment being right.

The experiment also highlighted why basing accuracy on agreement is a bad idea, as localities classified as unambiguous had the worst agreement. Unambiguous rows are more descriptive, meaning the model should theoretically obtain better accuracy. \
Why this happens becomes clear when looking at the MMU of CLC mapping. Using the description, the LLM can get far more accurate than 25 ha, meaning using CLC agreement would hurt here.

What earned its place:

- v4, on qualitative evidence. The guardrail fires: the botanic-garden specimen went from code 141
  at confidence 0.42 to confidence 0.12, with the reasoning "no reliable inference". The model
  correctly refuses to classify a garden.
- v5, on signal. There were 68 calls where the CLC reference was not the top pick but was in the
  top-3. That is the raw material for a soft-agreement rule in production.
- v2 and v3 are carried on as they did not harm and we were unable to determine whether the increasing confidence improved or hurt the model.

Small warning: 41 of 102 codes changed between v0 and v1, while v1 only reordered two JSON keys. Within-prompt consistency was around 0.9, so the model is stable across reps but it's very unstable across trivial prompt edits. 

Cost: $1.73 for the whole staircase (3,060 calls).

### Experiment 3: Model comparison

Frozen: prompt = v4. \
Varied: model.

On the config choice: exp 3 decides on a model and none of the deciding metrics need the top3. Running v5 across five models would have inflated cost meaningfullly (worst on Terra, at reasoning-token prices) to collect a signal that doesn't discriminate between models. \
v5 comes back for production and for exp 4.

On the criteria: since exp 2 showed why agreement was not reliable as a ranking metric, the deciding criteria are

| criterion | why |
|---|---|
| validity | invalid or out-of-taxonomy codes disqualify a model outright |
| prompt-stability (v0->v4 flip rate) | the 41/102 result. We did not find the reason and should look into that later. |
| consistency | stable answers on identical input |
| calibration | does confidence track anything? |
| cost | practical constraint |
| qualitative | read the reasoning on cultivated and boundary rows |

The cheap models were run at both v0 and v4 as that allows ranking stability.

#### Terra: ceiling check, not a candidate

gpt-5.6-terra ran on a deliberately selected 30-row subset, never as a shipping candidate. The
subset is biased toward nano's failures, so its aggregate agreement is not Terra's accuracy and
must be read per `subset_reason`:

| block | n | question it answers |
|---|---|---|
| `crux_unamb_disagree` | 12 | the crux: unambiguous rows where nano disagreed with CLC |
| `cultivated` | 3 | does a stronger model handle gardens without the guardrail spelled out? |
| `boundary_inconsistent` | 8 | boundary rows where nano was least consistent, so a better model should show its worth |
| `control_unamb_agree` | 4 | control: does Terra break rows nano got right? |
| `thin_hallucination_check` | 3 | does the stronger model get more confident on no-signal text? |

The crux is the whole point of the experiment. If Terra agrees with CLC there, nano was genuinely wrong and a better model buys accuracy. If Terra also disagrees, the map is the limitation rather than the model: two independent models converging against the reference confirms sub-MMU independently. No model upgrade can fix it.

#### Results

Prompt-instability is universal. Every model flips 48-75% of codes on the v0→v4 prompt change.
This is not a nano weakness but a property of the task, and it is arguably the single most
important operational finding here: the code you get depends materially on incidental prompt
details.

gpt-5-nano was eliminated on validity, having emitted invalid codes.

Chosen model: gpt-5.4-mini, chosen on calibration, with consistency and cost
as supports.

Terra crux verdict: \
Terra agreed with CLC on 3/12 crux rows \
Terra returned the cheap model's code on 9/12 crux rows


Cost per 100k: ~77 USD

gpt-5.4-nano and gpt-4.1-nano performed decently well and could be used as cheaper alternatives.

### Experiment 4: Heldout confirmation

Frozen: everything. Model from exp 3, prompt v5 (as that would be shipped), reps. \
Varied: only the data (the 98 heldout rows)

This is a confirmation not a comparison. It only tells us whether we overfit our configuration to the test dataset.

If heldout is noticeably worse, the prompt cannot be changed to improve it directly (would compromise heldout). Instead the low performance needs to be taken as is (or change data and restart).

#### Results

| metric | working | held-out | verdict |
|---|---|---|---|
| consistency | 0.859 | 0.837 | generalises |
| parse_fail | 0.0 | 0.0 | generalises |
| unknown_code | 0.0 | 0.0 | generalises |
| rows lost | 0 | 0 | generalises |
| cost / row | 0.0065 | 0.0066 | generalises |
| mean_conf | 0.659 | 0.721 | difficulty-mix, not drift (see below) |
| `agree_L1` | 0.384 | 0.469 | reported; not a validation |

No overfitting on any generalisable metric. Passes.

Calibration is inconclusive, but a combined table shows that might just be noise.

Heldout calibration is inverted (agreement reduces as richness increases), which fits with the sub-MMU theory (could be a coincidence though).

It would cost ~130 USD to run 100k rows.

## 5. Conclusions

1. The reference is the limitation, not the model. CLC agreement is anti-correlated with correct
   habitat reading on exactly the rows we care about (unambiguous 0.20 vs thin 0.34). It is
   reported everywhere and decides nothing. **Do not score against CLC.**
2. The classifier is operationally sound. Consistency around 0.84 in heldout, zero parse failures,
   zero invalid codes, zero rows lost, about $130 per 100k.
3. It is decalibrated by construction. More prompt scaffolding gives more confidence and no more
   accuracy. Since the resolver routes on confidence, this is should be tested again.
4. It is prompt-fragile, and so are the tested models. Often at least half of the codes flip on a
   trivial prompt edit, meaning any deployed prompt must be frozen and versioned. A harmless-looking
   reword is not harmless.
5. v4 and v5 are reasonable improvements. The results of v2 and v3 are inconclusive.
6. We still do not know whether the classifier is right.

## 6. What is still open

Expert labels are necessary.

The model is very sensitive to water (at least 5.4-nano is).

Using a basic tier OpenAI account, 100k rows take roughly 18 hours (estimated).

## 7. Reproducing

```
notebooks/1_prompt_ab.ipynb
notebooks/2_prompt_structure.ipynb
notebooks/3_model_comparison.ipynb
notebooks/4_heldout.ipynb
```

Run the staircase with:

```
python -m testing.util.exp2.staircase --input data/working100.csv --reps 5
```

## 8. Decisions log

| exp | decision | made on | not made on |
|---|---|---|---|
| 1 | base prompt `b` | calibration, consistency | accuracy: arms produced the same codes |
| 2 | ship v5 (v4 guardrail + top-3) | qualitative guardrail behaviour, top-3 signal | agreement: flat across all six rungs |
| 3 | model = gtp-5.4-mini | calibration, consistency, cost, validity | agreement was unusable |
| 4 | config generalises; ship it | consistency, validity, cost | calibration was inconclusive |