# Authoring a progressive explanation (sales) installation

Read this when a business package installs `progressive_explanation_skill` and
you are creating it, filling it in, or changing it after a diagnosis.

This file holds only the judgment the platform cannot check for you. Field
names, required properties and enums come from `design_get_schema`; the
mechanical writing rules come back from the preflight as
`configuration_review`, described at the end. Do not restate either here.

## What the skill is and is not

It talks. `capability_bindings` is empty: it never registers, orders, books or
hands off. Every write belongs to another installed task that declares the
capability and holds the authorization. A design that has this skill "complete
the booking" is wrong no matter how the wording reads.

Four things stay separate, and one never implies another: the customer's
business goal, what has been explained, the customer's own choice to start, and
a real operation receipt. Most defects in this skill are two of them collapsed
into one.

## The six configuration blocks

Only `units` is required. Each optional block changes the shape of the
conversation, so add one because the business needs it, not to fill the form.

- `units` — what gets explained, cut by the questions customers actually ask.
- `discovery_topics` — the few things to learn before recommending. Omit it and
  the skill explains directly, which is right when there is nothing to choose
  between.
- `solution_tracks` — when the same product serves several customer goals and
  the relevant explanation differs. One track is a sign this block is not
  needed.
- `objection_handlers` — objections that may interrupt at any point.
- `conversion_checkpoint` — how the conversation closes.
- `cadence` — follow-ups when the customer stops replying. **Not configuring it
  means no automatic follow-up exists at all.** Never tell a user silence will
  be followed up unless this block is present.

## Sorting what the user tells you

Requirement gathering for this skill is mostly routing: the user describes
their business in one flow of sentences, and each sentence belongs to exactly
one asset. Ask them to talk through a real customer conversation from first
message to close, then place each sentence:

| What they say | Where it goes | The test |
| --- | --- | --- |
| "客户会问 X，我们要让他明白 Y" | `units[]` — `customer_question` + `must_convey` | Y is a fact the customer could repeat to a colleague |
| "得先知道 X 才能推荐" | `discovery_topics[]` | Not knowing X actually changes what you would explain |
| "做 A 的客户和做 B 的客户，要讲的不一样" | `solution_tracks[]` | Two tracks genuinely diverge; one track means skip the block |
| "客户会拿 X 来挡我们" | `objection_handlers[]` | It interrupts at any point rather than being a topic to cover |
| "讲到什么程度可以邀请 / 要拿到什么" | `conversion_checkpoint` | See the next section for which mode |
| "永远不能说 X" / "没核实不能承诺 X" | business package `policies[]`, cited by `prohibited_claim_refs` | It constrains every unit, not just one |
| "这句话要这么说" — tone, phrasing, a fixed sentence | reply template item | Change the wording and the meaning is unchanged |
| "要记住 X，后面还用得上" | a declared Fact, listed in `collect_fact_refs` | It has to survive to a later turn |
| "然后帮客户下单 / 预约 / 转人工" | another installed task's capability + `journey_handoffs` | It changes something outside the conversation |
| Prices, quotas, rules, entitlements | `must_convey`, or bound knowledge when it changes often | Someone will ask "where is this number maintained?" |

Two disciplines while sorting:

**One sentence, one home.** The same rule restated as a policy, inside a unit's
points, and again in a reply item drifts apart within weeks — and the reply
item is the copy that will be wrong. When a number lives in the wording, a
price change means two edits and one of them gets missed.

**Say it customer-side.** A point written as "客户明确想开始时，提供入口" is an
instruction to the model, not something the customer understands. Rewrite it as
what the customer learns: "注册入口是公开的，不需要先留联系方式". If it reads
like a rule for whoever maintains the asset, it belongs in a policy; if it
reads like advice from us, it belongs in `selection_guidance`.

## Choosing how it closes

`conversion_checkpoint.mode` decides the whole ending, and organizations
consistently pick the wrong one when it is presented as an enum:

- **`collect_required_fact`** — the position needs one fact to act on (a city, a
  time, a contact). Explain, then ask for it. `after_unit_keys` should normally
  list every unit: asking for data before the customer heard the essentials is
  what makes this feel like a form.
- **`explicit_opt_in`** — the customer must choose to start (a trial, a signup,
  a demo). Explain, then *invite*, and only a real choice counts. Here
  `after_unit_keys` should list only the units that must precede an invitation;
  listing all of them means the invitation never fires.

Ask the user which one their business is, in their words: "do you need a piece
of information from them, or do you need them to say yes?"

The invitation is not consent. Delivering every unit is not consent. "好的" is
not consent. Only the fact named by `fact_key` records it, and that fact must
also appear in some unit's `collect_fact_refs` or nothing is allowed to write
it.

## Where the handover is declared

A sales conversation ends by handing over to another task — booking, human
handoff, activation. That target is a property of **this position**, not of the
reusable skill, and it is declared on the installation:

```json
"journey_handoffs": [
  {"to_task_key": "appointment_booking_task", "to_state_key": "appointment_collection"}
]
```

Assembly derives the cross-task edges from it and validates them against the
tasks this package installs. Two consequences worth stating to the user:

- Do not write the edges into the organization's task copy. Refreshing that
  copy from its platform source silently drops them, and the symptom is an
  agent that promises to transfer and then does nothing.
- `conversion_checkpoint.known_fact_next_step` is wording only. If the sentence
  says a task takes over, the corresponding `journey_handoffs` entry has to
  exist, and that task has to be installed and enabled.

## Two runtime boundaries that produce silence

Both have already caused live conversations to receive no reply at all.

**A question may not target a fact that is already collected.** Runtime rejects
a collection-purpose `pending_question` whose fact is known. So when the
business rule is "ask for the industry if we still do not know it", write the
negative condition first — "if the industry is already recorded, use it and do
not ask again; only when it is still missing, ask" — and never write an
unconditional 必须 that a condition is supposed to gate. A strong instruction
buried behind a condition wins over the condition.

**Explanation progress must be recorded or the close never happens.**
`after_unit_keys` is evaluated against the progress fact. If a unit is
delivered but not recorded, the checkpoint can never be satisfied and the
conversation simply continues forever. This is not visible in any preflight:
verify it on a real conversation by comparing units actually delivered against
progress records.

## What the preflight tells you

`design_prepare_draft_bundle_save` and `design_prepare_business_publish` both
return a `release_preview` that carries `configuration_review`: the content
review of every installation's configuration, keyed by task key, each finding
naming its `rule`, `level`, `path` and the offending text.

`level: "error"` means the writing contradicts a rule the contract states in
its own field descriptions — for example an explanation point written as our
advice or as an internal caveat instead of a fact the customer can repeat, a
closing line that previews the agenda, or a checkpoint fact no unit is allowed
to collect. Show those to the user and fix them before asking for
confirmation; they are not style preferences.

The review never blocks the closure by itself: `status`, `errors` and
`warnings` remain the structural contract's answer. A package can be `ready`
and still be written badly.
