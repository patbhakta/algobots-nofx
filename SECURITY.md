

---

# English

## 🛡️ Security Overview

NOFX is an AI-powered trading system that handles real funds and API credentials. We take security seriously and appreciate the security community's efforts to responsibly disclose vulnerabilities.

**Critical Areas:**
- 🔑 API key storage and handling
- 💰 Trading execution and fund management
- 🔐 Authentication and authorization
- 🗄️ Database security (SQLite)
- 🌐 Web interface and API endpoints

---

## 📋 Supported Versions

We provide security updates for the following versions:

| Version | Supported          | Notes                |
| ------- | ------------------ | -------------------- |
| 3.x     | ✅ Fully supported | Current stable release |
| 2.x     | ⚠️ Limited support | Security fixes only |
| < 2.0   | ❌ Not supported   | Please upgrade       |

**Recommendation:** Always use the latest stable release (v3.x) for best security.

---

## 🔒 Reporting a Vulnerability

### ⚠️ Please DO NOT Publicly Disclose

If you discover a security vulnerability in NOFX, please **DO NOT**:
- ❌ Open a public GitHub Issue
- ❌ Discuss it on social media (Twitter, Reddit, etc.)
- ❌ Share it in Telegram/Discord groups
- ❌ Post it on security forums before we've had time to fix it

Public disclosure before a fix is available puts all users at risk.

### ✅ Responsible Disclosure Process

**Step 1: Report Privately**

Contact core team directly:
- **Tinkle:** [@Web3Tinkle on Twitter](https://x.com/Web3Tinkle) (DM)

**Alternative:** Encrypted communication via [Keybase](https://keybase.io/) (if available)

**Step 2: Include These Details**

```markdown
Subject: [SECURITY] Brief description of vulnerability

## Vulnerability Description
Clear explanation of the security issue

## Affected Components
- Which parts of the system are affected?
- Which versions are vulnerable?

## Reproduction Steps
1. Step-by-step instructions
2. Sample code or commands (if applicable)
3. Expected vs actual behavior

## Potential Impact
- Can funds be stolen?
- Can API keys be leaked?
- Can accounts be compromised?
- Rate the severity: Critical / High / Medium / Low

## Suggested Fix (Optional)
If you have ideas for fixing it, please share!

## Your Information
- Name (or pseudonym)
- Contact info for follow-up
- If you want public credit (yes/no)
```

**Step 3: Wait for Our Response**

We will:
- ✅ Acknowledge receipt within **24 hours**
- ✅ Provide initial assessment within **72 hours**
- ✅ Keep you updated on fix progress
- ✅ Notify you before public disclosure

---

## ⏱️ Response Timeline

| Stage | Timeline | Action |
|-------|----------|--------|
| **Acknowledgment** | 24 hours | Confirm we received your report |
| **Initial Assessment** | 72 hours | Verify vulnerability, rate severity |
| **Fix Development** | 7-30 days | Depends on complexity and severity |
| **Testing** | 3-7 days | Verify fix doesn't break functionality |
| **Public Disclosure** | After fix deployed | Publish security advisory |

**Critical vulnerabilities** (fund theft, credential leaks) are prioritized and may be fixed within 48 hours.

---

## 💰 Security Bounty Program (Optional)

We offer rewards for valid security vulnerabilities:

| Severity | Criteria | Reward |
|----------|----------|--------|
| **🔴 Critical** | Fund theft, API key extraction, RCE | **$500-1000 USD** |
| **🟠 High** | Authentication bypass, unauthorized trading | **$200-500 USD** |
| **🟡 Medium** | Information disclosure, XSS, CSRF | **$100-200 USD** |
| **🟢 Low** | Security improvements, minor issues | **$50-100 USD or Recognition** |

**Note:** Bounty amounts are at maintainers' discretion based on:
- Severity and impact
- Quality of report
- Ease of exploitation
- Number of affected users

**Out of Scope (No Bounty):**
- Issues in third-party libraries (report to them directly)
- Social engineering attacks
- DoS/DDoS attacks
- Issues requiring physical access
- Previously known/reported vulnerabilities

---

## 🔐 Security Best Practices (For Users)

To keep your NOFX deployment secure:

### 1. API Key Management
```bash
# ✅ DO: Use environment variables
export BINANCE_API_KEY="your_key"
export BINANCE_SECRET_KEY="your_secret"

# ❌ DON'T: Hardcode in source files
api_key = "abc123..."  # NEVER DO THIS
```

### 2. Database Security
```bash
# ✅ Set proper permissions
chmod 600 nofx.db
chmod 600 config.json

# ❌ DON'T: Leave files world-readable
chmod 777 nofx.db  # NEVER DO THIS
```

### 3. Network Security
```bash
# ✅ Use firewall to restrict API access
# Only allow localhost to access API server
iptables -A INPUT -p tcp --dport 8080 -s 127.0.0.1 -j ACCEPT
iptables -A INPUT -p tcp --dport 8080 -j DROP

# ❌ DON'T: Expose API to public internet without authentication
```

### 4. Use Subaccounts
- Create dedicated Binance subaccount for trading
- Limit maximum balance
- Restrict withdrawal permissions
- Use IP whitelist

### 5. Test on Testnet First
- Hyperliquid: Use testnet mode
- Binance: Use testnet API (https://testnet.binancefuture.com)
- Never test with real funds initially

### 6. Regular Updates
```bash
# Check for updates regularly
git pull origin main
go build -o nofx

# Subscribe to security advisories
# Watch GitHub releases: https://github.com/NoFxAiOS/nofx/releases
```

---

## 🚨 Security Advisories

Past security advisories will be published here:

### 2025-XX-XX: [Title]
- **Severity:** [Critical/High/Medium/Low]
- **Affected Versions:** [x.x.x - x.x.x]
- **Fixed in:** [x.x.x]
- **Description:** [Brief description]
- **Mitigation:** [How to protect yourself]

*No security advisories have been published yet.*

---

## 🙏 Security Researchers Hall of Fame

We thank the following security researchers for responsibly disclosing vulnerabilities:

*No reports have been submitted yet. Be the first!*

---

## 📚 Additional Resources

**Security Documentation:**
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [Binance API Security Best Practices](https://www.binance.com/en/support/faq/360002502072)

**Audit Reports:**
- No third-party audits completed yet
- Self-audit checklist: [TODO: Add link]

---

## 📞 Contact

**For security issues ONLY:**
- 🐦 **Twitter DM:** [@Web3Tinkle](https://x.com/Web3Tinkle)

**For general questions:**
- See [CONTRIBUTING.md](CONTRIBUTING.md)
- Join [Telegram Community](https://t.me/nofx_dev_community)

---

**Thank you for helping keep NOFX secure!** 🔒

---





---



| ------- | ------------------ | -------------------- |


---










```markdown






```



---


|-------|----------|--------|


---



|----------|----------|--------|



---



```bash
export BINANCE_API_KEY="your_key"
export BINANCE_SECRET_KEY="your_secret"

```

```bash
chmod 600 nofx.db
chmod 600 config.json

```

```bash
iptables -A INPUT -p tcp --dport 8080 -s 127.0.0.1 -j ACCEPT
iptables -A INPUT -p tcp --dport 8080 -j DROP

```



```bash
git pull origin main
go build -o nofx

```

---





---




---




---

