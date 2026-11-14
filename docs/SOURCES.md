# Source coverage

Moved from the README. Checked 2026-11-02.

**Employers, enabled.** Each board is tied to the employer: the careers page links to the board or calls its API, or the job links are on the employer's own domain.
- Anthropic, Databricks, Glean, Sarvam AI, Observe.AI, Stripe, MongoDB, Elastic.
- Groww, CRED, Cursor (Anysphere), SpotDraft, UiPath, Fivetran, Together AI.

**Employers, disabled until you confirm them.** Each board answered, but an automated check could not tie it to the employer:
- OpenAI, Atlan, ElevenLabs, Harvey, GitLab, Celonis, Meesho.

**Feeds, enabled.**
- Substack: Latent Space, Lenny's Newsletter, One Useful Thing, AI as Normal Technology, Interconnects, Ahead of AI, The Pragmatic Engineer.
- Blogs: Eugene Yan, Hamel Husain, Simon Willison, Chip Huyen.
- Engineering: Netflix TechBlog, Airbnb Tech Blog, Flipkart Tech Blog.

**Feeds, off by default.** Exponential View, OpenAI News (vendor, summaries only) and Hugging Face Blog (titles only).

**Not supported.**
- LinkedIn scraping, logged-in browsing, CAPTCHA solving and paywall workarounds.
- Workday, SmartRecruiters and other boards without a documented public API: mark those employers "manual" and add jobs by hand. A pasted URL is fetched only if robots.txt allows it, and schema.org JobPosting data is used when the page has it.
