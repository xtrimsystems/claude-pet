.PHONY: run start stop debug install uninstall test-states sprites help

CLAUDE_CONFIG_DIRS ?= $(HOME)/.claude $(HOME)/.claude-work

# Default: run the pet
run:
	python3 main.py

# Run in background
start:
	python3 main.py &
	@echo "Claude Pet started in background (PID: $$!)"

# Stop the pet
stop:
	@if [ -f /tmp/claude-pet.pid ] && kill "$$(cat /tmp/claude-pet.pid)" 2>/dev/null; then \
		echo "Stopped Claude Pet"; \
	else \
		echo "Claude Pet not running"; \
	fi; \
	rm -f /tmp/claude-pet.pid /tmp/claude-pet-state; \
	rm -rf /tmp/claude-pet-sessions

# Run with debug logging
debug:
	python3 main.py --debug

# Install hooks into every Claude Code config dir (override with CLAUDE_CONFIG_DIRS="...")
install:
	bash install.sh $(CLAUDE_CONFIG_DIRS)

# Uninstall hooks
uninstall:
	bash uninstall.sh $(CLAUDE_CONFIG_DIRS)

# Redraw the generated Deadpool sprites (scooter: shime54-56, finger gun: shime57-68)
sprites:
	python3 tools/draw_scooter.py sprites/deadpool/img
	python3 tools/draw_finger_gun.py sprites/deadpool/img

# Test: cycle through all states (useful for development)
test-states:
	@echo "Testing state transitions..."
	@for state in working thinking attention celebrating doubling idle; do \
		echo "  State: $$state"; \
		echo "$$state" > /tmp/claude-pet-state; \
		sleep 3; \
	done
	@echo "Done!"

# Test: specific state (e.g., make test-attention)
test-%:
	@echo "$*" > /tmp/claude-pet-state
	@echo "Set state to: $*"

help:
	@echo "Claude Pet - Desktop companion for Claude Code"
	@echo ""
	@echo "  make run           Run the pet (foreground)"
	@echo "  make start         Run in background"
	@echo "  make stop          Kill the pet"
	@echo "  make debug         Run with debug logging"
	@echo "  make install       Install hooks (CLAUDE_CONFIG_DIRS=\"~/.claude ~/.claude-work\")"
	@echo "  make uninstall     Remove hooks"
	@echo "  make sprites       Redraw the generated Deadpool sprites"
	@echo "  make test-states   Cycle through all states"
	@echo "  make test-STATE    Set a specific state (e.g., make test-attention)"
