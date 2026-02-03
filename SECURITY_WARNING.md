# SECURITY WARNING

## Credentials Exposed in Git History

**Date:** 2026-02-03
**Severity:** MEDIUM

### Issue
The following files previously contained hardcoded database credentials that were committed and pushed to the GitHub repository:

1. `start_backend.ps1` - Hardcoded password `iccdds_password`
2. `docker-compose.dev.yml` - Hardcoded password `iccdds_password`
3. `docker-compose.yml` - Fallback default password

### Exposed Credentials
- **Username:** `iccdds`
- **Password:** `iccdds_password`
- **Database:** `iccdds`

### Impact
These credentials are visible in the public GitHub repository history. Anyone with access to the repository can view these credentials.

### Remediation Steps

#### 1. For Development/Testing Environments
If you're using these credentials in a development environment:
- **Change the database password immediately**
- Update your `.env` file with new credentials
- Never use these exposed credentials again

```bash
# Connect to PostgreSQL and change password
psql -h localhost -p 5433 -U iccdds -d iccdds
ALTER USER iccdds WITH PASSWORD 'your-new-secure-password';
```

#### 2. For Production Environments
If you used these credentials in production:
- **CRITICAL: Change all passwords immediately**
- Rotate all secrets and API keys
- Review database logs for unauthorized access
- Consider the database potentially compromised

#### 3. Updated Configuration
All configuration files have been updated to use environment variables:
- Copy `.env.example` to `.env`
- Set strong, unique passwords
- Never commit `.env` to git (already in `.gitignore`)

```bash
# Generate a secure password
openssl rand -base64 32

# Set in .env file
POSTGRES_PASSWORD=your-generated-secure-password
```

#### 4. Git History Cleanup (Optional)
To remove credentials from git history, use BFG Repo-Cleaner or git-filter-repo:

```bash
# WARNING: This rewrites history and requires force push
# All collaborators will need to re-clone the repository

# Option 1: BFG Repo-Cleaner
java -jar bfg.jar --replace-text passwords.txt

# Option 2: git-filter-repo
git filter-repo --path start_backend.ps1 --invert-paths --force
```

**Note:** Rewriting git history is disruptive and should be coordinated with all team members.

### Prevention
- Always use environment variables for sensitive data
- Use `.env` files (never commit them)
- Review code before committing for hardcoded secrets
- Use pre-commit hooks to scan for secrets
- Consider using secret management tools (HashiCorp Vault, AWS Secrets Manager, etc.)

### Status
✅ Fixed in commit (pending)
- `start_backend.ps1` now loads credentials from `.env`
- `docker-compose.dev.yml` uses environment variables with safe fallback
- Added `.env.example` template

### References
- [OWASP: Use of Hard-coded Credentials](https://owasp.org/www-community/vulnerabilities/Use_of_hard-coded_credentials)
- [GitHub: Removing sensitive data](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)
