"""
Skills Platform — Phase 6
Markdown-based prompt extensions that inject domain knowledge into agent system prompts.
Inspired by OpenClaw's src/agents/skills/ (simplified from bundled/managed/workspace to DB-stored).

Skills are stored in MongoDB and injected into the system prompt before each agent turn.
Each skill has: id, name, content (markdown), and can be assigned to specific agents.
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger("gateway.skills")


class SkillManager:
    """Manages skills stored in MongoDB."""

    def __init__(self, db):
        self.db = db

    async def list_skills(self) -> list[dict]:
        skills = await self.db.skills.find({}, {"_id": 0}).to_list(200)
        return skills

    async def get_skill(self, skill_id: str) -> dict | None:
        return await self.db.skills.find_one({"id": skill_id}, {"_id": 0})

    async def create_skill(self, skill: dict) -> dict:
        skill_id = skill.get("id", "").strip().lower().replace(" ", "-")
        if not skill_id:
            raise ValueError("Skill id is required")

        existing = await self.db.skills.find_one({"id": skill_id})
        if existing:
            raise ValueError(f"Skill '{skill_id}' already exists")

        doc = {
            "id": skill_id,
            "name": skill.get("name", skill_id),
            "description": skill.get("description", ""),
            "content": skill.get("content", ""),
            "enabled": skill.get("enabled", True),
            "agents": skill.get("agents", []),  # Empty = available to all agents
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.db.skills.insert_one({**doc})
        logger.info(f"Skill created: {skill_id}")
        return doc

    async def update_skill(self, skill_id: str, updates: dict) -> dict | None:
        allowed_fields = {"name", "description", "content", "enabled", "agents"}
        update_doc = {k: v for k, v in updates.items() if k in allowed_fields}
        if not update_doc:
            return None
        update_doc["updated_at"] = datetime.now(timezone.utc).isoformat()

        await self.db.skills.update_one({"id": skill_id}, {"$set": update_doc})
        logger.info(f"Skill updated: {skill_id}")
        return await self.get_skill(skill_id)

    async def delete_skill(self, skill_id: str) -> bool:
        result = await self.db.skills.delete_one({"id": skill_id})
        if result.deleted_count > 0:
            logger.info(f"Skill deleted: {skill_id}")
            return True
        return False

    async def get_skills_for_agent(self, agent_id: str) -> list[dict]:
        """Get all enabled skills that apply to a specific agent."""
        all_skills = await self.db.skills.find(
            {"enabled": True}, {"_id": 0}
        ).to_list(200)

        applicable = []
        for skill in all_skills:
            agents_list = skill.get("agents", [])
            # Empty agents list = global (applies to all agents)
            if not agents_list or agent_id in agents_list:
                applicable.append(skill)
        return applicable

    async def build_skills_prompt(self, agent_id: str) -> str:
        """Build the skills section to inject into the system prompt."""
        skills = await self.get_skills_for_agent(agent_id)
        if not skills:
            return ""

        sections = []
        sections.append("\n\n---\n## Active Skills\n")
        for skill in skills:
            sections.append(f"### {skill['name']}\n{skill['content']}\n")

        return "\n".join(sections)


async def seed_default_skills(db):
    """Seed some starter skills if none exist."""
    count = await db.skills.count_documents({})
    if count > 0:
        return

    starter_skills = [
        {
            "id": "code-review",
            "name": "Code Review",
            "description": "Guidelines for reviewing code quality, security, and best practices",
            "content": """When reviewing code, follow these principles:

**Quality Checks:**
- Look for clear naming, consistent formatting, and proper documentation
- Check for error handling and edge cases
- Identify potential performance bottlenecks
- Verify test coverage for critical paths

**Security Checks:**
- SQL injection, XSS, CSRF vulnerabilities
- Hardcoded secrets or credentials
- Input validation and sanitization
- Authentication and authorization gaps

**Response Format:**
- Start with a severity summary (Critical / Warning / Info)
- Group findings by category
- Include specific line references and fix suggestions
- End with overall assessment and approval recommendation""",
            "enabled": True,
            "agents": ["engineering"],
        },
        {
            "id": "meeting-notes",
            "name": "Meeting Notes",
            "description": "Structured format for summarizing meetings and extracting action items",
            "content": """When asked to summarize meetings or discussions, use this format:

## Meeting Summary
- **Date:** [date]
- **Participants:** [names]
- **Duration:** [time]

## Key Discussion Points
1. [Topic] — [Summary of discussion]

## Decisions Made
- [Decision with rationale]

## Action Items
| # | Action | Owner | Deadline |
|---|--------|-------|----------|
| 1 | [task] | [who] | [when]   |

## Follow-up Required
- [Items needing further discussion]

Always extract concrete action items with clear owners and deadlines.""",
            "enabled": True,
            "agents": [],  # Global — all agents
        },
        {
            "id": "incident-response",
            "name": "Incident Response",
            "description": "Template for analyzing and responding to production incidents",
            "content": """When analyzing production incidents, follow this structured approach:

**1. Triage (first 5 minutes)**
- What is the impact? (users affected, revenue impact, data at risk)
- What is the severity? (P1-Critical, P2-High, P3-Medium, P4-Low)
- Is there an immediate mitigation? (rollback, feature flag, scaling)

**2. Investigation**
- Timeline: When did it start? Any recent deployments?
- Scope: Which services/regions are affected?
- Root cause hypothesis: What changed?

**3. Resolution**
- Immediate fix applied
- Verification steps
- Communication to stakeholders

**4. Post-Mortem Template**
- Summary of incident
- Timeline of events
- Root cause analysis (use 5 Whys)
- What went well
- What could be improved
- Action items to prevent recurrence

Always recommend writing a post-mortem for P1 and P2 incidents.""",
            "enabled": True,
            "agents": ["engineering"],
        },
        {
            "id": "company-policies",
            "name": "Company Policies",
            "description": "General company policy guidelines for HR-related questions",
            "content": """When answering company policy questions:

**General Guidelines:**
- Always recommend consulting HR directly for specific personal cases
- Provide general policy information, not legal advice
- Be empathetic but factual

**Common Policy Areas:**
- PTO: Refer to the company handbook for specific accrual rates
- Remote Work: Follow the hybrid work policy guidelines
- Expenses: All expenses over $100 require manager approval
- Travel: Book through the approved travel platform

**Escalation:**
- For sensitive topics (harassment, discrimination, termination), always direct to HR
- For benefits questions, direct to the benefits team
- For payroll issues, direct to the payroll team

**Important:** Never make promises about policy outcomes. Always caveat with "based on general policy, but please confirm with HR for your specific situation." """,
            "enabled": True,
            "agents": ["hr-policy"],
        },
    ]

    for skill in starter_skills:
        doc = {
            **skill,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.skills.insert_one(doc)

    logger.info(f"Seeded {len(starter_skills)} default skills")
