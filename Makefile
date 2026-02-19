.PHONY: run stop install uninstall test-states test-pet clean help

NAMES = alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november oscar papa quebec romeo sierra tango

# Default: run the pet
run:
	python3 main.py

# Run in background
start:
	python3 main.py &
	@echo "Claude Pet started in background (PID: $$!)"

# Stop the pet (kills default instance and all per-project instances)
stop:
	@found=false; \
	for pidfile in /tmp/claude-pet*.pid; do \
		[ -f "$$pidfile" ] || continue; \
		pid=$$(cat "$$pidfile" 2>/dev/null); \
		if [ -n "$$pid" ] && kill "$$pid" 2>/dev/null; then \
			echo "Stopped Claude Pet (PID $$pid, $$pidfile)"; \
			found=true; \
		fi; \
		rm -f "$$pidfile"; \
	done; \
	rm -f /tmp/claude-pet-*-pos; \
	$$found || echo "Claude Pet not running"

# Run with debug logging
debug:
	python3 main.py --debug

# Install hooks and print setup instructions
install:
	bash install.sh

# Uninstall hooks
uninstall:
	bash uninstall.sh

# Spawn a test pet with a random NATO name
test-pet:
	@name=$$(echo $(NAMES) | tr ' ' '\n' | shuf -n1); \
	hash=$$(echo "$$name-$$$$" | md5sum | cut -c1-8); \
	echo "Spawning test pet: $$name ($$hash)"; \
	python3 main.py --debug \
		--state-file /tmp/claude-pet-$$hash-state \
		--pid-file /tmp/claude-pet-$$hash.pid \
		--project-name $$name &

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
	@echo "  make test-pet      Spawn a test pet (random name)"
	@echo "  make test-states   Cycle through all states"
	@echo "  make test-STATE    Set a specific state (e.g., make test-attention)"
