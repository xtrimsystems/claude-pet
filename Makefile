.PHONY: run stop install uninstall test-states clean help

# Default: run the pet
run:
	python3 main.py

# Run in background
start:
	python3 main.py &
	@echo "Claude Pet started in background (PID: $$!)"

# Stop the pet
stop:
	@if [ -f /tmp/claude-pet.pid ]; then \
		kill $$(cat /tmp/claude-pet.pid) 2>/dev/null && echo "Claude Pet stopped" || echo "Claude Pet not running"; \
	else echo "Claude Pet not running"; fi

# Run with debug logging
debug:
	python3 main.py --debug

# Install hooks and print setup instructions
install:
	bash install.sh

# Uninstall hooks
uninstall:
	bash uninstall.sh

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
	@echo "  make install       Install hooks and setup"
	@echo "  make uninstall     Remove hooks"
	@echo "  make test-states   Cycle through all states"
	@echo "  make test-STATE    Set a specific state (e.g., make test-attention)"
