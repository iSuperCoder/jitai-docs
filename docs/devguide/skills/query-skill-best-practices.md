---
sidebar_position: 6
sidebar_label: Build Query Skills
slug: query-skill-best-practices
description: "Build reusable query Skills around data models, using built-in Agents to generate, verify, and submit query templates."
---

# Build Query Skills

Query Skills turn query conditions, metric definitions, field explanations, and TQL templates for a data scenario into reusable Agent capability. They are not one-off query results. They help other Agents identify the business object, reuse query templates, and explain results consistently.

The best practice is not to put many TQL examples into this guide. The important parts are:

- Keep the Skill boundary clear and focused on one primary data scenario.
- Explain field meanings, types, enums, null values, and relationships completely.
- Design template coverage across both detail queries and aggregate queries.
- Execute and verify templates before submission.
- Keep final Skill files reusable, without process logs or failed candidates.

## Fast Start: Use the Built-in Agent {#start-with-built-in-agent}

If your app already has a data model, start with the built-in [`Model-based Query Skill Development` Agent](../ai-agent/agent-built-in#query-skill-development-agent). It organizes the workflow around the specified model, delegates TQL template generation and validation to [`Data Retrieval Execution`](../ai-agent/agent-built-in#data-operation-and-query), then submits the field definitions, query templates, and Skill instructions as a Skill element.

You can prompt it like this:

```text
Build a query Skill for <business object> queries and statistics based on the models.xxxx model.
Cover detail queries by key fields, status/type/time filters, aggregate statistics, and TopN rankings.
```

After the built-in Agent creates the Skill, install it in the target business assistant, data query Agent, or role-specific Agent. The target Agent can then read the generated field definitions and query templates and reuse verified TQL.

If you only need to add or verify a batch of query templates instead of creating a complete Skill, use `Data Retrieval Execution` directly.

## Focus one Skill on one data scenario {#one-skill-one-data-scenario}

Keep the granularity manageable. Start from one primary data model, and let one Skill focus on one clear business object or data scenario.

Benefits:

- The Agent can decide more reliably whether the Skill applies.
- Query templates can be organized around one field set.
- Field definitions, metric definitions, and null rules are easier to maintain.

If a scenario spans multiple models, identify the primary model first. Related models should only supplement filters, display fields, or metric definitions. If models have independent questions, fields, and metrics, split them into separate Skills.

## Classify query requirements {#query-requirement-types}

Around one data model, query requirements usually fall into two categories:

- **Detail queries**: filter by model fields and return detailed records.
- **Aggregate queries**: filter, group, or calculate by model fields and return counts, distinct counts, summaries, distributions, trends, or rankings.

These categories are coverage dimensions, not template counts. A model with many fields and rich business meaning may need multiple templates in each category. A smaller model may need fewer. Combine field semantics with query categories instead of creating only one template per category.

## Generate and Verify Query Templates with Data Retrieval Execution {#generate-and-verify-query-templates}

Query templates reduce the Agent's need to build queries on the fly. A template should be executable after parameter replacement. It should not merely say "supports status queries" or "supports monthly statistics."

Recommended workflow:

1. Start template generation with the primary model fullName.
2. Let `Data Retrieval Execution` read the model details and understand fields and relationships.
3. Design candidate templates for detail and aggregate queries.
4. Execute and verify every candidate template.
5. Keep only verified templates in the final template set.
6. Keep failed candidates, repair attempts, and unverifiable cases in the generation report or review notes, not in final Skill resources.

The task sent to `Data Retrieval Execution` should focus on business goals and deliverables. It does not need to repeat TQL syntax. TQL syntax, function usage, execution style, and failure repair belong to its query-building capability.

Example task:

```text
Use the models.xxxx model to generate reusable query templates for the <business object> scenario.
Cover detail queries, combined filters, aggregate statistics, distribution analysis, TopN rankings, and null-value analysis.
Execute and verify every candidate template.
Generate one Markdown template file directly and return its path.
```

## Core file structure {#query-skill-files}

Recommended structure:

```text
skill-name/
├── SKILL.md
└── references/
    ├── data-model.md
    └── query-template.md
```

File responsibilities:

| File | Responsibility | Should not contain |
| --- | --- | --- |
| `SKILL.md` | Trigger scenario, goal, reference navigation, analysis flow, constraints | Full field lists, lots of TQL, generation process |
| `references/data-model.md` | Fields, types, business meanings, enums, null rules, relationships, type risks | Query templates, one-off query results |
| `references/query-template.md` | Reusable parameterized query templates, template directory, execution syntax, metric definitions | Validation status, failed candidates, repair process |

### What to write in SKILL.md {#query-skill-main-file}

`SKILL.md` helps the Agent decide when to use the Skill. Keep it short and stable. Include:

- Business object and scope.
- When to read `references/data-model.md`.
- When to read `references/query-template.md`.
- The analysis flow for using the Skill.
- Constraints such as not inventing fields, not mixing metric definitions, and not writing data.

The `description` should be business-specific, so another Agent can understand what this Skill can answer by reading metadata alone. Example:

```markdown
description: Use this Skill to query customer order details by customer, order number, order status, and order time, and to calculate order counts, order amount summaries, status distributions, and customer order TopN rankings.
```

Avoid abstract descriptions such as "for model querying" or "supports detail and aggregate queries."

### How to write data-model.md {#data-model-file}

`references/data-model.md` helps the Agent understand fields and metric definitions correctly. Include at least:

| Content | Description |
| --- | --- |
| Model information | Model fullName, title, business object |
| Full field list | Field name, title, type, business meaning, query use, notes |
| Key field semantics | Subject identifier, name, status, type, time, amount, quantity, related object |
| Enums and values | Valid values and meanings for status, type, stage, round, and similar fields |
| Null rules | Which fields may be empty and whether they are counted or filtered |
| Type risks | Text-based numbers, date strings, formula fields, fields that cannot be aggregated directly |
| Relationships | Related models and how related fields may be used in this Skill |

The field table should cover every field in the model. If the business meaning is unclear, write "uncertain" instead of omitting the field.

### How to write query-template.md {#query-template-file}

`references/query-template.md` is the core reference file for a query Skill. Suggested structure:

```markdown
# <Business Object> Query Templates

## Template Directory

| ID | Category | Template | Covered fields | Applicable questions |
| --- | --- | --- | --- | --- |

## Execution Syntax

runFunction('models.services.ModelSvc', 'aiSelect', ['<TQL code string>', 0, 50], True, '<business query title>')

## 1. Detail Queries

### 1.1 <Template title>

Applicable questions:
Covered fields:
Parameters:
Query definition:
TQL:

## 2. Aggregate Queries

### 2.1 <Template title>

Applicable questions:
Covered fields:
Parameters:
Metric definition:
TQL:
```

The final template content should only contain reusable content. Final submitted templates are assumed to be verified. Do not write validation status, validation records, or validation process into each template.

## Review template coverage {#template-coverage}

For detail queries, check coverage for:

- Exact query by primary identifier, such as ID, code, or bill number.
- Fuzzy query by name or title.
- Status, type, or category filters.
- Time range filters.
- Related object filters.
- Numeric range filters.
- Multi-field combined filters.
- Pagination or `Limit` for detail results.

For aggregate queries, check coverage for:

- Record count.
- Distinct count.
- Status, type, or category distribution.
- Time trends.
- TopN rankings.
- Sum, average, max, and min for numeric fields.
- Empty and non-empty statistics.

If no suitable field exists, state the reason instead of forcing a template. Templates involving type conversion, related models, or complex metrics must be executed and verified by `Data Retrieval Execution` before entering the final template set.

## Delivery gates {#delivery-gates}

Before submitting the Skill, confirm:

- The Skill title and `description` are concrete and business-specific.
- One Skill focuses on one primary business object or model.
- `SKILL.md` does not contain full field lists or lots of TQL.
- `data-model.md` covers the complete field list and key metric definitions.
- `query-template.md` starts with a template directory and unified execution syntax.
- Templates are organized by detail and aggregate queries, not scattered by natural-language phrasing.
- Every template has parameters, covered fields, and a query or metric definition.
- Detail templates include pagination or `Limit`.
- Aggregate templates explain the metric definition.
- Templates in the final set have been executed and verified.
- Final template content does not contain validation status, failed candidates, repair process, or one-off query results.
- No unrelated `README.md`, `CHANGELOG.md`, or process report is generated.

## Checklist {#query-skill-checklist}

Use this checklist when building or reviewing a query Skill:

- Can a user understand the business problem from `description` alone?
- Can the Agent decide from `SKILL.md` when to read field definitions and query templates?
- Do field definitions prevent invented fields, type misuse, or enum confusion?
- Do query templates cover the main fields and main question types?
- Do aggregate templates clearly state what is counted, grouped, and sorted?
- Are templates concrete enough to execute after parameter replacement?
- Have templates been executed and verified by the built-in Agent?
- Do final Skill files contain only reusable content, not the generation process?
