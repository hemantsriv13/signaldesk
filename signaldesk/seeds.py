"""Starter watchlist and reading sources, checked on 2026-11-02.

A company is enabled only when its job board was tied to the employer: the official careers page
links to that board or calls its API, or the board's job links sit on the employer's own domain.
Boards that answered but could not be tied to the employer start disabled, with the reason.
Everything here is editable in the app (Sources).
"""

CHECKED = "2026-11-02"

COMPANIES = [
    # name, official careers URL, ATS, board id, enabled, how it was verified
    ("Anthropic", "https://www.anthropic.com/careers/jobs", "greenhouse", "anthropic", True, "Careers jobs page links greenhouse.io/anthropic job pages"),
    ("Databricks", "https://www.databricks.com/company/careers", "greenhouse", "databricks", True, "Board job links point to databricks.com"),
    ("Glean", "https://www.glean.com/careers", "greenhouse", "gleanwork", True, "Careers page loads the Greenhouse board 'gleanwork'"),
    ("Sarvam AI", "https://www.sarvam.ai/careers", "ashby", "sarvam", True, "Careers page links jobs.ashbyhq.com/sarvam"),
    ("Observe.AI", "https://www.observe.ai/careers", "greenhouse", "observeai", True, "Careers page links the board; job links point to observe.ai"),
    ("Stripe", "https://stripe.com/jobs", "greenhouse", "stripe", True, "Board job links point to stripe.com"),
    ("MongoDB", "https://www.mongodb.com/company/careers", "greenhouse", "mongodb", True, "Board job links point to mongodb.com"),
    ("Elastic", "https://www.elastic.co/careers", "greenhouse", "elastic", True, "Board job links point to jobs.elastic.co"),
    ("Groww", "https://groww.in/careers", "greenhouse", "groww", True, "Careers page links the Greenhouse board 'groww'"),
    ("CRED", "https://careers.cred.club/openings", "lever", "cred", True, "Openings page links jobs.lever.co/cred"),
    ("Cursor (Anysphere)", "https://cursor.com/careers", "ashby", "cursor", True, "Careers page links jobs.ashbyhq.com/cursor"),
    ("SpotDraft", "https://www.spotdraft.com/careers", "ashby", "spotdraft", True, "Careers page calls the Ashby board API for 'spotdraft'"),
    ("UiPath", "https://www.uipath.com/careers", "ashby", "uipath", True, "Careers page links jobs.ashbyhq.com/uipath"),
    ("Fivetran", "https://www.fivetran.com/careers", "greenhouse", "fivetran", True, "Board job links point to fivetran.com"),
    ("Together AI", "https://www.together.ai/careers", "greenhouse", "togetherai", True, "Careers page calls the Greenhouse board API for 'togetherai'"),
    # Answered, but not tied to the employer by an automated check. Confirm, then enable.
    ("OpenAI", "https://openai.com/careers/", "ashby", "openai", False, "Unverified: careers page refused automated access (HTTP 403)"),
    ("Atlan", "https://atlan.com/careers/", "ashby", "atlan", False, "Unverified: careers page does not link a board in its HTML"),
    ("ElevenLabs", "https://elevenlabs.io/careers", "ashby", "elevenlabs", False, "Unverified: careers page does not link a board in its HTML"),
    ("Harvey", "https://www.harvey.ai/careers", "ashby", "harvey", False, "Unverified: careers page does not link a board in its HTML"),
    ("GitLab", "https://about.gitlab.com/jobs/", "greenhouse", "gitlab", False, "Unverified: board is named GitLab but the careers page does not link it in its HTML"),
    ("Celonis", "https://careers.celonis.com", "greenhouse", "celonis", False, "Unverified: board is named Celonis but the careers page does not link it in its HTML"),
    ("Meesho", "https://www.meesho.io/jobs", "lever", "meesho", False, "Unverified: careers page does not link a board in its HTML"),
]

READING_SOURCES = [
    # name, site, feed, kind, enabled, note
    ("Latent Space", "https://www.latent.space", "https://www.latent.space/feed", "substack", True, "AI engineering interviews and essays; full text for free posts"),
    ("Lenny's Newsletter", "https://www.lennysnewsletter.com", "https://www.lennysnewsletter.com/feed", "substack", True, "Product practice; paid posts arrive as excerpts"),
    ("One Useful Thing", "https://www.oneusefulthing.org", "https://www.oneusefulthing.org/feed", "substack", True, "AI adoption at work"),
    ("AI as Normal Technology", "https://www.aisnakeoil.com", "https://www.aisnakeoil.com/feed", "substack", True, "Evidence and limits of AI claims"),
    ("Interconnects", "https://www.interconnects.ai", "https://www.interconnects.ai/feed", "substack", True, "Models, training and the industry"),
    ("Ahead of AI", "https://magazine.sebastianraschka.com", "https://magazine.sebastianraschka.com/feed", "substack", True, "LLM techniques explained"),
    ("The Pragmatic Engineer", "https://newsletter.pragmaticengineer.com", "https://newsletter.pragmaticengineer.com/feed", "substack", True, "Engineering practice; most posts arrive as excerpts"),
    ("Exponential View", "https://www.exponentialview.co", "https://www.exponentialview.co/feed", "substack", False, "Broad tech and economy; off by default to keep the list focused"),
    ("Eugene Yan", "https://eugeneyan.com", "https://eugeneyan.com/rss/", "blog", True, "Applied ML and LLM systems; the feed carries short summaries only"),
    ("Hamel Husain", "https://hamel.dev", "https://hamel.dev/index.xml", "blog", True, "LLM evaluation in practice"),
    ("Simon Willison", "https://simonwillison.net", "https://simonwillison.net/atom/entries/", "blog", True, "Hands-on LLM tooling notes"),
    ("Chip Huyen", "https://huyenchip.com", "https://huyenchip.com/feed.xml", "blog", True, "AI engineering; posts are infrequent"),
    ("Netflix TechBlog", "https://netflixtechblog.com", "https://netflixtechblog.com/feed", "engineering", True, "Company engineering case studies"),
    ("Airbnb Tech Blog", "https://medium.com/airbnb-engineering", "https://medium.com/feed/airbnb-engineering", "engineering", True, "Company engineering case studies"),
    ("Flipkart Tech Blog", "https://blog.flipkart.tech", "https://blog.flipkart.tech/feed", "engineering", True, "Indian e-commerce engineering case studies"),
    ("OpenAI News", "https://openai.com/news", "https://openai.com/news/rss.xml", "vendor", False, "Vendor announcements: claims are the vendor's own. Off by default; the feed carries summaries only"),
    ("Hugging Face Blog", "https://huggingface.co/blog", "https://huggingface.co/blog/feed.xml", "vendor", False, "Titles and links only in the feed. Off by default"),
]


def seed(db) -> None:
    from .db import now_iso
    if not db.scalar("SELECT COUNT(*) FROM companies"):
        for name, url, ats, ats_id, enabled, how in COMPANIES:
            db.insert("companies", {"name": name, "careers_url": url, "ats": ats, "ats_id": ats_id, "enabled": int(enabled),
                                    "verification": f"{how} (checked {CHECKED})", "created_at": now_iso()})
    if not db.scalar("SELECT COUNT(*) FROM reading_sources"):
        for name, site, feed, kind, enabled, note in READING_SOURCES:
            db.insert("reading_sources", {"name": name, "site_url": site, "feed_url": feed, "kind": kind, "enabled": int(enabled),
                                          "verification": f"Feed returned entries on {CHECKED}. {note}", "created_at": now_iso()})
