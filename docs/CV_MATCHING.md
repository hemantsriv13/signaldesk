# Matching jobs against your CV

Moved from the README.

In **Profile and settings → Your profile → Match jobs using your CV**, upload a
text-based PDF, DOCX or UTF-8 TXT (up to 5 MB), or paste the CV text. Extraction
runs locally without model calls. Scanned PDFs need OCR first. Check PDF column
order, dates and wrapped lines against your original document.

Choose up to 30 factual statements, use them in the profile editor, edit any
incomplete statements, and press **Save profile**. This replaces your saved facts;
uploading and previewing alone changes nothing. Exclude contact details and
headings. Long paragraphs must be split into statements of at most 400 characters.
The original file and extracted text are not persisted by SignalDesk; only the
facts explicitly saved into the existing local profile persist.

Open a job and choose **Analyse fit**, or **Re-analyse (outdated)** after changing
your CV facts. The existing queue sends reviewed profile facts and the job's
requirements to the configured local Qwen model through Colibri. It separates
essential/preferred requirements and reports supporting fact IDs, gaps, unknowns
and a qualitative match label. Existing location and salary rules still apply.
No paid model service is used. If Colibri is offline, analysis waits while CV
import and browsing remain usable.

The default model has limited context. Facts are selected by keyword overlap and
whole statements are retained within a prompt budget. Assessments disclose when
only part of the profile was sent. This selection can miss relevant transferable
experience. Job text may also be shortened; inspect the coverage warning and
original listing. A cited fact ID establishes provenance, not that the model's
interpretation is correct. Match labels are advisory, not hiring probabilities.
Saving changed facts makes previous analyses outdated; it does not rewrite
historical saved digests or automatically spend model calls on all stored jobs.
