# -----------------------------
# Version bumping
# -----------------------------
bump-patch:
	bump2version patch

bump-minor:
	bump2version minor

bump-major:
	bump2version major

.PHONY: bump-patch bump-minor bump-major
