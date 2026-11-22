# Morning Brief pipeline. Everything here is stdlib Python — no install step,
# same commands on a laptop and in GitHub Actions.
PY ?= python3

.PHONY: help test check render status lint

help:
	@printf '%s\n' \
		"test     unit tests" \
		"check    prove the committed Markdown matches the JSON (what CI runs on PRs)" \
		"render   regenerate all Markdown from JSON" \
		"status   list published days and item counts"

test:
	$(PY) -m unittest discover -s tests

check:
	$(PY) -m unittest discover -s tests
	$(PY) -m mb render --check

render:
	$(PY) -m mb render --write

status:
	$(PY) -m mb status
