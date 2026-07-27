from .contracts import FrameworkAgent


def framework_agents() -> list[FrameworkAgent]:
    return [
        FrameworkAgent(
            agent_id="governed-cohort-agent",
            name="Governed Cohort Agent",
            framework="LangGraph",
            framework_version="1.x",
            owner="OncoAgent Platform",
            role="first-party operational workflow",
            risk_tier="high-governance",
            supported_use_cases=["regulated cohort discovery", "durable verification workflow"],
            prohibited_use_cases=["clinical diagnosis", "treatment recommendation", "raw export"],
            dataset_permissions=["allowlisted synthetic Synthea datasets"],
            tools=["internal governed registry"],
            model_policy={"planner": "configured local policy", "fallback": "deterministic"},
            approval_policy={"required": True, "separation_of_duties": True},
            recovery={"mode": "checkpoint_resume", "durable": True},
            status="implemented",
            evaluation_summary={"source": "cross-framework evaluation"},
            known_limitations=["synthetic data only", "not clinically validated"],
        ),
        FrameworkAgent(
            agent_id="oncology-research-crew",
            name="Oncology Research Crew",
            framework="CrewAI",
            framework_version="1.15.7",
            owner="OncoAgent Platform",
            role="downstream MCP consumer",
            risk_tier="bounded-research",
            supported_use_cases=["specialist evidence gathering", "research brief drafting"],
            prohibited_use_cases=[
                "control-plane execution",
                "self approval",
                "clinical care",
                "raw export",
            ],
            dataset_permissions=["MCP-allowlisted synthetic Synthea datasets"],
            tools=["MCP read-only clinical tools"],
            model_policy={"default": "llama3.2:3b", "memory": False, "delegation": False},
            approval_policy={"required": True, "separate_reviewer": True},
            recovery={"mode": "process_interrupted_only", "durable": False},
            status="implemented",
            evaluation_summary={"source": "cross-framework evaluation"},
            known_limitations=[
                "local execution is not durable",
                "synthetic data only",
                "not clinically validated",
            ],
        ),
    ]
