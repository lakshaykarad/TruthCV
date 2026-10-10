from __future__ import annotations

import sys
import time
from pathlib import Path

import requests

BASE_URL = "http://localhost:8003"
EMAIL = "test@truthcv.com"

OUTPUT_DIR = Path("output") / "api_test"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ── Sample JD (fake, for testing) ─────────────────────────────
JD_TEXT = """
Backend Engineer at Razorpay (Bangalore)

We are hiring a backend engineer to work on our payments infrastructure.

Requirements:
- 2+ years of experience with Python
- Strong knowledge of FastAPI or Django
- Experience with PostgreSQL and Redis
- Familiarity with Docker and containerized deployments
- Understanding of REST API design and JWT authentication

Nice to have:
- Experience with AWS or GCP
- Knowledge of payment systems or fintech
- Exposure to Kubernetes

Responsibilities:
- Design and build REST APIs for payment services
- Write unit and integration tests
- Collaborate with frontend and product teams
- Participate in code reviews

Qualifications:
- Bachelor's degree in Computer Science or equivalent
- Strong problem-solving skills
"""

QUESTIONS = [
    "Why are you interested in this role?",
    "Why should we hire you?",
    "What is your biggest strength for this job?",
]


# ── Pretty printing ───────────────────────────────────────────
def banner(n: int, title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  [{n}] {title}")
    print("=" * 70)


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def fail(msg: str) -> None:
    print(f"  ✗ {msg}")


def info(msg: str) -> None:
    print(f"    {msg}")


# ── Test steps ────────────────────────────────────────────────
def test_health() -> bool:
    banner(1, "GET /health")
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=10)
        r.raise_for_status()
        data = r.json()
        ok(f"status = {data.get('status')}")
        for name, state in (data.get("checks") or {}).items():
            info(f"{name}: {state}")
        return data.get("status") in ("ok", "degraded")
    except Exception as e:
        fail(f"Health check failed: {e}")
        return False


def test_upload(pdf_path: str) -> int | None:
    banner(2, "POST /resume/upload")
    try:
        with open(pdf_path, "rb") as f:
            files = {"file": (Path(pdf_path).name, f, "application/pdf")}
            r = requests.post(
                f"{BASE_URL}/resume/upload",
                params={"email": EMAIL},
                files=files,
                timeout=300,
            )
        if r.status_code != 200:
            fail(f"HTTP {r.status_code}: {r.text[:300]}")
            return None
        data = r.json()
        resume_id = data.get("resume_id")
        ok(f"uploaded: resume_id={resume_id} chunks={data.get('chunks')}")
        info(f"name  = {data.get('name')}")
        info(f"email = {data.get('email')}")
        return resume_id
    except Exception as e:
        fail(f"Upload failed: {e}")
        return None


def test_current() -> bool:
    banner(3, "GET /resume/current")
    try:
        r = requests.get(
            f"{BASE_URL}/resume/current",
            params={"email": EMAIL},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        json_data = data.get("json_data") or {}
        ok(f"resume_id = {data.get('resume_id')}")
        info(f"filename = {data.get('filename')}")
        info(f"skills   = {len(json_data.get('skills') or [])} items")
        info(f"projects = {len(json_data.get('projects') or [])} items")
        return True
    except Exception as e:
        fail(f"Fetch current failed: {e}")
        return False


def test_score() -> bool:
    banner(4, "POST /generate/score")
    try:
        r = requests.post(
            f"{BASE_URL}/generate/score",
            params={"email": EMAIL},
            json={"jd_text": JD_TEXT},
            timeout=120,
        )
        if r.status_code == 404:
            fail("Endpoint not implemented yet (404). Skipping.")
            return False
        r.raise_for_status()
        data = r.json()
        ok(f"match_percent = {data.get('match_percent')}%")
        info(f"should_apply = {data.get('should_apply')}")
        info(f"matched = {data.get('matched')}")
        info(f"missing = {data.get('missing')}")
        return True
    except Exception as e:
        fail(f"Score failed: {e}")
        return False


def test_generate_resume() -> str | None:
    banner(5, "POST /generate/resume")
    try:
        r = requests.post(
            f"{BASE_URL}/generate/resume",
            params={"email": EMAIL},
            json={"jd_text": JD_TEXT, "user_instructions": ""},
            timeout=300,
        )
        if r.status_code != 200:
            fail(f"HTTP {r.status_code}: {r.text[:300]}")
            return None
        data = r.json()
        pdf_url = data.get("download_url")
        tailored = data.get("tailored") or {}
        ok(f"tailored_title = {tailored.get('tailored_title')}")
        info(f"summary chars = {len(tailored.get('summary') or '')}")
        info(f"skill groups  = {list((tailored.get('skills') or {}).keys())}")
        info(f"projects      = {len(tailored.get('projects') or [])}")
        info(f"pdf path      = {data.get('pdf_path')}")
        return pdf_url
    except Exception as e:
        fail(f"Generate resume failed: {e}")
        return None


def test_generate_letter() -> str | None:
    banner(6, "POST /generate/cover-letter")
    try:
        r = requests.post(
            f"{BASE_URL}/generate/cover-letter",
            params={"email": EMAIL},
            json={"jd_text": JD_TEXT},
            timeout=300,
        )
        if r.status_code != 200:
            fail(f"HTTP {r.status_code}: {r.text[:300]}")
            return None
        data = r.json()
        pdf_url = data.get("download_url")
        ok(f"word_count = {data.get('word_count')}")
        info(f"pdf path   = {data.get('pdf_path')}")
        info("preview:")
        preview = (data.get("cover_letter") or "")[:250]
        print(f"\n{preview}...\n")
        return pdf_url
    except Exception as e:
        fail(f"Generate cover letter failed: {e}")
        return None


def test_answers() -> bool:
    banner(7, "POST /generate/answers")
    try:
        r = requests.post(
            f"{BASE_URL}/generate/answers",
            params={"email": EMAIL},
            json={"jd_text": JD_TEXT, "questions": QUESTIONS},
            timeout=300,
        )
        if r.status_code != 200:
            fail(f"HTTP {r.status_code}: {r.text[:300]}")
            return False
        data = r.json()
        answers = data.get("answers") or []
        ok(f"answered {len(answers)} questions")
        for i, item in enumerate(answers, 1):
            print(f"\n    Q{i}: {item['question']}")
            print(f"    A{i}: {item['answer'][:250]}")
        return True
    except Exception as e:
        fail(f"Answers failed: {e}")
        return False


def test_download(pdf_url: str | None, tag: str) -> bool:
    if not pdf_url:
        fail(f"No URL to download for {tag}")
        return False
    banner(8, f"GET {pdf_url}  ({tag})")
    try:
        r = requests.get(f"{BASE_URL}{pdf_url}", timeout=30)
        if r.status_code != 200:
            fail(f"HTTP {r.status_code}")
            return False
        # Save to disk
        filename = pdf_url.split("/")[-1]
        out = OUTPUT_DIR / filename
        out.write_bytes(r.content)
        ok(f"saved → {out.absolute()}  ({len(r.content) // 1024} KB)")
        return True
    except Exception as e:
        fail(f"Download failed: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────
def main(pdf_path: str) -> None:
    if not Path(pdf_path).exists():
        print(f"File not found: {pdf_path}")
        sys.exit(1)

    print(f"\nBase URL: {BASE_URL}")
    print(f"PDF:      {pdf_path}")
    print(f"Email:    {EMAIL}")
    print(f"Outputs:  {OUTPUT_DIR.absolute()}")

    start = time.time()
    results: dict[str, bool] = {}

    results["health"] = test_health()
    resume_id = test_upload(pdf_path)
    results["upload"] = resume_id is not None

    if not results["upload"]:
        print("\nCannot continue: upload failed.")
        sys.exit(1)

    results["current"] = test_current()
    results["score"] = test_score()

    resume_url = test_generate_resume()
    results["generate_resume"] = resume_url is not None

    letter_url = test_generate_letter()
    results["generate_letter"] = letter_url is not None

    results["answers"] = test_answers()
    results["download_resume"] = test_download(resume_url, "resume")
    results["download_letter"] = test_download(letter_url, "cover letter")

    # ── Summary ──────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"  SUMMARY  ({time.time() - start:.1f}s total)")
    print("=" * 70)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for name, ok_ in results.items():
        mark = "✓" if ok_ else "✗"
        print(f"  {mark}  {name}")
    print(f"\n  {passed}/{total} passed")
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.test_api <resume.pdf>")
        sys.exit(1)
    main(sys.argv[1])