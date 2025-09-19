.PHONY: run-bot run-admin compile smoke-polling

run-bot:
	python run.py

run-admin:
	python start_admin_panel.py

compile:
        python -m compileall app utils

smoke-polling:
        python -m utils.smoke_polling
