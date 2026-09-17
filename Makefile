.PHONY: check
check:
	@for file in bin/* lib/common.sh lib/crew-status lib/crew-usage lib/release-resources.sh; do bash -n "$$file" || exit; done
	@PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s test -p 'test_*.py' -v
