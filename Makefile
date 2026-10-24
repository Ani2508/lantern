# Thin wrapper: every target calls scripts/tasks.py (the real task runner, also used on Windows).
PY ?= python
TARGETS = setup check sim train local-demo eval dashboard api fallback deploy destroy seed check-bedrock features regen-fixtures warm

.PHONY: $(TARGETS)

$(TARGETS):
	$(PY) scripts/tasks.py $@ $(if $(SCENARIO),SCENARIO=$(SCENARIO)) $(ARGS)
