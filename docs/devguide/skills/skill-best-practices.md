---
sidebar_position: 3
sidebar_label: Design Reliable Skills
slug: skill-best-practices
description: "Design, write, organize, validate, and iterate high-quality Skills for platform developers."
---

# Design Stable and Reusable Skills

A high-quality Skill is not a long document. It helps an Agent use the right professional method in the right scenario. It should have clear boundaries, be easy to select, easy to maintain, and map naturally to the platform's Skill creation, editing, attachment, and installation flows.

If you have not created a Skill yet, read [Create Standard Skills](./create-skill). If the Skill needs complex rules, templates, or examples, use [Manage Skill Attachments](./skill-attachments). After the Skill is ready, connect it to an Agent through [Install Skills in Agents](./use-skill-in-agent).

## What a Skill is {#what-is-skill}

A Skill is a reusable capability package for AI Agents. It is not an end-user manual and should not duplicate a knowledge base. It captures how to handle a domain, workflow, or task so the Agent knows what to do when that type of request appears.

An effective Skill usually provides four kinds of capability:

- **Specialized workflow**: steps to follow for a type of task.
- **Tool or file convention**: how to use a specific API, command, file format, template, or project structure.
- **Domain rules**: business concepts, decision rules, metrics, constraints, and common pitfalls.
- **Reusable resources**: attachment-based rules, templates, examples, checklists, or references.

The goal is not to make the Agent "know more background". The goal is to make it more stable, less error-prone, and less dependent on reasoning from scratch.

## Start from one repeatable task {#start-from-repeatable-task}

Do not start by building an "all-purpose assistant". Choose one frequent, stable, well-bounded task and capture it as a reusable capability. Then add rules, templates, and attachments as needed.

Ask:

1. What type of problem does this Skill solve?
2. Which Agents should use it?
3. When should an Agent use it?
4. What steps must be followed?
5. What should the output look like?
6. When should the Agent not use it?

When you can list a few typical user requests and explain how the Agent should handle them, move into the platform Skill creation flow.

## Keep one Skill focused on one problem type {#one-skill-one-problem}

Do not put unrelated capabilities into one Skill. A Skill should focus on one type of business problem so the Agent can decide when to use it and developers can maintain it over time.

Prefer:

- Customer Follow-up Skill
- Customer Churn Risk Analysis Skill
- Sales Weekly Report Skill

Avoid:

- Sales All-in-One Skill

If one topic has clearly different subflows, split them into separate Skills and let the Agent combine them when needed.

## Write descriptions that guide Agent selection {#description-should-guide-selection}

The Skill description is not only for humans. It also affects whether the Agent selects the Skill correctly. Describe the scenario, main capability, and boundary.

Weak description:

```text
For customer management.
```

Better description:

```text
Used by sales and support Agents to analyze customer follow-up status, determine customer priority, and generate next-step communication suggestions. It does not directly modify customer records or promise deal outcomes.
```

A good description includes:

- Target object.
- Main capability.
- Boundary.

Descriptions are especially important when the Agent uses intelligent Skill selection. Name and description are configured when you [Create Standard Skills](./create-skill).

## Define capability scope and boundaries {#define-capability-scope}

Scope tells the Agent what the Skill can do and what it must not do.

Make clear:

- What it can do.
- What it cannot do.
- Which objects it applies to.
- Which scenarios are out of scope.
- Whether missing information should trigger a clarification, a default, or a stop.

Clear boundaries reduce accidental misuse.

## Use execution steps to capture the workflow {#write-execution-steps}

Execution steps are the core of a Skill. They turn team experience into a process the Agent can follow.

Use ordered steps instead of long prose:

```markdown
## Execution Steps

1. Confirm the object the user wants to handle.
2. Check whether the required information is available.
3. Apply the fixed rules or workflow.
4. Return the result with evidence and limitations.
```

If a step needs tools or data, write the business action. Tool exposure belongs to Agent capability configuration. See [Expose tool functions to the model as needed](../ai-agent/agent-tool-management).

## Stabilize results with an output format {#stabilize-output-format}

Output formats reduce answer drift. For reports, reviews, analysis conclusions, and operational suggestions, define a stable structure.

Recommended patterns:

- Fixed headings.
- Table columns.
- Bullet lists.
- Clear conclusion, evidence, and suggestions.

Example:

```markdown
### Conclusion

### Key Evidence

### Suggested Actions

### Information Requiring Human Review
```

If downstream systems depend on structured results, combine this with [Agent input and output settings](../ai-agent/agent-input-output).

## Add constraints to reduce misuse {#add-constraints}

Constraints tell the Agent what must not happen.

Common constraints:

- Do not invent missing data.
- Explain missing information when data is insufficient.
- Do not promise prices, contract terms, or legal conclusions.
- Do not bypass role permissions for high-risk actions.
- Do not output irrelevant internal reasoning.

High-risk Skills should also be paired with tool exposure and role permissions. Tool exposure affects what the model can see; role permissions determine what the user can actually execute.

## Split complex knowledge into attachments {#split-complex-knowledge-into-attachments}

The main prompt should not be too long. Put complex rules, glossaries, templates, and examples into attachments, and explain each attachment's purpose in the main prompt.

This keeps the main workflow clear and lets business rules be maintained independently. If a rule must be followed every time, keep it in the main prompt. If it is a reference for detailed judgment, put it in an attachment. See [Manage Skill Attachments](./skill-attachments).

## Do not copy knowledge base content into Skills {#do-not-copy-knowledge-base}

Skills are for "how to do it". Knowledge bases are for facts and documents. Do not copy product manuals, policies, FAQs, or historical records into a Skill.

Recommended division:

- **Skill**: how to judge, process, and output.
- **Knowledge base**: product documents, policies, FAQs, historical materials.
- **Tools**: query, write, call services, operate pages.

If an Agent needs to answer based on documents or retrieve facts, use [knowledge bases for Agents](../ai-agent/agent-knowledge-base).

## Avoid duplicating the Agent system prompt {#avoid-overlap-with-agent-prompts}

The Agent system prompt defines the current Agent's role, goal, and overall behavior. A Skill provides reusable professional capability and execution standards.

Avoid writing this in a Skill:

```text
You are a sales manager assistant responsible for all sales management work.
```

Prefer:

```text
When analyzing customer follow-up status, use this Skill's tiering rules and output format to generate follow-up suggestions.
```

If content only applies to one Agent, keep it in that Agent's system prompt. See [Create a ReActAgent](../ai-agent/create-react-agent).

## Validate before reuse {#validate-before-reuse}

When a Skill is reused by multiple Agents, its impact grows. Validate it in one test Agent before rolling it out more broadly.

Check:

- Whether the usage scenario is accurate.
- Whether the output format is stable.
- Whether it conflicts with the Agent system prompt.
- Whether it needs extra tools or knowledge bases.
- Whether high-risk actions require permissions or human review.

Use realistic tasks for validation. Asking "is this Skill good?" is less useful than testing the Skill with real user requests.

## Iterate from concrete failures {#iterate-by-failure}

Skills do not need to be perfect on the first version. After real use, record failure modes and update the right part.

Common iteration paths:

- Wrong trigger: rewrite name and description.
- Confusing process: convert prose into numbered steps.
- Unstable output: add a fixed output structure.
- Repeated mistakes: turn implicit rules into explicit constraints.
- Too much content: move detailed rules, templates, and examples into attachments.
- Missing factual basis: connect a knowledge base or tool instead of stuffing documents into the Skill.

Each iteration should fix a specific problem, not simply add more content.
