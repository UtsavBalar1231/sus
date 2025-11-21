# Claude Agent SDK Documentation Scraper

Comprehensive SUS configuration for scraping Claude Agent SDK documentation, tutorials, and blog posts from 86 different URLs across multiple platforms.

## 📊 Overview

| Config File | URLs | Auth Required | Scrape Time | Description |
|-------------|------|---------------|-------------|-------------|
| `01-anthropic-official.yaml` | 16 | No | 10-15 min | Official Anthropic docs and blog |
| `02-blog-sites.yaml` | 54 | No | 30-45 min | Public technical blogs |
| `03-documentation-sites.yaml` | 10 | No | 15-20 min | Technical documentation sites |
| `04-npm-package.yaml` | 1 | No | <1 min | NPM package registry |
| `05-medium-test.yaml` | 10 | No | 2-3 min | Test Medium for paywalls |
| `06-medium-authenticated.yaml` | 10 | **Yes** | 5-10 min | Medium with authentication |
| `07-substack-test.yaml` | 5 | No | 1-2 min | Test Substack for subscribers |
| `08-substack-authenticated.yaml` | 5 | **Yes** | 3-5 min | Substack with authentication |
| `99-all-public-urls.yaml` | 76 | No | 1-2 hours | All public URLs combined |

**Total Coverage:** 86 URLs | **Success Rate:** ~88% (76 public, 10 with auth)

---

## 🚀 Quick Start

### Prerequisites

```bash
# Install SUS with JavaScript rendering support
uv sync --group js

# Install Chromium browser (required for SPAs)
uv run playwright install chromium

# Verify installation
uv run sus --version
```

### Basic Usage

```bash
# 1. Start with public URLs (easiest)
uv run sus scrape --config examples/claude-agent-sdk/99-all-public-urls.yaml

# 2. Test specific category
uv run sus scrape --config examples/claude-agent-sdk/01-anthropic-official.yaml

# 3. Test with limited pages
uv run sus scrape --config examples/claude-agent-sdk/02-blog-sites.yaml --max-pages 10

# 4. Dry run to preview
uv run sus scrape --config examples/claude-agent-sdk/03-documentation-sites.yaml --dry-run
```

### With Resume (Recommended for Large Scrapes)

```bash
# Enable checkpoint/resume in config (already enabled)
uv run sus scrape --config examples/claude-agent-sdk/99-all-public-urls.yaml --resume

# If scrape crashes or stops, resume from checkpoint
uv run sus scrape --config examples/claude-agent-sdk/99-all-public-urls.yaml --resume
```

---

## 📁 Configuration Files Guide

### 01-anthropic-official.yaml

**Official Anthropic Documentation**

- **What:** docs.claude.com, platform.claude.com, engineering blog, news
- **JavaScript:** Required (React/Next.js SPAs)
- **Sitemap:** Enabled with auto-discovery
- **Best For:** Most authoritative Claude Agent SDK information

**Usage:**
```bash
uv run sus scrape --config examples/claude-agent-sdk/01-anthropic-official.yaml
```

**Expected Output:**
```
output/anthropic-official/
├── docs/
│   ├── agent-sdk/
│   ├── claude-code/
│   └── release-notes/
└── assets/
```

---

### 02-blog-sites.yaml

**Public Blog Articles**

- **What:** 54 blog posts from skywork.ai, datacamp.com, dev.to, AWS, etc.
- **JavaScript:** Optional (most are static HTML)
- **Rate Limiting:** Conservative (2 req/s)
- **Best For:** Tutorials, guides, and real-world examples

**Usage:**
```bash
uv run sus scrape --config examples/claude-agent-sdk/02-blog-sites.yaml
```

**Note:** skywork.ai has 8 URLs - uses per-domain concurrency limit.

---

### 03-documentation-sites.yaml

**Technical Documentation**

- **What:** LangChain docs, ClickHouse docs, docs.rs, etc.
- **JavaScript:** Enabled for Docusaurus/SPA-based docs
- **Depth:** 5 levels (follows internal docs links)
- **Best For:** Integration guides and API references

**Usage:**
```bash
uv run sus scrape --config examples/claude-agent-sdk/03-documentation-sites.yaml
```

---

### 04-npm-package.yaml

**NPM Package Page**

- **What:** Single npmjs.com package page
- **JavaScript:** Not required
- **Rate Limiting:** Very conservative (1 req/s)
- **Best For:** Package metadata and README

**Usage:**
```bash
uv run sus scrape --config examples/claude-agent-sdk/04-npm-package.yaml
```

---

### 05-medium-test.yaml + 06-medium-authenticated.yaml

**Medium Articles (Paywall Testing)**

**Step 1: Test for Paywalls**
```bash
uv run sus scrape --config examples/claude-agent-sdk/05-medium-test.yaml --dry-run --verbose
```

**Check output for:**
- "member-only story"
- "read the full story"
- Content ending with "..."
- Very short content (<500 chars)

**Step 2: If Paywalled, Use Authentication**

See [Cookie Extraction Guide](#-cookie-extraction-guide) below.

```bash
# Edit 06-medium-authenticated.yaml with your cookies
uv run sus scrape --config examples/claude-agent-sdk/06-medium-authenticated.yaml
```

---

### 07-substack-test.yaml + 08-substack-authenticated.yaml

**Substack Articles (Subscriber Testing)**

**Step 1: Test for Subscriber-Only Content**
```bash
uv run sus scrape --config examples/claude-agent-sdk/07-substack-test.yaml --dry-run --verbose
```

**Check output for:**
- "This post is for paid subscribers"
- "Subscribe to unlock"
- Content ending with free trial CTA
- Very short content (<300 chars)

**Step 2: If Subscriber-Only, Use Authentication**

See [Cookie Extraction Guide](#-cookie-extraction-guide) below.

**Note:** Each Substack publication has independent subscriptions. You may need to:
- Subscribe to multiple publications separately
- Use free trials (typically 7 days)
- Create separate configs per publication if cookies differ

```bash
# Edit 08-substack-authenticated.yaml with your cookies
uv run sus scrape --config examples/claude-agent-sdk/08-substack-authenticated.yaml
```

---

### 99-all-public-urls.yaml

**Combined Configuration (76 Public URLs)**

- **What:** All URLs that don't require authentication
- **Includes:** Configs 01-04 combined
- **Excludes:** Medium and Substack (test those separately)
- **Best For:** One-stop scraping of all public content

**Usage:**
```bash
# Full scrape with resume
uv run sus scrape --config examples/claude-agent-sdk/99-all-public-urls.yaml --resume

# Monitor progress in another terminal
watch -n 5 'tail -n 20 output/claude-agent-sdk-complete/.all_public_checkpoint.json'
```

**Performance:**
- Time: 1-2 hours
- Memory: ~1-2 GB RAM
- Disk: ~100-150 MB output
- Network: ~200-300 MB download

---

## 🍪 Cookie Extraction Guide

### Why Cookies?

Medium and Substack use paywalls/subscriptions. To scrape member-only content, you need to extract authentication cookies from your logged-in browser session.

### For Medium

**Step-by-Step:**

1. **Login to Medium**
   - Open https://medium.com in Chrome/Firefox
   - Sign in to your Medium account (or start free trial)

2. **Open DevTools**
   - Press `F12` or Right-click → Inspect
   - Navigate to: **Application** tab → **Storage** → **Cookies** → `https://medium.com`

3. **Find Required Cookies**

   Look for these cookies:

   | Cookie Name | Example Value | Description |
   |-------------|---------------|-------------|
   | `uid` | `lo_abc123...xyz` | User ID (long string) |
   | `sid` | `1:abc123:def456...` | Session ID |

4. **Copy Cookie Values**

   Click each cookie and copy the **Value** field.

5. **Update Config File**

   Edit `examples/claude-agent-sdk/06-medium-authenticated.yaml`:

   ```yaml
   authentication:
     type: cookie
     cookies:
       - name: uid
         value: "lo_YOUR_ACTUAL_UID_VALUE_HERE"
         domain: .medium.com

       - name: sid
         value: "YOUR_ACTUAL_SID_VALUE_HERE"
         domain: .medium.com
   ```

6. **Test Authentication**

   ```bash
   # Test with single URL first
   uv run sus scrape --config 06-medium-authenticated.yaml --max-pages 1 --verbose
   ```

**Security Notes:**
- Never commit files with real cookie values to version control
- Cookies expire after ~30 days
- Keep cookies private (they grant access to your account)
- Consider using environment variables:
  ```yaml
  value: "${MEDIUM_UID_COOKIE}"
  ```

---

### For Substack

**Step-by-Step:**

1. **Subscribe to Publications**

   Each Substack is independent. Subscribe to:
   - https://aimaker.substack.com
   - https://responseawareness.substack.com
   - https://blog.sshh.io

   Or start free trials (usually 7 days).

2. **Login to Substack**

   - Click magic link from email
   - Verify you're logged in (see profile icon)

3. **Open DevTools**

   - Press `F12`
   - Navigate to: **Application** → **Cookies** → `https://*.substack.com`

4. **Find Required Cookie**

   | Cookie Name | Example Value | Description |
   |-------------|---------------|-------------|
   | `substack.sid` | `s%3A1234abcd-5678...` | Session ID |

5. **Copy Cookie Value**

   Copy the entire value of `substack.sid`.

6. **Update Config File**

   Edit `examples/claude-agent-sdk/08-substack-authenticated.yaml`:

   ```yaml
   authentication:
     type: cookie
     cookies:
       - name: substack.sid
         value: "YOUR_ACTUAL_SUBSTACK_SID_VALUE_HERE"
         domain: .substack.com
   ```

7. **Test Authentication**

   ```bash
   uv run sus scrape --config 08-substack-authenticated.yaml --max-pages 1 --verbose
   ```

**Substack-Specific Notes:**
- Each publication has independent subscriptions
- Cookies should work across all `*.substack.com` domains
- Custom domains (e.g., `blog.sshh.io`) may need separate cookies
- Free trials are typically 7 days

---

## 🔧 Advanced Usage

### Customizing Configurations

**Override Output Directory:**
```bash
uv run sus scrape --config 01-anthropic-official.yaml --output /custom/path
```

**Adjust Concurrency:**
```yaml
# In config file
crawling:
  concurrency:
    max_concurrent: 20  # Increase for faster scraping
    per_domain: 5       # Higher per-domain limit
```

**Disable JavaScript Rendering:**
```yaml
# Faster but may miss dynamic content
crawling:
  javascript:
    enabled: false
```

**Change Rate Limiting:**
```yaml
crawling:
  rate_limiting:
    delay_between_requests: 1.0  # Slower, more respectful
    burst: 3
```

---

### Monitoring Progress

**Watch Checkpoint File:**
```bash
watch -n 5 'wc -l output/claude-agent-sdk-complete/.all_public_checkpoint.json'
```

**Count Scraped Pages:**
```bash
find output/claude-agent-sdk-complete/docs -name "*.md" | wc -l
```

**Check Disk Usage:**
```bash
du -sh output/claude-agent-sdk-complete/
```

**Tail Logs:**
```bash
# If you're redirecting output to a log file
tail -f scrape.log
```

---

### Benchmarking

**Test JavaScript Rendering Performance:**
```bash
python benchmarks/benchmark_js_rendering.py

# Compare different context pool sizes
python benchmarks/benchmark_js_rendering.py --compare-pools
```

**Expected Performance:**
- **HTTP-only:** 25-50 pages/sec
- **With JS rendering:** 5-10 pages/sec (3-5x slower)
- **Memory usage:** 500-800 MB with Playwright
- **Network:** ~2-5 MB/min download

---

## 🐛 Troubleshooting

### Common Issues

#### 1. Empty Content or "Loading..." Text

**Cause:** JavaScript rendering not working or wait timeout too short.

**Solution:**
```yaml
crawling:
  javascript:
    enabled: true
    wait_for: networkidle  # Change to "networkidle" for more thorough waiting
    wait_timeout_ms: 30000  # Increase timeout
```

#### 2. 429 Too Many Requests

**Cause:** Rate limiting by server.

**Solution:**
```yaml
crawling:
  rate_limiting:
    delay_between_requests: 2.0  # Increase delay (slower but safer)
    burst: 2
  concurrency:
    per_domain: 1  # Lower per-domain concurrency
```

#### 3. Still Getting Paywalled Content

**Cause:** Cookies expired or incorrect.

**Solution:**
- Re-extract cookies (they expire after ~30 days)
- Verify you're logged in to Medium/Substack in browser
- Check cookie domain is correct (`.medium.com` with leading dot)
- Ensure subscription is active

#### 4. Memory Errors

**Cause:** Too many browser contexts or large page cache.

**Solution:**
```yaml
crawling:
  javascript:
    context_pool_size: 3  # Reduce from 5
```

Or disable JavaScript rendering if not needed.

#### 5. Chromium Not Found

**Cause:** Playwright browser not installed.

**Solution:**
```bash
uv run playwright install chromium
```

#### 6. Permission Denied / 403 Errors

**Cause:** Anti-bot measures or IP blocking.

**Solution:**
- Enable JavaScript rendering (mimics real browser)
- Use realistic headers (already configured)
- Increase delay between requests
- Check site's robots.txt for restrictions

#### 7. Checkpoint Not Working

**Cause:** Checkpoint file corrupted or config changed.

**Solution:**
```bash
# Reset checkpoint and start fresh
uv run sus scrape --config your-config.yaml --reset-checkpoint

# Or manually delete checkpoint
rm output/your-output-dir/.sus_checkpoint.json
```

---

## 📊 Expected Results

### Output Structure

```
output/
├── anthropic-official/
│   ├── docs/
│   │   ├── api/
│   │   │   └── agent-sdk/
│   │   │       └── index.md
│   │   ├── docs/
│   │   │   ├── agent-sdk/
│   │   │   │   └── index.md
│   │   │   └── claude-code/
│   │   │       └── index.md
│   │   └── release-notes/
│   │       └── index.md
│   ├── engineering/
│   │   └── building-agents-with-the-claude-agent-sdk.md
│   ├── news/
│   │   └── claude-sonnet-4-5.md
│   └── assets/
│       ├── images/
│       └── css/
├── claude-agent-sdk-blogs/
│   └── docs/
│       ├── skywork.ai/
│       ├── aankitroy.com/
│       └── ...
└── claude-agent-sdk-complete/  # All public URLs
    ├── docs/
    └── assets/
```

### File Format

Each scraped page becomes a Markdown file with frontmatter:

```markdown
---
title: "Building Agents with the Claude Agent SDK"
url: "https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk"
scraped_at: "2025-01-15T10:30:00Z"
---

# Building Agents with the Claude Agent SDK

[Content in clean Markdown format...]
```

### Statistics

**After Full Scrape (99-all-public-urls.yaml):**

- **Total pages:** ~80-120 (depends on depth and link following)
- **Markdown files:** ~80-120 .md files
- **Assets:** ~200-500 images + CSS files
- **Disk usage:** ~100-150 MB
- **Scrape time:** 1-2 hours (with JS rendering)

---

## 💡 Tips & Best Practices

### 1. Start Small

Test with limited pages before full scrape:
```bash
uv run sus scrape --config your-config.yaml --max-pages 5 --verbose
```

### 2. Use Checkpoints

Always enable checkpoints for large scrapes:
```yaml
crawling:
  checkpoint:
    enabled: true
    checkpoint_interval_pages: 10
```

### 3. Monitor Resources

Keep an eye on:
- Memory usage (`htop` or Activity Monitor)
- Disk space (`df -h`)
- Network bandwidth

### 4. Test Medium/Substack First

Use test configs before running authenticated scrapes:
```bash
# Test first
uv run sus scrape --config 05-medium-test.yaml --dry-run

# Then authenticate if needed
uv run sus scrape --config 06-medium-authenticated.yaml
```

### 5. Respect Rate Limits

Use conservative settings:
- 0.5-1.0 second delay between requests
- Lower per-domain concurrency for single-domain scrapes
- Respect robots.txt (enabled by default)

### 6. Handle Authentication Securely

- Never commit configs with real cookie values
- Use environment variables: `value: "${COOKIE_VALUE}"`
- Rotate cookies when they expire (~30 days)

### 7. Parallel Scraping

Run multiple configs in parallel (different terminals):
```bash
# Terminal 1
uv run sus scrape --config 01-anthropic-official.yaml

# Terminal 2
uv run sus scrape --config 02-blog-sites.yaml

# Terminal 3
uv run sus scrape --config 03-documentation-sites.yaml
```

---

## 🤝 Contributing

Found a broken URL or want to add more? Edit the configs and submit a PR!

**Checklist for New URLs:**
- [ ] Test URL is accessible (not 404)
- [ ] Check if authentication required
- [ ] Verify content renders correctly (JS needed?)
- [ ] Add to appropriate config file
- [ ] Update URL counts in README
- [ ] Test scrape with `--max-pages 1`

---

## 📚 Additional Resources

- **SUS Documentation:** [Main README](../../README.md)
- **CLAUDE.md Guide:** [Project documentation](../../CLAUDE.md)
- **JavaScript Rendering Guide:** [docs/guides/javascript-rendering.md](../../docs/guides/javascript-rendering.md)
- **Example Configs:** [examples/](../)
- **Benchmarks:** [benchmarks/](../../benchmarks/)

---

## 📄 License

Same as parent SUS project. These configs are examples for educational use.

---

## ⚠️ Legal & Ethical Considerations

- **Respect robots.txt:** Enabled by default in all configs
- **Rate limiting:** Conservative delays to avoid overloading servers
- **Terms of Service:** Review each site's ToS before scraping
- **Authentication:** Only use cookies from your own accounts
- **Personal Use:** These configs are for personal documentation archival
- **Commercial Use:** Check licensing before using scraped content commercially

**Platforms with specific policies:**
- **Medium:** [Medium ToS](https://policy.medium.com/medium-terms-of-service-9db0094a1e0f) - Personal use generally acceptable
- **Substack:** Per-publication policies vary
- **Anthropic:** Documentation is public, but check [Terms](https://www.anthropic.com/legal/terms)

**Best Practice:** When in doubt, contact the site owner for permission.

---

## 🆘 Getting Help

**Issues with configs?**
- Check [Troubleshooting](#-troubleshooting) section above
- Review SUS [CLAUDE.md](../../CLAUDE.md) for detailed architecture
- Open an issue: [GitHub Issues](https://github.com/UtsavBalar1231/sus/issues)

**Questions about SUS itself?**
- Main documentation: [README.md](../../README.md)
- Example configs: [examples/](../)
- Test suite: [tests/](../../tests/)

**Cookie extraction problems?**
- Re-read [Cookie Extraction Guide](#-cookie-extraction-guide)
- Verify you're logged in to the correct account
- Check DevTools Console for error messages
- Try incognito mode to test authentication

---

**Happy Scraping! 🚀**

*Last updated: 2025-01-15*
