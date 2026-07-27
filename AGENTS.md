# OncoAgent Platform Engineering Rules

- Use synthetic Synthea data only.
- Never commit raw datasets, archives, extracted FHIR files, generated patient records, database volumes, embeddings, model weights, caches, secrets, tokens, or `.env` files.
- Do not claim that the platform is clinically validated.
- Do not invent metrics or evaluation results.
- Use typed Python and TypeScript.
- Use Pydantic for API request and response boundaries.
- Keep business logic outside FastAPI route handlers.
- Add tests for new backend behavior.
- Run formatting, linting, type checking, and tests before reporting completion.
- Do not add dependencies without a clear present need.
- LangGraph will be the future primary agent runtime.
- CrewAI will later be a downstream integration, not the core runtime.
- Do not add AutoGen as a core dependency.
- Do not make Git commits unless explicitly requested.
