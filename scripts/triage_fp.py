"""
=============================================================================
LLM-based False Positive Triage for Semgrep Findings
Day 20 — DevSecOps FPT FIM

Đọc semgrep-report.json → gọi Claude API để phân loại TP / FP / UNCERTAIN
→ in ra console + lưu markdown report

Usage:
  export ANTHROPIC_API_KEY=sk-ant-...
  python scripts/triage_fp.py semgrep-report.json
  python scripts/triage_fp.py semgrep-report.json --out triage-report.md
  python scripts/triage_fp.py semgrep-report.json --sarif semgrep-results.sarif

Yêu cầu:
  pip install anthropic
=============================================================================
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("ERROR: 'anthropic' package chưa được cài.")
    print("       pip install anthropic")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    rule_id: str
    message: str
    file_path: str
    line_start: int
    line_end: int
    code_snippet: str
    severity: str = "ERROR"
    cwe: str = ""
    owasp: str = ""

    # Filled in by LLM triage
    verdict: str = ""          # TRUE_POSITIVE | FALSE_POSITIVE | UNCERTAIN
    explanation: str = ""
    confidence: str = ""       # HIGH | MEDIUM | LOW


# ---------------------------------------------------------------------------
# Parser: Semgrep JSON format
# ---------------------------------------------------------------------------

def _read_lines(file_path: str, start: int, end: int, context: int = 3) -> str:
    """Đọc dòng từ source file với context xung quanh."""
    try:
        p = Path(file_path)
        if not p.exists():
            return "(source file not available)"
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        lo = max(0, start - context - 1)
        hi = min(len(lines), end + context)
        numbered = [
            f"{'>>>' if lo + i + 1 in range(start, end + 1) else '   '} "
            f"{lo + i + 1:4d} | {line}"
            for i, line in enumerate(lines[lo:hi])
        ]
        return "\n".join(numbered)
    except Exception:
        return "(could not read source)"


def parse_semgrep_json(path: str) -> list[Finding]:
    """Parse semgrep --json output."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    findings: list[Finding] = []

    for result in data.get("results", []):
        meta = result.get("extra", {}).get("metadata", {})
        start = result.get("start", {}).get("line", 1)
        end = result.get("end", {}).get("line", start)
        file_path = result.get("path", "")

        snippet = result.get("extra", {}).get("lines", "")
        if not snippet:
            snippet = _read_lines(file_path, start, end)

        findings.append(Finding(
            rule_id=result.get("check_id", "unknown"),
            message=result.get("extra", {}).get("message", ""),
            file_path=file_path,
            line_start=start,
            line_end=end,
            code_snippet=snippet,
            severity=result.get("extra", {}).get("severity", "ERROR"),
            cwe=meta.get("cwe", ""),
            owasp=meta.get("owasp", ""),
        ))

    return findings


def parse_sarif(path: str) -> list[Finding]:
    """Parse SARIF output từ semgrep --sarif."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    findings: list[Finding] = []

    for run in data.get("runs", []):
        rules_meta = {
            r["id"]: r
            for r in run.get("tool", {}).get("driver", {}).get("rules", [])
        }
        for result in run.get("results", []):
            rule_id = result.get("ruleId", "unknown")
            rule_meta = rules_meta.get(rule_id, {})
            msg = result.get("message", {}).get("text", "")

            locations = result.get("locations", [])
            if not locations:
                continue

            phys = locations[0].get("physicalLocation", {})
            file_path = (
                phys.get("artifactLocation", {}).get("uri", "")
                .replace("file:///", "")
                .replace("/", "\\")
            )
            region = phys.get("region", {})
            start = region.get("startLine", 1)
            end = region.get("endLine", start)
            snippet = region.get("snippet", {}).get("text", "") or _read_lines(file_path, start, end)

            props = rule_meta.get("properties", {})
            findings.append(Finding(
                rule_id=rule_id,
                message=msg,
                file_path=file_path,
                line_start=start,
                line_end=end,
                code_snippet=snippet,
                severity=result.get("level", "error").upper(),
                cwe=str(props.get("cwe", "")),
                owasp=str(props.get("owasp", "")),
            ))

    return findings


# ---------------------------------------------------------------------------
# LLM Triage
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = textwrap.dedent("""\
    Bạn là một security engineer senior chuyên phân tích kết quả SAST.
    Nhiệm vụ: phân loại từng finding của Semgrep là TRUE_POSITIVE, FALSE_POSITIVE, hoặc UNCERTAIN.

    Quy tắc phân loại:
    - TRUE_POSITIVE: Code thực sự có rủi ro SQL injection. User input có thể reach database mà không qua parameterized query.
    - FALSE_POSITIVE: Code an toàn. VD: hardcoded string, integer literal, đã có parameterized query riêng, hoặc ORM method.
    - UNCERTAIN: Không thể xác định không có context đầy đủ (VD: cần biết caller có validate input không).

    Trả lời PHẢI có định dạng:
    VERDICT: [TRUE_POSITIVE|FALSE_POSITIVE|UNCERTAIN]
    CONFIDENCE: [HIGH|MEDIUM|LOW]
    EXPLANATION: (2-3 câu tiếng Việt giải thích lý do)
    RECOMMENDATION: (1 câu hành động cụ thể nếu là TP hoặc UNCERTAIN)
""")

USER_PROMPT_TEMPLATE = textwrap.dedent("""\
    === Semgrep Finding ===
    Rule ID   : {rule_id}
    Severity  : {severity}
    File      : {file_path}:{line_start}
    CWE       : {cwe}
    Message   : {message}

    === Code Context ===
    ```python
    {code_snippet}
    ```

    Phân tích finding này.
""")


def triage_finding(client: anthropic.Anthropic, finding: Finding, model: str) -> Finding:
    """Gọi Claude API để triage một finding."""
    prompt = USER_PROMPT_TEMPLATE.format(
        rule_id=finding.rule_id,
        severity=finding.severity,
        file_path=finding.file_path,
        line_start=finding.line_start,
        cwe=finding.cwe or "CWE-89",
        message=finding.message,
        code_snippet=finding.code_snippet,
    )

    response = client.messages.create(
        model=model,
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()

    # Parse structured response
    verdict = "UNCERTAIN"
    confidence = "LOW"
    explanation = raw
    recommendation = ""

    for line in raw.splitlines():
        if line.startswith("VERDICT:"):
            verdict = line.split(":", 1)[1].strip()
        elif line.startswith("CONFIDENCE:"):
            confidence = line.split(":", 1)[1].strip()
        elif line.startswith("EXPLANATION:"):
            explanation = line.split(":", 1)[1].strip()
        elif line.startswith("RECOMMENDATION:"):
            recommendation = line.split(":", 1)[1].strip()

    finding.verdict = verdict
    finding.confidence = confidence
    finding.explanation = explanation
    if recommendation:
        finding.explanation += f"\n  → {recommendation}"

    return finding


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

VERDICT_EMOJI = {
    "TRUE_POSITIVE": "🔴",
    "FALSE_POSITIVE": "🟢",
    "UNCERTAIN": "🟡",
}


def generate_markdown_report(findings: list[Finding], input_file: str) -> str:
    tp = [f for f in findings if f.verdict == "TRUE_POSITIVE"]
    fp = [f for f in findings if f.verdict == "FALSE_POSITIVE"]
    un = [f for f in findings if f.verdict == "UNCERTAIN"]

    lines = [
        "# Semgrep LLM Triage Report",
        f"",
        f"**Source**: `{input_file}`  ",
        f"**Generated**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"**Total findings**: {len(findings)}",
        f"",
        "## Summary",
        f"",
        f"| Verdict | Count |",
        f"|---------|-------|",
        f"| 🔴 TRUE_POSITIVE  | {len(tp)} |",
        f"| 🟡 UNCERTAIN      | {len(un)} |",
        f"| 🟢 FALSE_POSITIVE | {len(fp)} |",
        f"",
    ]

    for section_label, section_findings in [
        ("TRUE POSITIVES — Cần fix ngay", tp),
        ("UNCERTAIN — Cần review thủ công", un),
        ("FALSE POSITIVES — Có thể bỏ qua", fp),
    ]:
        if not section_findings:
            continue
        lines.append(f"## {section_label}")
        lines.append("")
        for f in section_findings:
            emoji = VERDICT_EMOJI.get(f.verdict, "❓")
            lines += [
                f"### {emoji} `{f.rule_id}`",
                f"",
                f"- **File**: `{f.file_path}:{f.line_start}`",
                f"- **Severity**: {f.severity}",
                f"- **Confidence**: {f.confidence}",
                f"",
                f"**Code**:",
                f"```python",
                f.code_snippet.rstrip(),
                f"```",
                f"",
                f"**LLM Analysis**: {f.explanation}",
                f"",
                "---",
                "",
            ]

    return "\n".join(lines)


def print_summary(findings: list[Finding]) -> None:
    tp = sum(1 for f in findings if f.verdict == "TRUE_POSITIVE")
    fp = sum(1 for f in findings if f.verdict == "FALSE_POSITIVE")
    un = sum(1 for f in findings if f.verdict == "UNCERTAIN")

    print("\n" + "=" * 60)
    print("  SEMGREP TRIAGE SUMMARY")
    print("=" * 60)
    print(f"  🔴 TRUE_POSITIVE  : {tp}")
    print(f"  🟡 UNCERTAIN      : {un}")
    print(f"  🟢 FALSE_POSITIVE : {fp}")
    print(f"  Total             : {len(findings)}")
    print("=" * 60)

    if tp > 0:
        print("\n  ⚠️  Findings cần fix:")
        for f in findings:
            if f.verdict == "TRUE_POSITIVE":
                print(f"    • {f.file_path}:{f.line_start} — {f.rule_id}")

    if un > 0:
        print("\n  ⚠️  Findings cần review thủ công:")
        for f in findings:
            if f.verdict == "UNCERTAIN":
                print(f"    • {f.file_path}:{f.line_start} — {f.rule_id}")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Triage Semgrep findings với Claude LLM"
    )
    parser.add_argument(
        "input",
        help="semgrep-report.json hoặc semgrep-results.sarif",
    )
    parser.add_argument(
        "--out", "-o",
        default="triage-report.md",
        help="Output markdown file (default: triage-report.md)",
    )
    parser.add_argument(
        "--sarif",
        action="store_true",
        help="Input là SARIF format (thay vì JSON)",
    )
    parser.add_argument(
        "--model",
        default="claude-haiku-4-5-20251001",
        help="Claude model ID (default: claude-haiku-4-5-20251001 — nhanh + rẻ cho triage)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse findings nhưng không gọi LLM (test parser)",
    )
    args = parser.parse_args()

    # Parse input
    input_path = args.input
    if not Path(input_path).exists():
        print(f"ERROR: File không tìm thấy: {input_path}")
        sys.exit(1)

    print(f"[triage] Đang đọc: {input_path}")
    if args.sarif or input_path.endswith(".sarif"):
        findings = parse_sarif(input_path)
    else:
        findings = parse_semgrep_json(input_path)

    print(f"[triage] Tìm thấy {len(findings)} finding(s)")

    if not findings:
        print("[triage] Không có finding nào. Pipeline sạch!")
        Path(args.out).write_text("# Semgrep Triage\n\nNo findings.\n", encoding="utf-8")
        return

    if args.dry_run:
        print("[triage] --dry-run: bỏ qua LLM call")
        for f in findings:
            print(f"  {f.rule_id} @ {f.file_path}:{f.line_start}")
        return

    # LLM Triage
    import os
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY chưa được set")
        print("       export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    print(f"[triage] Model: {args.model}")
    print(f"[triage] Đang triage {len(findings)} finding(s)...")

    for i, finding in enumerate(findings, 1):
        print(f"  [{i}/{len(findings)}] {finding.rule_id} @ {finding.file_path}:{finding.line_start} ...", end=" ", flush=True)
        try:
            triage_finding(client, finding, args.model)
            print(f"{VERDICT_EMOJI.get(finding.verdict, '?')} {finding.verdict}")
        except Exception as e:
            finding.verdict = "UNCERTAIN"
            finding.confidence = "LOW"
            finding.explanation = f"LLM error: {e}"
            print(f"⚠️  ERROR: {e}")

    # Output
    print_summary(findings)
    report = generate_markdown_report(findings, input_path)
    Path(args.out).write_text(report, encoding="utf-8")
    print(f"[triage] Report saved → {args.out}")

    # Exit code: 1 nếu có TRUE_POSITIVE (để CI có thể dùng làm gate)
    tp_count = sum(1 for f in findings if f.verdict == "TRUE_POSITIVE")
    if tp_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
