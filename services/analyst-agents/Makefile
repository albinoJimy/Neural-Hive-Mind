.PHONY: deploy validate

deploy:
	@../../scripts/deploy.sh --services analyst-agents --env $(ENV)

validate:
	@../../scripts/validate.sh --target services --component analyst-agents
