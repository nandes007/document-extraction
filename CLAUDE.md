@PROJECT_BRIEF.md

- Work on one task file from `tasks/` at a time.
- Never edit files in `data/ground_truth/`.
- Never write an API key into any file.
- Ask before changing the schema.
- Local container runtime is Podman: use `podman compose`, but keep `docker-compose.yml` fully Docker-compatible. The README documents `docker compose` commands.
- Never call the real LLM provider. Verify with tests and fakes only. Real eval runs are started by the user.
- Stop when the task's "Done when" list is satisfied. Do not start the next task.