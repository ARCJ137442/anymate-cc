# AnyMate-CC v0.1.0 Release Checklist

## Pre-Release (Completed ✅)
- [x] All security fixes implemented and tested (4 rounds, 11 issues)
- [x] CHANGELOG.md created (commit c5d9ae4)
- [x] Release notes drafted (RELEASE_NOTES_v0.1.0.md, commit e32080d)
- [x] All tests passing (19 passed, 1 xfail)
- [x] Documentation updated (README, security docs)
- [x] PR #22 ready for merge
- [x] Version numbers consistent (0.1.0 in pyproject.toml and __init__.py)

## Release Process

### Step 1: Merge to Main
```bash
# Switch to main branch
git checkout main
git pull origin main

# Merge dev branch
git merge dev --no-ff -m "Merge branch 'dev' - Release v0.1.0"

# Push to origin
git push origin main
```

### Step 2: Create Git Tag
```bash
# Create annotated tag
git tag -a v0.1.0 -m "Release v0.1.0 - Security-first stable release

- 11 security fixes across 4 rounds
- Cross-platform support (Windows/Linux/macOS/Termux)
- Defense-in-depth security architecture
- Production-ready backends

See CHANGELOG.md and RELEASE_NOTES_v0.1.0.md for details."

# Push tag
git push origin v0.1.0
```

### Step 3: Create GitHub Release
1. Go to https://github.com/ARCJ137442/anymate-cc/releases/new
2. **Tag**: Select `v0.1.0`
3. **Title**: `AnyMate-CC v0.1.0 - Security First Release`
4. **Description**: Copy content from `RELEASE_NOTES_v0.1.0.md`
5. **Attachments**: None needed (source auto-attached)
6. **Mark as latest release**: ✅ Yes
7. **Mark as pre-release**: ❌ No
8. Click **Publish release**

### Step 4: Close PR #22
```bash
# PR will auto-close on merge, verify:
gh pr list --state merged
```

## Post-Release Tasks

### GitHub Repository

- [ ] Update README badges (if any)
- [ ] Close related issues:
  - [ ] Check open security issues
  - [ ] Check cross-platform support issues
  - [ ] Update issue labels as needed

- [ ] Pin important issues/discussions

### Documentation

- [ ] Verify README.md displays correctly on GitHub
- [ ] Verify CHANGELOG.md formats correctly
- [ ] Check all links in documentation are working
- [ ] Update any version-specific documentation

### Communication

- [ ] **GitHub Discussions**: Post release announcement
  ```
  Title: 🎉 AnyMate-CC v0.1.0 Released - Security First Stable Release
  Content: Link to release notes + highlights
  ```

- [ ] **GitHub Issues**: Comment on related issues that they're fixed in v0.1.0

- [ ] **Social Media** (if applicable):
  - [ ] Twitter/X announcement
  - [ ] Reddit (r/ClaudeAI, r/Python, etc.)
  - [ ] Dev.to / Hashnode blog post

### Package Distribution (if planning PyPI release)

- [ ] Build distribution packages:
  ```bash
  python -m build
  ```

- [ ] Test installation from dist:
  ```bash
  pip install dist/anymate_cc-0.1.0-py3-none-any.whl
  ```

- [ ] Upload to PyPI:
  ```bash
  python -m twine upload dist/*
  ```

- [ ] Verify PyPI page:
  - [ ] Description renders correctly
  - [ ] Links work
  - [ ] Installation instructions accurate

### Testing & Validation

- [ ] Fresh install test on clean environment
- [ ] Smoke test each backend (stdio, python-repl, shell, codex)
- [ ] Verify MCP integration works
- [ ] Cross-platform validation (if possible):
  - [ ] Windows (Cygwin/MSYS2)
  - [ ] Linux
  - [ ] macOS
  - [ ] Termux (if available)

### Maintenance

- [ ] Create `v0.2` milestone on GitHub
- [ ] Move deferred issues to v0.2 milestone:
  - [ ] Cryptographic sender authentication
  - [ ] Secure IPC migration
  - [ ] shutdown_request protocol
  - [ ] Enhanced team validation
  - [ ] CI Windows test matrix
  - [ ] Native PowerShell backend
  - [ ] Cross-platform split-window

- [ ] Update project roadmap
- [ ] Create `SECURITY.md` with vulnerability reporting guidelines

### Cleanup

- [ ] Archive old development branches (if any)
- [ ] Clean up stale issues
- [ ] Update issue templates (if needed)
- [ ] Review and update CONTRIBUTING.md (if it exists)

## Rollback Plan (if needed)

If critical issues are discovered immediately after release:

1. **Immediate hotfix**:
   ```bash
   # Create hotfix branch from v0.1.0
   git checkout -b hotfix/v0.1.1 v0.1.0

   # Fix issue, test, commit
   git add .
   git commit -m "hotfix: ..."

   # Merge to main and tag
   git checkout main
   git merge hotfix/v0.1.1
   git tag -a v0.1.1 -m "Hotfix release"
   git push origin main v0.1.1
   ```

2. **Update GitHub release** with hotfix notice

3. **Notify users** via GitHub Discussions/Issues

## Success Criteria

Release is considered successful when:
- [x] All tests passing (19 passed, 1 xfail)
- [ ] GitHub release published
- [ ] At least 5 fresh installs tested successfully
- [ ] No critical bugs reported within 48 hours
- [ ] Documentation accessible and accurate
- [ ] Community feedback is positive/constructive

## Notes

- **Upgrade Priority**: HIGH (critical security fixes)
- **Breaking Changes**: Yes (codex defaults) - documented in release notes
- **Backward Compatibility**: API unchanged, only default values
- **Support Period**: v0.1.x will receive security patches until v0.2.0 release

## Timeline

- **Pre-release prep**: Completed
- **Release date**: 2026-03-07
- **Post-release tasks**: Complete within 7 days
- **v0.2 planning**: Start after post-release stabilization

---

Last updated: 2026-03-07
