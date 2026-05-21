---
sidebar_position: 5
sidebar_label: Install Skills in Agents
slug: use-skill-in-agent
description: "Install existing Skills into AI Agents and choose intelligent mode, custom mode, or disabled mode based on the Agent's task scope."
---

# Install Skills in Agents

A Skill only takes effect after it is installed into an Agent. Developers can choose automatic matching, manual selection, or disabling based on the Agent's task scope.

## Why Agents need Skills {#why-agent-needs-skills}

The Agent's main configuration describes who the Agent is, what it should accomplish, and what tools it can use. Skills carry reusable domain capability.

Examples:

- A sales Agent installs a Customer Follow-up Skill.
- A data analysis Agent installs a Business Report Skill.
- An operations Agent installs a Ticket Handling Skill.
- A legal Agent installs a Contract Risk Review Skill.

## Open Skills configuration in the Agent editor {#open-skills-tab-in-agent}

Open the target Agent editor and go to the `Skills` tab. The platform provides three usage modes:

- **Intelligent mode**
- **Custom mode**
- **Disabled**

For entry points and UI details, see the AI Agent guide [Install Skills for Agents](../ai-agent/agent-skill#manage-skills).

## Intelligent mode fits multi-scenario Agents {#smart-mode}

Use intelligent mode when one Agent handles multiple task types or when you want the platform to select Skills based on context.

Good fits:

- An enterprise assistant that handles support, sales, and data queries.
- An Agent with multiple domain Skills installed.
- User requests vary and capability selection should be semantic.

In intelligent mode, Skill names and descriptions must be clear enough for the Agent to choose correctly. See [Create Standard Skills](./create-skill).

## Custom mode fits narrow-scope Agents {#custom-mode}

Use custom mode when the Agent has a clear task scope and you want to manually choose the Skills it can use.

Good fits:

- A support Agent only installs support response and ticket Skills.
- A contract review Agent only installs contract risk review Skills.
- A report Agent only installs data metric and report output Skills.

Custom mode reduces irrelevant Skill interference and helps the Agent stay focused.

## When to disable Skills {#disable-skills}

Disable Skills when:

- The Agent task is simple and does not need extra domain capability.
- You are debugging the Agent system prompt and want to remove Skill influence.
- The Agent must rely strictly on tools or knowledge bases.
- A Skill has not been validated and should not affect production behavior yet.

Disabling Skills does not delete Skill elements. It only prevents the current Agent from using them.

## Validate with real tasks after installation {#verify-with-real-tasks}

After installing a Skill, test it with realistic business tasks instead of only simple questions.

Check:

- Whether the Agent uses the Skill in the right scenario.
- Whether the output follows the Skill's format.
- Whether the Agent respects the Skill's boundaries and constraints.
- Whether multiple Skills conflict with each other.

If results are unstable, first check whether the Skill's scenario, scope, and execution steps are clear. For design principles, see [Design Reliable Skills](./skill-best-practices).
