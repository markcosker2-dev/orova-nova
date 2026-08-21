# Evaluations — sales-intelligence

Per Anthropic's evaluation-driven guidance, three scenarios that test whether the
skill changes behavior on real tasks. There is no built-in runner; run these by
hand (or wire a harness) with the skill loaded vs. not, and score against
`expected_behavior`. These are the source of truth for whether the skill works —
update them as failure modes appear.

```json
[
  {
    "skills": ["sales-intelligence"],
    "query": "Write a cold email to the owner of Fusion Luxury Motors, an exotic car dealer in the LA area.",
    "expected_behavior": [
      "Email is <= 75 words, Hook-Value-Ask shape, single low-pressure ask",
      "Leads with a specific, plausible detail about THEIR dealership (not about OROVA)",
      "States the differentiator: every lead called/qualified in minutes, only talk to ready buyers",
      "Sells qualified conversations / revenue growth, NOT generic 'lead generation' or 'grow your business'",
      "No past-client claims, no spam-trigger words, signed 'Nova @ OROVA'"
    ]
  },
  {
    "skills": ["sales-intelligence"],
    "query": "A prospect replied to our cold call: 'Sounds expensive, and honestly we got burned by an agency before.' How do I respond?",
    "expected_behavior": [
      "Validates the concern first (does not argue or immediately pitch price)",
      "Reframes: most agencies hand over leads to chase (the part that burned them); OROVA qualifies every lead before it reaches them",
      "States actual pricing correctly ($4k / $5k) without offering a discount",
      "Ends with a forward secondary ask (e.g. offer a 15-minute comparison call), not silence",
      "Makes no past-client claims and no guaranteed-number promises"
    ]
  },
  {
    "skills": ["sales-intelligence"],
    "query": "QA this draft before it sends: 'Hi — OROVA is a top digital marketing agency and we guarantee we'll flood your dealership with 50+ leads this month, free trial available, act now! Our clients see huge ROI. — Team'",
    "expected_behavior": [
      "FAILS the QA gate and lists the specific violations",
      "Flags generic agency-speak ('digital marketing agency', 'flood with leads') vs. qualified-conversations positioning",
      "Flags guaranteed number on a deadline (breaks the promise ceiling)",
      "Flags spam triggers ('free', 'act now') and the past-client claim ('our clients see')",
      "Rewrites it on-brand: <=75 words, differentiator-led, no guarantees, correct signature"
    ]
  }
]
```

## Baseline note

Run each query with the skill OFF first and record what Claude does without it
(likely: generic agency copy, a specific-time CTA on the cold call, no QA
rejection). The skill's value is the delta. Re-run across Haiku / Sonnet / Opus —
Haiku may need the non-negotiables spelled out more; Opus should not over-explain.
