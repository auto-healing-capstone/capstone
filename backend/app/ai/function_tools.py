from openai.types.chat import ChatCompletionToolParam

ANALYZE_TOOL: ChatCompletionToolParam = {
    "type": "function",
    "function": {
        "name": "analyze_incident",
        "description": "Analyze the incident and return structured diagnosis.",
        "parameters": {
            "type": "object",
            "properties": {
                "ai_title": {
                    "type": "string",
                    "description": "One-line incident title, 10 words or less.",
                },
                "ai_severity": {
                    "type": "string",
                    "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                    "description": (
                        "Assessed severity based on alert data and predictions."
                    ),
                },
                "llm_analysis": {
                    "type": "string",
                    "description": (
                        "Structured analysis with three sections: "
                        "Observed symptom, Inferred cause, Risk assessment."
                    ),
                },
                "incident_types": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "CONTAINER_CRASH",
                            "OOM",
                            "DISK_FULL",
                            "HIGH_CPU",
                            "DB_CONNECTION",
                            "NGINX_5XX",
                        ],
                    },
                    "description": (
                        "One or more incident types that apply. "
                        "Select multiple for compound failures."
                    ),
                },
            },
            "required": ["ai_title", "ai_severity", "llm_analysis", "incident_types"],
        },
    },
}

RECOMMEND_TOOL: ChatCompletionToolParam = {
    "type": "function",
    "function": {
        "name": "recommend_action",
        "description": "Recommend a recovery action based on the incident analysis.",
        "parameters": {
            "type": "object",
            "properties": {
                "action_type": {
                    "type": "string",
                    "enum": [
                        "RESTART_CONTAINER",
                        "CLEAR_LOGS",
                        "DOCKER_PRUNE",
                        "RESTART_PROCESS",
                        "SCALE_OUT",
                    ],
                    "description": "Recovery action type matching ActionTypeEnum.",
                },
                "reason": {
                    "type": "string",
                    "description": "Why this action fits the diagnosed root cause.",
                },
                "slack_summary": {
                    "type": "string",
                    "description": (
                        "1-2 sentences for human operators in Slack. "
                        "States what happened and what action is proposed."
                    ),
                },
            },
            "required": ["action_type", "reason", "slack_summary"],
        },
    },
}
