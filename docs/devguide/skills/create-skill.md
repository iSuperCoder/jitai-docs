---
sidebar_position: 2
sidebar_label: Create Standard Skills
slug: create-skill
description: "Create a standard Skill in the IDE, fill in its name and description, and open the Skill editor to maintain reusable capability content."
---

# Create Standard Skills

Standard Skill is the platform's basic Skill type. It is suitable for capturing reusable business processes, domain rules, output formats, and example templates. After creation, developers can maintain the content in the Skill editor and install the Skill into Agents.

## Create from the IDE Skills entry {#create-from-skills-entry}

Open the IDE and click `Skills` in the left navigation. If the current application does not have any Skills yet, use the add entry at the bottom of the resource panel.

Choose `Standard Skill`, fill in the basic information, and save. After saving, the Skill appears in the Skills list. Click it to open the editor.

## Use the name to describe the reusable capability {#name-the-reusable-capability}

The name should help both developers and Agents quickly understand what the Skill is for. A useful pattern is "domain + capability".

Recommended examples:

- `Customer Follow-up Strategy Skill`
- `Sales Weekly Report Skill`
- `Contract Risk Review Skill`
- `Ticket Routing Skill`

Avoid overly broad names such as `Business Skill`, `General Assistant Skill`, or `Smart Processing Skill`. These names do not communicate clear capability boundaries and make later selection and maintenance harder.

## Use the description to define scope and boundaries {#describe-scope-and-boundary}

The description should not simply repeat the name. It should explain when the Skill should be used and when it should not.

A clear description usually includes:

- **Target object**: customers, contracts, tickets, reports, or another business object.
- **Main capability**: judge, generate, review, classify, summarize, or suggest.
- **Boundary**: provides suggestions only, does not make final decisions, handles only a specific data type, or excludes certain scenarios.

Example:

```text
Used by sales and support Agents for customer follow-up scenarios. This Skill provides customer tiering, follow-up cadence, communication templates, and next-step suggestions. It does not directly modify customer records.
```

## Open the Skill editor after saving {#open-skill-editor-after-save}

After saving, the IDE opens the Skill editor. The editor has two main areas:

- **Basic information**: maintain the Skill name and description.
- **Prompt and attachments**: write the main Skill prompt and maintain complex rules, templates, and examples.

After creating the Skill, complete the main prompt first, then add attachments when needed. For design and writing principles, see [Design Reliable Skills](./skill-best-practices).

## Install the Skill into an Agent after creation {#install-skill-after-create}

Creating a Skill does not automatically affect any Agent. Open the Agent editor and configure it on the `Skills` tab. For details, see [Install Skills in Agents](./use-skill-in-agent), or the AI Agent guide [Install Skills for Agents](../ai-agent/agent-skill).
