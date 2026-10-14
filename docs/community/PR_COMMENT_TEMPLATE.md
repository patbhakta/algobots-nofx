# 📢 PR Comment Template for Existing PRs

This template is for maintainers to comment on existing PRs to introduce the new system.

---

## Template (English)

```markdown
Hi @{username}! 👋

Thank you for your contribution to NOFX!

## 🚀 New PR Management System

We're introducing a new PR management system to improve code quality and make reviews faster. Your PR will **not be blocked** by these changes - we'll review it under current standards.

### ✨ Optional: Want to check your PR against new standards?

We've created a **PR health check tool** that analyzes your PR and gives you suggestions!

**How to use:**

```bash
# In your local fork, on your PR branch
cd /path/to/your/nofx-fork
git checkout <your-branch-name>

# Run the health check (reads only, doesn't modify)
./scripts/pr-check.sh
```

**What it does:**
- 🔍 Analyzes your PR (doesn't modify anything)
- ✅ Shows what's already good
- ⚠️ Points out issues
- 💡 Gives specific suggestions on how to fix
- 📊 Overall health score

**Then fix and re-check:**
```bash
# Fix the issues based on suggestions
# Run check again to verify
./scripts/pr-check.sh

# Push when everything looks good
git push origin <your-branch-name>
```

### 📖 Learn More

- [Migration Announcement](https://github.com/NoFxAiOS/nofx/blob/dev/docs/community/MIGRATION_ANNOUNCEMENT.md)
- [Contributing Guidelines](https://github.com/NoFxAiOS/nofx/blob/dev/CONTRIBUTING.md)

### ❓ Questions?

Just ask here! We're happy to help. 🙏

---

**Note:** This migration is **completely optional** for existing PRs. We'll review and merge your PR either way!
```

---


```markdown







```bash
cd /path/to/your/nofx-fork
git checkout <your-branch-name>

./scripts/pr-check.sh
```


```bash
./scripts/pr-check.sh

git push origin <your-branch-name>
```





---

```

---

## Quick Copy-Paste Template

For quick commenting on multiple PRs:

```markdown
👋 Hi! Thanks for your PR!

We're introducing a new PR system. Your PR won't be blocked - we'll review it normally.

**Want to check your PR?** Run this in your fork:
```bash
./scripts/pr-check.sh
```

[Learn more](https://github.com/NoFxAiOS/nofx/blob/dev/docs/community/MIGRATION_ANNOUNCEMENT.md) | This is optional!
```

---

## Bulk Comment Script (for maintainers)

```bash
#!/bin/bash

# Comment on all open PRs
gh pr list --state open --json number --jq '.[].number' | while read pr_number; do
  echo "Commenting on PR #$pr_number"

  gh pr comment "$pr_number" --body "👋 Hi! Thanks for your PR!

We're introducing a new PR system. Your PR won't be blocked - we'll review it normally.

**Want to check your PR?** Run this in your fork:
\`\`\`bash
./scripts/pr-check.sh
\`\`\`

[Learn more](https://github.com/NoFxAiOS/nofx/blob/dev/docs/community/MIGRATION_ANNOUNCEMENT.md) | This is optional!"

  echo "✅ Commented on PR #$pr_number"
  sleep 2  # Be nice to GitHub API
done
```

Save as `comment-all-prs.sh` and run:
```bash
chmod +x comment-all-prs.sh
./comment-all-prs.sh
```
