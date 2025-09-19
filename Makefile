.PHONY: run-bot run-admin compile

run-bot:
	python run.py

run-admin:
	python start_admin_panel.py

compile:
	python -m compileall app utils
