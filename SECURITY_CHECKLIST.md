# 🔐 Security Checklist - Before Committing to Git

## ✅ Files That Should NEVER Be Committed

### 1. Environment Files
- [ ] `.env` - Main environment file with real credentials
- [ ] `frontend/.env` - Frontend environment variables
- [ ] `.env.local`, `.env.production` - All .env variants
- [ ] **SAFE TO COMMIT**: `.env.example` (template with placeholders)

### 2. Credentials & Keys
- [ ] `*.pem`, `*.key` - Private keys
- [ ] `credentials.json`, `secrets.json` - API credentials
- [ ] `service-account*.json` - Cloud service accounts
- [ ] SSH keys (`id_rsa`, `id_dsa`, etc.)

### 3. Database Files
- [ ] `*.sql`, `*.dump` - Database backups with real data
- [ ] `pgdata/`, `postgres-data/` - PostgreSQL data directories
- [ ] `dump.rdb` - Redis database dump

### 4. Local Configuration
- [ ] `.claude/` - Claude Code local settings
- [ ] `docker-compose.override.yml` - Local Docker overrides

---

## 🛡️ Pre-Commit Verification Commands

### Before First Commit (Initialize Git)

```bash
# 1. Initialize git repository
git init

# 2. Add .gitignore first (BEFORE adding any files)
git add .gitignore

# 3. Verify .gitignore is working - check what will be committed
git status

# 4. Look for red flags in the output:
#    ❌ If you see .env
#    ❌ If you see *.key or *.pem
#    ❌ If you see credentials.json
#    STOP and update .gitignore!
```

### Check for Accidentally Tracked Credentials

```bash
# Check if any credential files are staged
git ls-files | grep -E '\\.env$|password|secret|credentials|*.key|*.pem'

# If anything appears, remove it immediately:
git rm --cached .env
git rm --cached <filename>
```

### Verify Sensitive Files Are Ignored

```bash
# Test that .env is ignored
git check-ignore -v .env
# Should output: .gitignore:XX:.env    .env

# Test that credentials.json is ignored
git check-ignore -v credentials.json
# Should output: .gitignore:XX:credentials.json    credentials.json

# If it says "not ignored", update .gitignore!
```

---

## 📋 Sensitive Data in Current .env File

Your `.env` file contains these sensitive values:
- ❌ Database password
- ❌ PostgreSQL credentials
- ❌ Secret key for JWT
- ❌ Redis connection strings (if password protected)

**DO NOT commit this file!**

---

## 🔍 How to Check if Credentials Are Already Committed

### If you already initialized git:

```bash
# Search git history for .env file
git log --all --full-history -- .env

# Search for passwords in commit history
git log --all -p -S "password"

# If found, you need to remove them from git history:
# (WARNING: This rewrites history - coordinate with your team!)
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch .env" \
  --prune-empty --tag-name-filter cat -- --all
```

---

## ✅ Safe Files to Commit

These files are SAFE to commit (already configured in .gitignore):
- ✅ `.env.example` - Template with placeholders
- ✅ `requirements.txt` - Python dependencies
- ✅ `package.json` - Node dependencies
- ✅ `Dockerfile`, `docker-compose.yml` - Infrastructure as code
- ✅ All source code (`.py`, `.ts`, `.tsx`)
- ✅ Documentation (`.md` files)
- ✅ Configuration templates without secrets

---

## 🚀 First Commit Workflow

```bash
# 1. Verify .gitignore is in place
cat .gitignore | head -20

# 2. Check what git sees (should NOT include .env)
git status

# 3. Add all safe files
git add .

# 4. Double-check what's staged
git status

# 5. If everything looks safe, commit
git commit -m "Initial commit - ICCDDS Cold Chain Dispatch System"

# 6. Before pushing to remote, final check
git log --stat
```

---

## 🔐 Production Security Reminders

1. **Generate new SECRET_KEY** for production:
   ```bash
   openssl rand -hex 32
   ```

2. **Use strong database passwords** (not "iccdds_password")

3. **Enable HTTPS** in production

4. **Use environment-specific .env files**:
   - Development: `.env.development`
   - Production: `.env.production`
   - Both should be in `.gitignore`!

5. **Never log sensitive data** (passwords, tokens, API keys)

6. **Use secrets management** in production (AWS Secrets Manager, HashiCorp Vault, etc.)

---

## 📌 Quick Reference

### What's in .gitignore?
- ✅ All `.env` files (except `.env.example`)
- ✅ All credential files (`*.key`, `*.pem`, `credentials.json`)
- ✅ Database dumps and data directories
- ✅ `node_modules/`, `__pycache__/`
- ✅ Build outputs (`dist/`, `build/`)
- ✅ IDE files (`.vscode/`, `.idea/`)
- ✅ OS files (`.DS_Store`, `Thumbs.db`)
- ✅ Logs and temp files
- ✅ Claude Code settings (`.claude/`)

### What's NOT in .gitignore (safe to commit)?
- ✅ `.env.example` - Template file
- ✅ `.gitignore` itself
- ✅ Source code
- ✅ Documentation
- ✅ Configuration templates

---

## ⚠️ Emergency: Credentials Were Committed!

If you accidentally committed credentials:

### 1. For the most recent commit (not pushed yet):
```bash
# Remove file from commit
git reset HEAD~1
git add .
git commit -m "Fix: Remove credentials"
```

### 2. If already pushed to remote:
```bash
# ⚠️ WARNING: This requires force push - coordinate with team!

# Remove from history
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch .env" \
  --prune-empty -- --all

# Force push (BE CAREFUL!)
git push origin --force --all

# Rotate ALL credentials immediately!
```

### 3. After fixing:
- 🔄 Generate new secrets/passwords
- 🔄 Update all services with new credentials
- 🔄 Invalidate old credentials if possible
- 📝 Document the incident

---

**Remember**: Once credentials are pushed to a public repository, consider them compromised permanently. Even if removed from git history, they may still exist in forks, clones, or cached versions.

**Always verify before pushing!**
