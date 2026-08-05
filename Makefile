# Regex against the raw file text rather than a TOML parser -- avoids
# needing tomllib (Python 3.11+ only) or a tomli fallback on 3.9/3.10 for
# a single top-level `version = "..."` line under [project].
VERSION := $(shell python -c "import re; print(re.search(r'(?m)^version = \"([^\"]+)\"', open('pyproject.toml').read()).group(1))")

CURRENT_BRANCH := $(shell git rev-parse --abbrev-ref HEAD)

# -----------------------------
# Version bumping
# -----------------------------
bump-patch:
	bump2version patch

bump-minor:
	bump2version minor

bump-major:
	bump2version major

# -----------------------------
# TestPyPI Release
# -----------------------------
release-test:
	@echo "Releasing to TestPyPI version $(VERSION)"
	@if git rev-parse "v$(VERSION)-test" >/dev/null 2>&1; then \
	    echo "ERROR: Tag v$(VERSION)-test already exists."; \
	    exit 1; \
	fi
	git tag v$(VERSION)-test
	git push origin v$(VERSION)-test

# -----------------------------
# Production PyPI Release
# -----------------------------
release-prod:
	@if [ "$(CURRENT_BRANCH)" != "main" ]; then \
	    echo "ERROR: Must be on main to release to PyPI."; \
	    exit 1; \
	fi
	@echo "Checking tag state for v$(VERSION)..."
	@if git rev-parse "v$(VERSION)" >/dev/null 2>&1; then \
	    local_exists=1; \
	else \
	    local_exists=0; \
	fi; \
	\
	if git ls-remote --tags origin "v$(VERSION)" | grep "v$(VERSION)" >/dev/null; then \
	    remote_exists=1; \
	else \
	    remote_exists=0; \
	fi; \
	\
	if [ $$local_exists -eq 1 ] && [ $$remote_exists -eq 1 ]; then \
	    echo "ERROR: Tag v$(VERSION) exists locally AND remotely. Aborting release."; \
	    exit 1; \
	fi; \
	\
	if [ $$local_exists -eq 1 ] && [ $$remote_exists -eq 0 ]; then \
	    echo "Local tag v$(VERSION) exists but remote does not. Deleting local tag..."; \
	    git tag -d v$(VERSION); \
	fi; \
	\
	if [ $$local_exists -eq 0 ]; then \
	    echo "Creating local tag v$(VERSION)"; \
	    git tag v$(VERSION); \
	fi; \
	\
	if [ $$remote_exists -eq 0 ]; then \
	    echo "Pushing tag v$(VERSION) to origin"; \
	    git push origin v$(VERSION); \
	else \
	    echo "Remote tag v$(VERSION) already exists. Skipping push."; \
	fi; \
	\
	if gh release view v$(VERSION) >/dev/null 2>&1; then \
	    echo "GitHub Release v$(VERSION) already exists. Updating notes."; \
	    gh release edit v$(VERSION) --generate-notes; \
	else \
	    echo "Creating GitHub Release v$(VERSION)"; \
	    gh release create v$(VERSION) --generate-notes; \
	fi
	@echo "release-prod completed successfully."

release: release-prod

.PHONY: bump-patch bump-minor bump-major release-test release-prod release
