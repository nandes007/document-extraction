@PROJECT_BRIEF.md

- Work on one task file from `tasks/` at a time.
- Never edit files in `data/ground_truth/`.
- Never write an API key into any file.
- Ask before changing the schema.
- Local container runtime is Podman: use `podman compose`, but keep
  `docker-compose.yml` fully Docker-compatible. The README documents
  `docker compose` commands.