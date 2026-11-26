#!/usr/bin/env python3
"""Check the repo for secrets and personal data before committing or publishing.

    python3 tools/check_secrets.py

Scans every file git tracks or would add (ignored files are skipped) for API keys, tokens,
private keys, passwords, claude.ai artifact and scheduled-task IDs, and email addresses.
Add your own words to `.private-words` (one per line, git-ignored), such as your street or
surname, and they're flagged too. Exits 1 if anything is found.
"""
import pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

PATTERNS = {
    "Anthropic API key": r"sk-ant-[A-Za-z0-9_-]{10,}",
    "OpenAI-style key": r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}",
    "GitHub token": r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})",
    "AWS access key": r"\bAKIA[0-9A-Z]{16}\b",
    "Google API key": r"\bAIza[0-9A-Za-z_-]{35}\b",
    "Slack token": r"\bxox[abposr]-[A-Za-z0-9-]{10,}",
    "Stripe live key": r"\b[rs]k_live_[A-Za-z0-9]{10,}",
    "Supabase key": r"\bsb_(?:secret|publishable)_[A-Za-z0-9_-]{10,}",
    "JSON web token": r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    "private key": r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----",
    "password or secret in code": r"(?i)\b(?:api[_-]?key|secret|token|passw(?:or)?d)\b\s*[:=]\s*[\"'][^\"'\s]{12,}[\"']",
    "claude.ai artifact link": r"claude\.ai/artifact/[A-Za-z0-9]{8,}",
    "scheduled-task ID": r"\btrig_[A-Za-z0-9]{16,}",
    "session link": r"claude\.ai/code/session_[A-Za-z0-9]+",
    "email address": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b",
}
ALLOWED_EMAIL = re.compile(r"@(?:example\.(?:com|org|net)|users\.noreply\.github\.com)$|^noreply@", re.I)
FORBIDDEN_FILES = re.compile(r"(^|/)(\.env(\..*)?|\.dev\.vars|.*\.pem|.*\.key|id_(rsa|ed25519|ecdsa)|credentials\.json|\.private-words)$")
SKIP = {"LICENSE"}  # standard license text


def files():
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return sorted({f for f in out.split("\0") if f and (ROOT / f).is_file()})


def main():
    private = []
    pw = ROOT / ".private-words"
    if pw.exists():
        private = [w.strip() for w in pw.read_text().splitlines() if w.strip() and not w.startswith("#")]
    found = []
    for f in files():
        if FORBIDDEN_FILES.search(f):
            found.append((f, 0, "file that usually holds secrets", f))
        if f in SKIP:
            continue
        try:
            text = (ROOT / f).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary
        for n, line in enumerate(text.splitlines(), 1):
            for name, pat in PATTERNS.items():
                for m in re.finditer(pat, line):
                    if name == "email address" and ALLOWED_EMAIL.search(m.group(0)):
                        continue
                    found.append((f, n, name, m.group(0)))
            low = line.lower()
            for w in private:
                if w.lower() in low:
                    found.append((f, n, "private word", w))
    for f, n, name, hit in found:
        shown = hit if len(hit) <= 12 else hit[:8] + "…"
        print(f"{f}:{n}: {name}: {shown}")
    print(f"{len(found)} problem(s) found" if found else "No secrets or personal data found.")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
