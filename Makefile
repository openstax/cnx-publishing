STATEDIR = $(PWD)/.state

# Short descriptions for commands (var format _SHORT_DESC_<cmd>)
_SHORT_DESC_PYENV := "Set up the python environment"

default : help
	@echo "You must specify a command"
	@exit 1



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
#  Catch-all to avoid errors when passing args to make test
# ###

%:
	@:
# /Catch-all
