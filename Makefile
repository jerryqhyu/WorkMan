.PHONY: backend desktop dev mcp bootstrap build-sidecar

backend:
	cd backend && uv sync
	cd backend && uv run agentpm-server serve --reload

desktop:
	cd apps/desktop && npm install
	cd apps/desktop && npm run dev

dev:
	./scripts/dev.sh

mcp:
	cd backend && uv run agentpm-server mcp --port 8766

bootstrap:
	cd backend && uv run agentpm-server bootstrap-repo $(path)

build-sidecar:
	./scripts/build_sidecar.sh
