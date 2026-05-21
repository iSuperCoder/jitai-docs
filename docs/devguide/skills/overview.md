---
sidebar_position: 1
sidebar_label: Capture Expertise
slug: overview
description: "Capture reusable business experience, workflow rules, and output requirements as Skills that multiple AI Agents can share."
---

# Capture Reusable Domain Expertise

Skills are reusable capability packages for AI Agents. Developers can capture domain experience, workflows, output standards, decision rules, and examples as Skills, then install them into one or more Agents.

Agents handle user-facing tasks. Skills provide reusable professional methods. When multiple Agents need to follow the same rules, process, or output format, put that reusable capability in a Skill instead of repeating it in every Agent prompt.

## What belongs in a Skill {#what-should-be-a-skill}

A capability is a good Skill candidate when it needs to be reused across Agents or maintained over time.

- **Fixed business workflows**: customer follow-up, contract review, ticket routing, report preparation.
- **Stable output standards**: daily reports, weekly reports, review comments, risk lists, action suggestions.
- **Domain decision rules**: customer tiers, lead priority, defect severity, approval risk levels.
- **Team operating practices**: onboarding workflows, presales answer guidelines, support response patterns.
- **Reusable examples and templates**: email templates, proposal templates, reply templates, checklists.

If a prompt only defines one Agent's identity or task goal, keep it in that Agent's own configuration. Extract it into a Skill only when it can become a reusable professional capability.

## How Skills differ from Agents, knowledge bases, and tools {#skill-agent-knowledge-tool}

| Capability | Main purpose | Typical content |
| --- | --- | --- |
| **AI Agent** | Receives user tasks, plans steps, calls tools, and returns results | Role, task goal, available tools, input/output settings |
| **Skill** | Adds reusable professional methods and execution standards | Domain workflows, output formats, rule boundaries, examples |
| **Knowledge base** | Provides searchable factual materials and business documents | Product manuals, policies, FAQs, historical knowledge |
| **Tool** | Lets the Agent perform concrete actions | Query data, update records, call services, operate pages |

A typical setup is: the Agent receives the user request, the Skill defines how to handle it, the knowledge base provides factual references, and tools perform actual actions. If you are new to Agents, start with [AI Agent overview](../ai-agent/overview).

## Reuse one Skill across multiple Agents {#reuse-skill-across-agents}

The value of a Skill is reuse. For example, a "Customer Follow-up Skill" can be installed in a sales assistant, a support assistant, and a manager analysis assistant. These Agents have different goals, but they can share the same customer tiering rules, follow-up cadence, messaging templates, and output format.

This has three benefits:

- **Consistent behavior**: multiple Agents follow the same business rules.
- **Centralized maintenance**: update the Skill once when the rules change.
- **Flexible composition**: one Agent can install multiple Skills to build combined capabilities.

## Start from one repeatable task {#start-from-repeatable-task}

When designing a Skill, do not start by writing a long prompt. Start from one frequent, stable, reusable task.

Answer these questions first:

1. What type of problem does this Skill solve?
2. Which Agents should use it?
3. When should an Agent use it?
4. What steps must the Agent follow?
5. What should the output look like?
6. When should the Agent not use it?

After this concept is clear, continue to [Create Standard Skills](./create-skill) to create the Skill element in the platform.
