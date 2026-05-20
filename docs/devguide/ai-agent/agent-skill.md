---
sidebar_position: 12
slug: agent-skill
description: "Install reusable skill packages into Agents and choose how the Agent selects them at runtime."
---

# Install Skills for Agents

Skills are reusable domain capability packages. After a Skill is installed, an Agent can use its workflow, output standards, decision rules, and examples when handling matching user requests.

If you have not created a Skill yet, start with [Capture Reusable Domain Expertise](../skills/overview), [Create Standard Skills](../skills/create-skill), and [Design Stable and Reusable Skills](../skills/skill-best-practices).

## Manage Skills {#manage-skills}

Open the Agent editor and switch to the `Skills` tab. The platform supports three modes:

- **Intelligent mode**: the system selects suitable Skills based on the user request and Skill description. Use this for Agents that handle multiple task types.
- **Custom mode**: manually select the Skills this Agent can use. Use this for Agents with a clear and narrow capability boundary.
- **Disabled**: the Agent does not use Skills. Use this for simple Agents or when debugging the Agent's main prompt.

For the same configuration from the Skill perspective, see [Install Skills in Agents](../skills/use-skill-in-agent).

## Typical Use Cases {#typical-use-cases}

- **Customer management Skill**: customer follow-up workflow, tiering rules, communication templates, and next-step suggestions.
- **Data report Skill**: query templates, metric definitions, report structure, and export format.
- **Ticket handling Skill**: ticket classification, priority rules, routing process, and response format.

If one Skill will be reused by multiple Agents, keep its scope clear and avoid mixing it with one Agent's role prompt, tool configuration, or knowledge base content. See [Design Stable and Reusable Skills](../skills/skill-best-practices).
