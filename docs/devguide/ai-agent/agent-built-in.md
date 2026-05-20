---
sidebar_position: 25
slug: agent-built-in
description: "Understand the platform's built-in Agents, their task boundaries, and how developers can reuse their design patterns."
---

# Understand Built-in Agents

Built-in Agents are ready-to-use Agents provided by the platform. End users can use them from the chat page for modeling, querying, data operations, and business analysis. Developers can also use them as reference designs for combining [ReActAgent](./create-react-agent), [DeepAgent](./create-deep-agent), [Skills](../skills/overview), file spaces, data model tools, service function tools, privacy protection, and role permissions.

This page focuses on how to choose the right built-in Agent and what design patterns developers can reuse.

## Choose by Task {#choose-built-in-agent-by-task}

| Task | Recommended Agent | Output |
| --- | --- | --- |
| You have business requirements but no existing tables | Requirement-based Model Generation and Maintenance | Data model creation or maintenance |
| You already have database tables or views | Database-based Model Generation and Maintenance | Data model creation or maintenance |
| You want to inspect table or view structures first | Database Table/View Schema Profile | Schema profile file |
| You already have a schema profile and want model configuration | Generate Model Configuration from Schema Profile | Model configuration submitted to the platform |
| You want to query, create, update, or delete business data | Data Operation/Query Agent | Daily data operations |
| You want to turn a business question into clear metric definitions | Data Metric Design | Metric definition and query requirements |
| You have clear query requirements and need data results | Data Retrieval Execution | Query result files |
| You want to turn an existing model into a reusable query Skill | Model-based Query Skill Development | Skill element installable in other Agents |
| You want to answer an open-ended business question | Business Data Insight Analysis | Analysis report |

## Data Operations and Query Agents {#data-operation-and-query}

This group works on existing data models and lets users process data through natural language. It includes two levels:

- `Data Operation/Query Agent`
- `Data Retrieval Execution`

`Data Operation/Query Agent` is for daily business actions such as query, create, update, and delete. `Data Retrieval Execution` is for structured query tasks where the target, fields, filters, and metrics are relatively clear.

Use `Data Operation/Query Agent` when the user wants to perform a business action, such as creating a customer, updating a status, or deleting a record. Use `Data Retrieval Execution` when the user already has a clear query goal and needs stable retrieval results.

This separation keeps daily operations simple while allowing structured data retrieval to stay stable enough for reuse by other Agents and [query Skills](../skills/query-skill-best-practices).

## Query Skill Development Agent {#query-skill-development-agent}

`Model-based Query Skill Development` is for developers. Use it when a data model already exists and you want to capture common queries, metric definitions, and TQL templates as a reusable Skill.

This Agent does not return a one-off query result. Its output is a Skill element that usually contains:

- `SKILL.md`: when to use the query Skill and which references to read.
- `references/data-model.md`: full field definitions, field types, enum values, null rules, and type risks.
- `references/query-template.md`: verified detail query, combined filter, aggregate, and TopN templates.

The Agent works by checking existing Skills, asking `Data Retrieval Execution` to generate and verify templates, writing only verified TQL templates, saving the Skill element into the current app's `skills` directory, and reading it back for final checks.

You can prompt it like this:

```text
Build a customer order query Skill based on models.sales.CustomerOrder.
Cover order detail queries, customer/status/time filters, order amount summaries, status distribution, and customer order amount TopN.
```

After the Skill is generated, install it in the target business assistant or data query Agent. Use the same configuration flow as other Skills: add the generated Skill to the target Agent's Skill list. The target Agent can then read the generated field definitions and query templates when answering related questions.

Use this Agent when repeated questions should become maintainable Skill content. If there is no model yet, use a modeling Agent first. If you only need a one-time data result, use `Data Retrieval Execution`.

Related docs:

- [Build Query Skills](../skills/query-skill-best-practices)
- [Use Skills in Agents](../skills/use-skill-in-agent)
- [Skill Best Practices](../skills/skill-best-practices)

## Reusable Design Patterns {#reusable-design-patterns}

Built-in Agents repeatedly use several platform capabilities:

| Platform capability | Typical role |
| --- | --- |
| [ReActAgent](./create-react-agent) | Handles bounded single-agent tasks |
| [DeepAgent](./create-deep-agent) | Coordinates multi-step workflows and sub-Agents |
| [Skills](../skills/overview) | Captures stable reusable professional methods |
| Data model tools | Read and write business data |
| Service function tools | Execute complex business actions |
| Tool exposure | Controls which candidate tools are visible to the model |
| Role permissions | Controls what the current user can actually execute |
| Privacy protection | Masks or hashes sensitive information when needed |

The most important lesson is not a particular prompt. It is the separation of responsibilities: use bounded scene Agents for clear tasks, use expert Agents for open-ended analysis, capture stable professional methods as Skills, and keep permissions separate from model-visible tool exposure.
