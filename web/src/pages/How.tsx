import { PageHeader, Section } from "@/components/common"
import { href } from "@/lib/router"

const AGENTS: [string, string, string][] = [
  ["Job Scout", "jobs", "Reads the public job boards of the employers in Sources. Rules, not the model, decide the location class, pay wording and whether a role fits your role families. Roles that match go to the model for a fit explanation; unclear ones wait in To review."],
  ["Reading Scout", "reading", "Reads the RSS feeds in Sources. It notes whether it got the full article, an excerpt or only a title, and the model writes a reading card from what it got."],
  ["Case Study Analyst", "cases", "Picks full-text articles that describe a real deployment, or a public link you paste, and breaks each into problem, workflow, what AI does, what ordinary software does, data, failure modes and evidence."],
  ["Digest Editor", "saved", "Picks up to 3 jobs, 1 case study and 2 articles that you have not seen in recent briefings, rechecks that the jobs are still listed, says why each is there, and asks the model for one suggested action."],
]

export default function How() {
  return (
    <div className="flex max-w-[78ch] flex-col gap-8 p-4 sm:p-6">
      <PageHeader title="How this works" line="What SignalDesk does, what it does not do, and where each number comes from." />
      <Section title="Four agents, one local model">
        <p>Each agent is ordinary code that collects, filters and checks. Only the writing is done by a language model, and that model runs on this laptop through Colibri. Nothing is sent to a paid AI service, and there is no cloud fallback.</p>
        <dl className="flex flex-col gap-4">
          {AGENTS.map(([name, page, text]) => (
            <div key={name}><dt className="font-medium"><a className="underline-offset-2 hover:underline" href={href(page)}>{name}</a></dt><dd className="text-[0.95rem]">{text}</dd></div>
          ))}
        </dl>
      </Section>
      <Section title="One request at a time">
        <p>Model requests wait in a queue and run one by one, so the laptop's 6 GB graphics card is never asked for two at once. If the model server is off or running a different model, requests wait; collecting and reading saved results keep working. A request that fails is retried a few times, then marked failed, and the queue moves on. You can cancel a run from Today or Agent runs; a request already in progress finishes first.</p>
        <p>Every result is saved with the text it read, the prompt version and the model's name. The same item is not analysed twice unless its text, your profile or the prompt changes, in which case the old result is marked outdated.</p>
      </Section>
      <Section title="What to trust">
        <ul className="flex list-disc flex-col gap-2 ps-5">
          <li>Employer, title, location wording, pay wording, dates and links come straight from the source.</li>
          <li>"Potential match" means some requirements line up with facts in your profile. It does not confirm you are eligible, and there is no fit percentage.</li>
          <li>"Remote" is never read as "worldwide". Remote roles that do not mention India stay in To review.</li>
          <li>Quotes are checked against the source. A quote the model invented is flagged; a claim about you that cites no profile fact is removed.</li>
          <li>Case studies label each point as source-reported, vendor claim, the analyst's inference or missing. A company describing its own product is a vendor.</li>
          <li>Text from web pages is treated as data. If a page tries to give the model instructions, it is flagged and ignored; it cannot change your preferences or send anything.</li>
          <li>The small model can still be wrong. Open the original before acting.</li>
        </ul>
      </Section>
      <Section title="What it does not do">
        <ul className="flex list-disc flex-col gap-2 ps-5">
          <li>It does not apply to jobs, contact recruiters or send messages.</li>
          <li>It does not scrape LinkedIn, log in anywhere, solve CAPTCHAs or get around paywalls. Add a LinkedIn job by pasting it.</li>
          <li>It only works while this laptop and SignalDesk are running. The daily schedule is off until you turn it on.</li>
        </ul>
      </Section>
      <Section title="Costs">
        <p>No hosted model and no paid scraping service is used. Local inference has no per-token bill, but it does use this laptop's electricity and time; SignalDesk shows request counts, model time and the token counts the server reports, and does not estimate money.</p>
      </Section>
    </div>
  )
}
