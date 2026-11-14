# Human review of job-fit analyses

Automatic checks confirm that quotes exist and that cited fact ids are real. They cannot say whether a
match label is fair or whether a cited fact supports the requirement it is tied to. Only you can judge
that. This kit gives you a sheet to fill in and counts your verdicts. It never fills in a verdict.

Nothing here calls the model or changes the app's database (it is opened read-only). Sheets and
scores are written to `<data dir>\evals`, never into the repository.

## 1. Export a sheet

From the `signaldesk` folder:

```bat
.venv\Scripts\python -m eval.review export --n 20
```

This writes `<data dir>\evals\review-<date-time>.csv` with the 20 most recent saved job-fit analyses,
one row each. Open it in Excel.

| Column | What it holds |
|---|---|
| `review_id`, `item`, `model`, `source` | Row id; the job (`saved-job-<id>`); the model that answered; where the row came from |
| `job_title`, `employer`, `analysed_at` | The job and when it was analysed |
| `requirement_text_sent` | The job text the model was given: summary and requirement sections, cut to fit |
| `requirement_text_status` | Whether that text is exact. "rebuilt; same length…" means it matches what was sent. "REBUILT FROM TODAY'S JOB TEXT" means the posting or settings changed since, so judge with care. "NOT RECORDED" means an older eval run did not keep it |
| `profile_facts_sent` | The facts from your profile that were sent, with their ids |
| `essential`, `preferred` | The model's split, each with its quote and whether the quote was found in the posting |
| `cited_facts` | Which fact ids the model tied to which requirement |
| `gaps`, `unknowns`, `match_label` | The rest of the model's answer |
| `checks_notes` | What the automatic checks removed or flagged |
| `verdict_match_label`, `verdict_cited_facts`, `note` | **Yours to fill in** |

To review without knowing which model answered, hide the `model` and `source` columns before you start.

## 2. Rubric

Judge each row **against what the model was sent**: `requirement_text_sent` and `profile_facts_sent`.
If a relevant part of your background was not sent, the model could not use it. Say so in `note`
(that is a fact-selection problem, not a model error).

**`verdict_match_label`**: one of `right`, `too generous`, `too harsh`.

The labels, from strongest to weakest: `potential match`, `weak match`, `not a match`. `unknown` means
the model declined to judge.

- `right`: given the text and facts sent, you would give the same label.
- `too generous`: the label is stronger than the evidence supports. Typical cause: an essential
  requirement is unmet or unsupported by any fact sent, yet the label is "potential match".
- `too harsh`: the label is weaker than the evidence supports. Typical cause: the facts sent cover the
  essential requirements, yet the label is "weak match" or "not a match".
- For `unknown`: `right` if the text sent genuinely does not allow a judgement. Otherwise `too harsh`
  if you would have said potential or weak match, `too generous` if you would have said not a match,
  and write the label you would have given in `note`.

Location and pay are decided by rules, not by the model. Do not mark a label wrong because of them.

**`verdict_cited_facts`**: one of `yes`, `partly`, `no`.

- `yes`: every cited fact supports the requirement it is tied to.
- `partly`: some do, or they support it only weakly (for example "uses SQL" cited for "builds data pipelines").
- `no`: none of the cited facts supports its requirement, or nothing was cited although a relevant fact
  was sent.
- If nothing was cited and no relevant fact was sent, that is `yes`.

**`note`**: free text. Useful: the label you would have given, a wrong essential/preferred split, a
quote that was found but misread, a gap that is not a gap.

Leave a verdict blank to skip a row. Blank rows are counted as "not reviewed".

## 3. Score it

Save the sheet as **CSV UTF-8** (Excel: File → Save As → "CSV UTF-8 (Comma delimited)"), then:

```bat
.venv\Scripts\python -m eval.review score "D:\LocalAI\signaldesk\evals\review-<date-time>.csv"
```

It prints, and saves as `score-review-<date-time>.md` beside the sheet:

- counts of each verdict per model;
- where two models answered the same item, your verdicts side by side;
- any entry it could not read (a typo such as `maybe`), so you can fix it and score again.

## 4. Compare the 4B and the installed 9B

Both runs must use the same jobs. `--saved 10` takes the 10 most recent matching jobs, so run both
without a sweep in between. Switching to 9B stops the 4B server (and NextWord's tutor), so do this when
nothing else needs the model.

```bat
:: 1. With Colibri serving the 4B
.venv\Scripts\python -m eval.run_eval model --saved 10

:: 2. Switch to 9B, run the same items, switch back
cd .. && local-ai\start-colibri.cmd 9b
cd signaldesk && .venv\Scripts\python -m eval.run_eval model --model-id qwen3.5-9b-q4km --saved 10
cd .. && local-ai\start-colibri.cmd 4b && cd signaldesk

:: 3. One sheet with both runs (file names are printed by steps 1 and 2)
.venv\Scripts\python -m eval.review export --no-saved --run "D:\LocalAI\signaldesk\evals\model-qwen3-4b-instruct-2507-q4km-<time>.json" --run "D:\LocalAI\signaldesk\evals\model-qwen3.5-9b-q4km-<time>.json"
```

Fill in the sheet and score it as above. The "Same item, two models" table shows your verdicts for
each job from both models. The run files also include the fixture jobs from `eval/cases.json`
(invented postings), which is useful as a baseline.

Runs made before this kit existed did not record the text sent. Their rows say "NOT RECORDED"; rerun
them to review properly.

## Record

Record your results in [EVALUATION.md](EVALUATION.md) under "Human review": the date, the sheet's
file name, the counts per model, and anything you learned. Until then the human review is not done.
