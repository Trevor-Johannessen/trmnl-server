PORT    := 8015
DEST    := /usr/local/bin/trmnl-server
STATE   := /var/lib/trmnl-server
VENV    := $(DEST)/venv
SERVICE := trmnl-server
# The service runs as this user, not root; see trmnl-server.service.
RUNAS   := tjohannessen

# venv is excluded so `make install` never clobbers the installed environment;
# `make deps` owns it. tests/ and integrations/ are development material.
EXCLUDE := .* __pycache__ venv* *.service Makefile tests integrations *.md ./
EXCLUDE_FLAGS := $(foreach pattern,$(EXCLUDE),--exclude='$(pattern)')

.PHONY: dryrun install uninstall deps debug test lint status logs preview clean

dryrun:
	rsync -avn $(EXCLUDE_FLAGS) ./ $(DEST)/

install: dryrun
	@command -v systemctl >/dev/null 2>&1 || { echo "systemd not found; this target is for deploy1." >&2; exit 1; }
	@test -d $(VENV) || { echo "No venv at $(VENV) -- run 'make deps' first." >&2; exit 1; }
	firewall-cmd --permanent --add-port=$(PORT)/tcp || true
	firewall-cmd --reload || true
	mkdir -p $(DEST) $(STATE)
	chown -R $(RUNAS) $(STATE)
	rsync -av $(EXCLUDE_FLAGS) ./ $(DEST)/
	cp $(SERVICE).service /etc/systemd/system/
	systemctl daemon-reload
	systemctl restart $(SERVICE)
	systemctl status $(SERVICE) --no-pager

# Chromium is downloaded into the *user's* cache, not root's: the service runs
# as tjohannessen (as monika does) so it can read ~/.credentials and the skills
# tree. ~ is the NFS home, so this download is shared by every host.
deps:
	mkdir -p $(DEST) $(STATE)
	chown -R $(RUNAS) $(STATE)
	test -d $(VENV) || python3 -m venv $(VENV)
	$(VENV)/bin/python -m pip install --upgrade pip
	$(VENV)/bin/python -m pip install -r requirements.txt
	runuser -u $(RUNAS) -- $(VENV)/bin/python -m playwright install chromium
	$(VENV)/bin/python -c "import playwright, PIL, caldav; print('deps ok')"

uninstall:
	-systemctl stop $(SERVICE)
	-systemctl disable $(SERVICE)
	rm -f /etc/systemd/system/$(SERVICE).service
	systemctl daemon-reload
	-systemctl reset-failed $(SERVICE)
	-firewall-cmd --permanent --remove-port=$(PORT)/tcp || true
	-firewall-cmd --reload || true
	rm -rf $(DEST)
	@echo "Kept $(STATE) (metrics history and the device registry)."

# ./data rather than $(STATE) so a debug run needs no root and cannot write to
# the live history or steal the device's registry.
debug:
	TRMNL_SERVER_DATA_DIR=./data TRMNL_SERVER_BASE_URL=http://$(shell hostname -f):8016 \
	  ./venv/bin/python -m trmnl_server --port 8016

test:
	./venv/bin/python -m unittest discover -s tests -t . -v

lint:
	./venv/bin/python -m compileall -q trmnl_server tests

# Render every screen to a PNG in ./data/preview for eyeballing at 1-bit.
preview:
	./venv/bin/python -m trmnl_server.preview

status:
	curl -s http://localhost:$(PORT)/ | python3 -m json.tool

logs:
	journalctl -u $(SERVICE) -f --no-pager

clean:
	rm -rf __pycache__ trmnl_server/__pycache__ tests/__pycache__ data
