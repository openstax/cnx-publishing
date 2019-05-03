STATEDIR = $(PWD)/.state
LINTENV = $(STATEDIR)/lint-env

# Short descriptions for commands (var format _SHORT_DESC_<cmd>)
_SHORT_DESC_LINT := "Run linting tools on the codebase"
_SHORT_DESC_PYENV := "Set up the python environment"

default : help
	@echo "You must specify a command"
	@exit 1


# ###
#  Helpers
# ###

$(STATEDIR)/lint-env/pyvenv.cfg : requirements/lint.txt
	@echo "Using Python 2.7 ..."
	rm -rf $(STATEDIR)/lint-env
	virtualenv -p $$(which python2.7) $(VENV_EXTRA_ARGS) $(LINTENV)
	# Mark this as having been built
	touch $(LINTENV)/pyvenv.cfg

	# Upgrade tooling requirements
	$(LINTENV)/bin/python -m pip install --upgrade pip wheel tox setuptools

	# Install requirements
	$(LINTENV)/bin/python -m pip install -r requirements/lint.txt

# /Helpers


# ###
#  Help
# ###

help :
	@echo ""
	@echo "Usage: make <cmd> [<VAR>=<val>, ...]"
	@echo ""
	@echo "Where <cmd> can be:"  # alphbetical please
	@echo "  * help -- this info"
	@echo "  * help-<cmd> -- for more info"
	@echo "  * lint -- ${_SHORT_DESC_LINT}"
	@echo "  * version -- Print the version"
	@echo ""
	@echo "Where <VAR> can be:"  # alphbetical please
	@echo ""

# /Help


# ###
#  Version
# ###


curr_tag := $(shell git describe --tags $$(git rev-list --tags --max-count=1))
curr_tag_rev := $(shell git rev-parse "$(curr_tag)^0")
head_rev := $(shell git rev-parse HEAD)
head_short_rev := $(shell git rev-parse --short HEAD)
ifeq ($(curr_tag_rev),$(head_rev))
	version := $(curr_tag)
else
	version := $(curr_tag)-dev$(head_short_rev)
endif

version help-version : .git
	@echo $(version)

# /Version


# ###
#  Lint
# ###

help-lint :
	@echo "${_SHORT_DESC_LINT}"
	@echo "Usage: make lint"

lint : $(LINTENV)/pyvenv.cfg setup.cfg
	@$(LINTENV)/bin/python -m flake8 --exclude=cnxpublishing/tests *.py cnxpublishing/
	@$(LINTENV)/bin/python -m flake8 --max-line-length=200 cnxpublishing/tests
	@echo '====  ====  ====  ====  ====  ====  ====  ====  ====  ===='
	@$(LINTENV)/bin/python -m doc8.main README.rst docs/

# /Lint


# ###
#  Catch-all to avoid errors when passing args to make test
# ###

%:
	@:
# /Catch-all
