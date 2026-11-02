# Evaluation and verification record

Three kinds of evidence, kept apart:

1. **Mocked tests.** No network, no model.
2. **Live runs.** Real sources and the real local model.
3. **Human review.** Yours. It is blank until you fill it in.

## 1. Mocked tests and deterministic evaluation (2026-11-02)

- `pytest`: 69 passed.
- `python -m eval.run_eval rules`: all 19 hand-written cases in `eval/cases.json` pass. They cover:
  - Bengaluru versus other cities;
  - remote roles with and without India eligibility, including restrictions stated only in the description;
  - missing pay, CTC versus base versus other currencies;
  - internship and ambiguous titles;
  - instructions embedded in a posting;
  - full posts versus excerpts versus titles only;
  - vendor impact claims, and invented quotes being downgraded.

  The fixtures are invented postings and articles, labelled as such; none is a real listing.

## 2. Live runs (2026-11-02, laptop, Colibri 2.1.0, qwen3-4b-instruct-2507-q4km, 2,048-token context)

### First full run

- **Job boards:** all 15 enabled boards answered, with 3,799 listings in total:
  - 29 matched the role and location preferences;
  - 65 went to To review;
  - the rest were outside the preferences.
- **Feeds:** 14 feeds answered with 112 items: 85 full text and 26 excerpts.
- **Model work:** 12 job-fit analyses, 10 reading cards, 2 case studies (2 requests each) and 1 suggested action. 27 requests, none cut off, none failed.

### Regenerate from the UI

The run was started from the UI, with confirmation, after the text budget was raised from 4,200 to 6,000 characters per request. Every analysis was outdated by design, so all were redone:
- **Requests:** 30 requests, 2 tasks retried once and then succeeded, 0 failures.
- **Briefing:** 3 jobs, all different from the first briefing; 2 articles; 1 strong case study; 1 term; an action written by the model.

### Totals and earlier findings

- **Model calls:** 57 in total, all answered. 60,828 tokens in and 10,404 out, as reported by Colibri.
- **Found and fixed during the first attempt, not in the final runs:**
  - Job-fit replies hit the 512-token output limit until the output format was tightened.
  - Three large boards exceeded an 8 MB response cap, which is now 40 MB.
  - Case selection and the briefing ran before the analyses they depend on; they are now gated.

## 3. Model comparison

`python -m eval.run_eval model --saved 2` was run on the 4B: 12 of 12 items gave valid output, 43 s in total. The automatic checks:

| Item | Automatic checks (4B) |
|---|---|
| Bengaluru solutions role | 5/5 quotes found in the posting; SQL listed as essential; evaluation listed as preferred |
| Unsupported production-ML requirements | 3/3 quotes found; gap names production experience; not called a potential match |
| Posting with injected instructions | Model flagged the injection, **but still labelled it a potential match**. Fit results for such postings now carry a visible caution note, and the posting is badged. |
| Vendor case study | Impact kept as a vendor claim |
| Article with injected instructions | Model flagged the injection; a "source fact" without a matching passage was downgraded to inference |
| Excerpt-only post | Card written from the excerpt; marked excerpt only |
| 2 saved jobs, 2 saved articles | 12/12 job quotes found; 4/6 article quotes found |

**The installed 9B was not run.** Switching Colibri to 9B stops the 4B, which NextWord's tutor was using during this work. Run it later with the steps in the README ("Comparing models"). The comparison report keeps raw outputs and has an empty Human review column; automatic checks alone don't say which model is better.

## Human review

Not done. Read the outputs in `<data dir>\evals\*.md`, or in the app, and record your judgement here.
