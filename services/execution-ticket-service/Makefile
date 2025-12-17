.PHONY: deploy validate

deploy:
	@../../scripts/deploy.sh --services execution-ticket-service --env $(ENV)

validate:
	@../../scripts/validate.sh --target services --component execution-ticket-service
