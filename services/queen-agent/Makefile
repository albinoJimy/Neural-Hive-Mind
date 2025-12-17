.PHONY: deploy validate

deploy:
	@../../scripts/deploy.sh --services queen-agent --env $(ENV)

validate:
	@../../scripts/validate.sh --target services --component queen-agent
