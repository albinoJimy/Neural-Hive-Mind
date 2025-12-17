.PHONY: deploy validate

deploy:
	@../../scripts/deploy.sh --services optimizer-agents --env $(ENV)

validate:
	@../../scripts/validate.sh --target services --component optimizer-agents
