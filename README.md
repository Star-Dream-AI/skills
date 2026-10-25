> **Note:** This repository is an independent, community-maintained collection of Agent Skills by [Star Dream AI](https://github.com/Star-Dream-AI). For information about the open format, visit [agentskills.io](https://agentskills.io/).

# Star Dream AI Skills

**An open-source collection of Agent Skills.**

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![Agent Skills](https://img.shields.io/badge/Standard-Agent%20Skills-blueviolet)](https://agentskills.io/)
[![Contributions Welcome](https://img.shields.io/badge/Contributions-Welcome-brightgreen.svg)](https://github.com/Star-Dream-AI/skills/issues)

Agent Skills are reusable sets of instructions, scripts, and supporting resources that help compatible AI agents perform specialized tasks. A skill lives in its own folder and includes a `SKILL.md` file describing what it does and when an agent should use it.

This repository is a home for Skills created and maintained by **Star Dream AI** and community contributors. Our goal is to make useful, reusable workflows easy to discover, inspect, improve, and share.

## About This Repository

Skills in this collection may cover different tasks and disciplines. Each is intended to be self-contained, with clear instructions and any resources needed to perform its specific workflow.

**Status:** This repository is being set up. Skills will be added over time. No particular skill is promised or available until it appears in the `skills/` directory.

## Browse Skills

Once skills have been published, you will find them in the `skills/` directory. Each skill will have its own `SKILL.md` and, where needed, scripts, examples, or reference materials.

> The `skills/` directory is planned and may not exist yet.

## Using Skills

Support depends on the agent or application you use. Consult that platform's documentation for its supported skill installation locations and requirements.

### Skills CLI

After skills are published, the community [Skills CLI](https://skills.sh/) can help you discover and install individual skills from this repository:

```bash
# View available skills
npx skills add Star-Dream-AI/skills --list

# Select skills interactively
npx skills add Star-Dream-AI/skills

# Install a specific skill
npx skills add Star-Dream-AI/skills --skill <skill-name>
```

These commands are examples for **future published skills**; they will not install an unpublished skill. The CLI is maintained by a third party and may require Node.js. Always review a skill's instructions, scripts, and permissions before running it.

### Manual Installation

For agents that support the Agent Skills format, you can also copy an individual skill folder into the skills directory supported by that agent. Installation locations vary by platform.

## Repository Structure

As the collection grows, it will follow this general layout:

```text
skills/
├── README.md
├── LICENSE
└── skills/
    └── example-skill/
        ├── SKILL.md
        ├── scripts/       # Optional
        ├── references/    # Optional
        └── assets/        # Optional
```

Each skill is independent. The example folder above illustrates the intended structure; **it is not an existing skill**.

## Create a Skill

At minimum, a skill is a folder containing a `SKILL.md` file with YAML frontmatter:

```markdown
---
name: example-skill
description: Describe what this skill does and when an agent should use it.
---

# Example Skill

Add the instructions, workflow, and examples here.
```

For more details, consult the [Agent Skills specification](https://agentskills.io/specification).

## Contributing

Contributions, suggestions, bug reports, and improvements are welcome.

- **Suggest a skill:** Open an [issue](https://github.com/Star-Dream-AI/skills/issues) describing the problem and intended users.
- **Improve an existing skill:** Open a [pull request](https://github.com/Star-Dream-AI/skills/pulls) with a concise explanation and, where possible, tests or examples.
- **Submit a new skill:** Add a folder under `skills/` with a valid `SKILL.md`, document any dependencies, and include example usage.

Please do not commit API keys, passwords, private personal information, or third-party material without permission. Keep skills understandable, testable, and appropriately scoped.

## Disclaimer

Skills may generate incorrect results or execute scripts that affect local files or connected services. Review the contents of each skill, confirm its dependencies and permissions, and test it in a suitable environment before relying on it for important work.

This collection is independent and is not affiliated with or endorsed by Anthropic, OpenAI, or any other AI platform provider.

## License

This repository is licensed under the [Apache License 2.0](LICENSE), unless otherwise noted for individual files or third-party dependencies.

## Community

- [GitHub Organization](https://github.com/Star-Dream-AI)
- [Issues & Suggestions](https://github.com/Star-Dream-AI/skills/issues)
- [Pull Requests](https://github.com/Star-Dream-AI/skills/pulls)
- [Telegram Group](https://t.me/zcofo)

---

*Made to share. Built to improve.*
