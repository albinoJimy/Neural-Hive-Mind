.PHONY: deploy validate proto

deploy:
	@../../scripts/deploy.sh --services optimizer-agents --env $(ENV)

validate:
	@../../scripts/validate.sh --target services --component optimizer-agents

proto:
	python -m grpc_tools.protoc \
		-I. \
		--python_out=. \
		--grpc_python_out=. \
		src/proto/optimizer_agent.proto
	python -m grpc_tools.protoc \
		-I. \
		--python_out=. \
		--grpc_python_out=. \
		proto/consensus_engine_extensions.proto \
		proto/orchestrator_extensions.proto
