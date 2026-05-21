---
sidebar_position: 4
sidebar_label: Manage Attachments
slug: skill-attachments
description: "Use Skill attachments to maintain complex rules, glossaries, templates, examples, and checklists while keeping the main prompt clear."
---

# Manage Skill Attachments

When a Skill becomes long, do not put every rule, template, and example into the main prompt. Move long-term supporting materials into attachments so the main prompt remains clear and attachments carry the details.

## What belongs in attachments {#what-belongs-in-attachments}

Good attachment content is usually long, independently maintained, not always read in full, but still important to the Agent's judgment or output.

Common attachment types:

- **Business rules**: customer tier rules, ticket priority rules, review checklists.
- **Glossaries**: industry terms, internal abbreviations, product names, field meanings.
- **Output templates**: email templates, report templates, processing forms, reply formats.
- **Example sets**: good replies, bad examples, typical cases.
- **Checklists**: release checks, contract review items, approval prechecks.

The main prompt tells the Agent when to use the Skill and which steps to follow. Attachments provide the detailed rules and examples.

## Split business rules into attachments {#split-business-rules}

If business rules are longer than one screen, put them in attachments. Name each attachment by purpose, for example:

- `customer-level-rules.md`
- `ticket-priority-rules.md`
- `contract-risk-checklist.md`

Keep only the rule entry in the main prompt:

```markdown
When tiering customers, refer to `customer-level-rules.md`.
```

This lets you update detailed rules without changing the main Skill flow.

## Maintain glossaries and templates {#maintain-glossary-and-templates}

Glossaries help the Agent use terms consistently. Templates stabilize output format.

Use tables for glossaries:

```markdown
| Term | Meaning | Usage |
| --- | --- | --- |
| MQL | Marketing qualified lead | Marketing-side qualification only |
| SQL | Sales qualified lead | Sales has confirmed demand and follow-up value |
```

Use placeholders in templates:

```markdown
## Customer Follow-up Suggestion Template

- Customer name:
- Current stage:
- Main risk:
- Next action:
- Information requiring human review:
```

## Use example files as quality references {#use-examples-as-quality-reference}

For Skills involving judgment, writing, or review, examples are important. They show the Agent what a good result looks like and reduce style drift.

An example file can include:

- Typical input.
- Recommended output.
- Why the output is recommended.

If you include negative examples, mark them clearly as "do not output this way" to avoid confusion.

## Split responsibilities between the main prompt and attachments {#main-content-vs-attachments}

Use this principle:

- **Main prompt**: scenario, capability scope, execution steps, output structure, key constraints.
- **Attachments**: detailed rules, long templates, glossaries, cases, checklists.

If a rule must be followed every time, include it in the main prompt. If it is a reference for detailed judgment, put it in an attachment.

## Keep attachments discoverable {#keep-attachments-discoverable}

When there are many attachments, add an attachment guide to the main prompt:

```markdown
## Attachments

- `customer-level-rules.md`: customer tiering rules.
- `follow-up-message-templates.md`: follow-up message templates for different stages.
- `risk-examples.md`: common risk cases and recommended handling.
```

This helps both Agents and future maintainers understand what each file is for.
