const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType, ExternalHyperlink,
  PageBreak
} = require("docx");

const NAVY = "0A2540", GOLD = "C08F2F", TEAL = "168F89", INK = "28251D", MUTED = "5A6B7C", LINE = "D4D1CA", PAPER = "F5F7FA";

const FONT = "Calibri", HFONT = "Calibri";

function h1(text) {
  return new Paragraph({ spacing: { before: 60, after: 160 },
    children: [new TextRun({ text, bold: true, size: 40, color: NAVY, font: HFONT })] });
}
function h2(text) {
  return new Paragraph({ spacing: { before: 260, after: 100 },
    border: { bottom: { color: LINE, size: 6, style: BorderStyle.SINGLE, space: 4 } },
    children: [new TextRun({ text, bold: true, size: 26, color: NAVY, font: HFONT })] });
}
function p(runs, opts = {}) {
  const arr = Array.isArray(runs) ? runs : [runs];
  return new Paragraph({ spacing: { after: opts.after ?? 120 }, alignment: opts.align,
    children: arr.map(r => typeof r === "string" ? new TextRun({ text: r, size: 21, color: INK, font: FONT }) : r) });
}
function bullet(text, opts = {}) {
  return new Paragraph({ bullet: { level: opts.level ?? 0 }, spacing: { after: 70 },
    children: [ ...(opts.lead ? [new TextRun({ text: opts.lead, bold: true, size: 21, color: NAVY, font: FONT })] : []),
                new TextRun({ text, size: 21, color: INK, font: FONT }) ] });
}
function muted(text, size = 18) {
  return new Paragraph({ spacing: { after: 120 }, children: [new TextRun({ text, italics: true, size, color: MUTED, font: FONT })] });
}
function cell(text, { bold = false, color = INK, shade = null, size = 21, align } = {}) {
  return new TableCell({
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    shading: shade ? { type: ShadingType.CLEAR, fill: shade } : undefined,
    children: [new Paragraph({ alignment: align, children: [new TextRun({ text, bold, color, size, font: FONT })] })],
  });
}

// ---- Access credentials card (table) ----
function credTable() {
  const rows = [
    ["Web address", "https://szlholdings-david-leads.hf.space"],
    ["Username", "david"],
    ["Password", "David2026!"],
    ["Secure access key", "DAVID-2026-SECURE-DEMO"],
  ].map(([k, v]) => new TableRow({ children: [
    cell(k, { bold: true, color: NAVY, shade: "EFF3F8" }),
    cell(v, { bold: true, color: INK }),
  ]}));
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    borders: {
      top: { style: BorderStyle.SINGLE, size: 6, color: LINE }, bottom: { style: BorderStyle.SINGLE, size: 6, color: LINE },
      left: { style: BorderStyle.SINGLE, size: 6, color: LINE }, right: { style: BorderStyle.SINGLE, size: 6, color: LINE },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 6, color: LINE }, insideVertical: { style: BorderStyle.SINGLE, size: 6, color: LINE },
    },
    columnWidths: [3200, 6400],
    rows,
  });
}

const doc = new Document({
  styles: { default: { document: { run: { font: FONT, size: 21, color: INK } } } },
  sections: [{
    properties: { page: { margin: { top: 900, bottom: 900, left: 1000, right: 1000 } } },
    children: [
      // Header band
      new Paragraph({ spacing: { after: 40 }, children: [
        new TextRun({ text: "DAVID LEADS", bold: true, size: 30, color: NAVY, font: HFONT }),
        new TextRun({ text: "   Sovereign Insurance Intelligence", bold: true, size: 18, color: GOLD, font: HFONT }),
      ]}),
      muted("A private, public-data lead-intelligence console — prepared for David Abraham, New York Life.", 19),

      h1("Your private intelligence console"),
      p([
        new TextRun({ text: "David — this is your own console for finding the people in your territory who just had a life event that creates a real insurance need. ", size: 21, color: INK, font: FONT }),
        new TextRun({ text: "Everything you see is built live from public records, ranked so the best prospects rise to the top, and every lead comes with a proof trail you can open and check.", size: 21, color: INK, font: FONT }),
      ]),
      p([ new TextRun({ text: "Honest by design: ", bold: true, color: NAVY, size: 21, font: FONT }),
          new TextRun({ text: "public, aggregate data only — never private personal information — and nothing is ever fabricated.", size: 21, color: INK, font: FONT }) ]),

      h2("How to log in"),
      muted("Open the link below in any browser (Chrome, Safari, Edge — phone or laptop). It is a private, login-gated console, not a public website.", 19),
      credTable(),
      new Paragraph({ spacing: { before: 120, after: 120 }, children: [
        new ExternalHyperlink({ link: "https://szlholdings-david-leads.hf.space",
          children: [new TextRun({ text: "→ Open David Leads", bold: true, size: 22, color: TEAL, underline: {}, font: FONT })] }),
      ]}),
      muted("Tip: the console may take ~20–30 seconds to wake up on the very first visit. Give it a moment, then log in.", 18),

      h2("A 7-step guided tour"),
      bullet("Click \"Find Leads.\" In seconds it scans public records across the East Coast — new businesses, new licenses, home purchases, building permits, and more — and finds the people who just had a life event that creates an insurance need.", { lead: "1. Find leads.  " }),
      bullet("Click \"Coverage Map\" to see your states light up by how much activity is happening. Where we don't yet have live data, we say so plainly — we never pretend to have data we don't.", { lead: "2. See your territory.  " }),
      bullet("Each lead shows a Hot / Warm / Nurture badge, the matched New York Life product, an illustrative annual premium, an \"Act now\" flag for time-sensitive ones, plus its momentum (heating up, cooling off, or steady), a confidence level (High / Medium), and how many public records confirm it. The strongest, best-confirmed leads rise to the top.", { lead: "3. Read the ranked leads.  " }),
      bullet("Click the ▸ arrow on any lead to see why they surfaced, the public records behind them, an estimate of their wealth, and your next best action — with a ready-to-use talk track you can read straight off the screen.", { lead: "4. Expand a lead.  " }),
      bullet("Click \"Call Brief\" on your top lead. You get a short, ready-to-use brief — who to call, why now, three opening lines, and what to be sensitive about — so you can pick up the phone with confidence.", { lead: "5. Open the Call Brief.  " }),
      bullet("Click \"Proof & Sources\" on any lead. You'll see a clear panel confirming the lead comes from public records, lists every source, and shows nothing was invented. This is what you can show compliance.", { lead: "6. Check the proof.  " }),
      bullet("\"How scoring works\" explains, in plain English, the five things that make a lead strong and the public records behind each. \"Export CSV\" downloads your call list as a spreadsheet. \"Push to CRM\" sends your leads into your CRM.", { lead: "7. See how it works & export.  " }),

      h2("Real prospects you can act on today"),
      muted("Click \"Real Businesses\" in the toolbar. This pulls real, currently-filed public business and professional-license records live from state portals across New York, New Jersey, Pennsylvania, Maryland, Delaware, and Connecticut — actual businesses with their public address and a suggested New York Life angle (key-person, buy-sell, business-continuation, disability overhead, or starter life + disability for newly-licensed professionals).", 19),
      bullet("Each row is a real public record — real business name, category, public business address, and a link to the official source. Every row has a \"Proof & Sources\" button so you can see exactly where it came from."),
      bullet("It uses public BUSINESS records only — no private personal phone numbers, no social media, nothing fabricated. You do your own compliant outreach (look up the business, no auto-dialing).", { lead: "Compliant by design.  " }),
      bullet("This is the start: more states and record types are easy to add, plus an opt-in web form so prospects who want to hear from you come to you directly.", { lead: "Growing.  " }),

      h2("Where need is rising"),
      muted("Click \"Rising Areas\" in the toolbar to see, at a glance, which areas have more new activity than usual right now — more new homeowners and businesses means more people who just took on a new obligation and need coverage. Each area is marked Rising, Steady, or Quiet, in plain language, with a link to the public source behind it. It tells you where to focus your week.", 19),

      h2("The wealth map"),
      muted("Click \"Wealth Map\" in the toolbar. You asked whether taxes could help find leads — they can. This reads free public IRS tax statistics to point you at the right neighborhoods, never named individuals. Two views:", 19),
      bullet("Ranked ZIP codes where the most households file high-income returns ($200k+ adjusted gross income). Top of your list today is ZIP 10023 in Manhattan — about 11,500 high-income returns, roughly a third of all filers there. The suggested angle is estate planning, premium-financed life, and annuities. These are affluent-territory targets, drawn from IRS Statistics of Income by ZIP code.", { lead: "1. Affluent ZIPs.  " }),
      bullet("Counties seeing the biggest inflow of people and income from elsewhere — a relocation is a classic trigger for an estate and coverage review. Top today is New York County, with about $14.8 billion in adjusted gross income moving in (≈77,900 returns), drawn from IRS county-to-county migration data. The angle is a new-resident coverage review.", { lead: "2. Money-in-motion counties.  " }),
      bullet("This uses aggregate IRS tax statistics for territory targeting only — it never names a person and never uses anyone's private tax data. It tells you where to focus, then you prospect compliantly in those areas.", { lead: "Compliant by design.  " }),
      bullet("Every row links to the official IRS source so you can check it yourself, same as your leads.", { lead: "Provable.  " }),

      h2("Let prospects come to you"),
      muted("Click \"Opt-In\" in the toolbar. This is the cleanest way to get a real name and a real phone number you can call — because the prospect gives it to you and asks to be contacted.", 19),
      bullet("Anyone interested fills in their name, phone, email, and a note, and checks a box consenting to be contacted. Their details are only saved if they check that box — no consent, nothing is stored.", { lead: "How it works.  " }),
      bullet("Because the prospect opted in, you have written consent on file — the compliant, safe way to call or text. Every opt-in is saved with a record of when and how consent was given.", { lead: "Call-ready & compliant.  " }),
      bullet("Share the form link in your email signature, on a flyer, or after a seminar. The leads land in your console under their own list, ready to call.", { lead: "Share it anywhere.  " }),

      h2("What makes this different"),
      bullet("Every lead carries a proof trail — you can show compliance exactly where each detail came from.", { lead: "Provable.  " }),
      bullet("It only uses free, public information. No private personal data, ever. Anyone who can't be contacted is removed automatically.", { lead: "Public-data only.  " }),
      bullet("Nothing is hidden — \"How scoring works\" explains, in plain English, exactly what makes a lead strong.", { lead: "Transparent.  " }),
      bullet("It tells you not just who, but when to reach them and what to say.", { lead: "Actionable.  " }),

      h2("A few honest notes"),
      bullet("Premium and pipeline figures are illustrative estimates."),
      bullet("Wealth tiers are estimated from public records (property assessments, Census income, public-company insider status)."),
      bullet("The lapse-risk indicator is a guide only — it is not a credit decision and uses no credit data."),
      bullet("When an area or source is marked \"example\" or \"not yet covered,\" that is the system being honest about what it could and couldn't pull live — it never pretends."),
      bullet("Confidence levels (High / Medium) reflect how many public records confirm a lead — more confirming records means higher confidence. They are honest estimates, not guarantees."),

      new Paragraph({ spacing: { before: 280, after: 40 },
        border: { top: { color: LINE, size: 6, style: BorderStyle.SINGLE, space: 6 } },
        children: [ new TextRun({ text: "In one sentence: ", bold: true, color: NAVY, size: 21, font: FONT }),
          new TextRun({ text: "this finds your best prospects the moment their need appears, tells you why and what to say, and lets you prove every word.", italics: true, size: 21, color: INK, font: FONT }) ] }),
      muted("Prepared by SZL Holdings · public-data only · honest by design · © 2026", 17),
    ],
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync("/home/user/workspace/doc_build/David_Leads_Access_and_Tour.docx", buf);
  console.log("written", buf.length, "bytes");
});
