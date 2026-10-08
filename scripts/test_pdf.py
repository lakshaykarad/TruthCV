"""
Test pdf_writer.py without calling the LLM.
Uses hardcoded tailored JSON. Zero Groq tokens.

Run:
    python -m scripts.test_pdf
"""

import logging
from pathlib import Path

from app.pipeline.pdf_writer import render_resume_pdf, render_cover_letter_pdf

logging.basicConfig(level=logging.INFO)

# ─── FAKE TAILORED DATA ────────────────────────────────────────
# Copy this shape from a real generate_tailored_resume() run.
# Change the values to test edge cases (missing phone, no projects, etc).
FAKE_TAILORED = {
    "name": "Rahul Sharma",
    "tailored_title": "Android + Backend Developer",
    "email": "sharmarahul7@gmail.com",
    "phone": "7851234567",
    "location": "Noida",
    "website": "linkedin.com/in/Rahul-Sharma",
    "links": [
        "github.com/RahulSharma",
        "leetcode.com/u/SharmaRahul7",
        "RahulSharma.vercel.app",
    ],
    "summary": (
        "Android and backend developer experienced in building Kotlin/Jetpack "
        "Compose mobile apps and FastAPI services. Delivered RapidLink, a routing "
        "platform with JWT-secured FastAPI backend and Compose UI, and URL-Shorten, "
        "a high-throughput URL shortener using PostgreSQL, Redis, Docker and Nginx."
    ),
    "skills": {
        "Backend": [
            "FastAPI", "Python", "PostgreSQL", "REST API design", "Docker",
            "Redis", "JWT / OAuth2", "SQLAlchemy", "Alembic", "Uvicorn",
            "Nginx", "bcrypt", "Locust",
        ],
        "Android": [
            "Kotlin", "Jetpack Compose", "Retrofit", "Kotlin Flow",
            "Coroutines/Flow", "MVVM", "Clean Architecture", "Hilt",
            "Room", "WorkManager", "Foreground Services",
        ],
    },
    "projects": [
        {
            "name": "RapidLink",
            "tech": ["Kotlin", "Jetpack Compose", "FastAPI", "PostgreSQL",
                     "OSRM", "Docker", "MapLibre"],
            "links": [
                "rahulsharma.vercel.app",
                "github.com/RahulSharma/RapidLink",
            ],
            "description": [
                "Built a FastAPI service on a self-hosted OSRM engine (Dockerized) "
                "that serves multiple route alternatives with ETAs",
                "Implemented JWT authentication (signup, login, token refresh) "
                "using the OAuth2 password flow",
                "Modeled users and profiles in PostgreSQL with SQLAlchemy and "
                "versioned schema changes via Alembic migrations",
                "Designed a traffic-simulation layer applying per-segment weights "
                "to the road network",
                "Integrated Nominatim geocoding, throttled to OSM's 1 req/sec "
                "fair-use limit",
                "Structured the Android client with MVVM, Clean Architecture, "
                "Hilt, and Kotlin Flow",
            ],
        },
        {
            "name": "URL-Shorten",
            "tech": ["Python", "FastAPI", "PostgreSQL", "Redis", "Nginx", "Docker"],
            "links": [
                "rahulsharma.vercel.app",
                "github.com/RahulSharma/URL-Shorten",
            ],
            "description": [
                "Built a URL shortener with 3 FastAPI servers behind Nginx, "
                "containerized with Docker Compose",
                "Used Redis as a cache layer so repeated redirects never hit "
                "PostgreSQL",
                "Added IP-based rate limiting using Redis INCR — 5 requests "
                "per 60-second window per IP",
                "Load-tested with Locust achieving 934 RPS at 500 concurrent "
                "users with zero failures",
            ],
        },
        {
            "name": "ShopEase",
            "tech": ["Kotlin", "Compose", "Firebase", "Retrofit", "Room"],
            "links": [
                "rahulsharma.vercel.app",
                "github.com/RahulSharma/ShopEase",
            ],
            "description": [
                "Built a full e-commerce flow — product search, cart, "
                "favorites, and order placement — with Jetpack Compose and "
                "Material 3",
                "Structured the app in Clean Architecture layers (data, domain, "
                "presentation) using MVVM ViewModels",
                "Integrated Firebase Authentication for login and registration, "
                "and Retrofit for the product catalog API",
                "Added Room for offline caching",
            ],
        },
    ],
    "experience": [],
    "education": [
        {
            "degree": "Bachelor of Computer Applications (BCA)",
            "institution": "University of Noida",
            "year": "07/2023 – 09/2026",
        },
    ],
    "achievements": [
        "Ideathon Runner-Up (REJOICE 2026): Won 2nd place pitching "
        "RapidLink as a scalable, B2B logistics routing solution",
        "Open Source Licensing: Published the full RapidLink mobile engine "
        "and FastAPI backend under the Apache License 2.0",
    ],
}

FAKE_LETTER = """Dear Hiring Manager,

My name is Rahul Sharma, and I am writing to apply for the Android + Backend
Developer role at your fintech startup. I have hands-on experience building
Kotlin and Jetpack Compose Android apps alongside FastAPI backend services,
including RapidLink — a routing platform with a JWT-secured backend and a
Compose UI — and URL-Shorten, a high-throughput URL shortener load-tested
to 934 RPS.

I would welcome the opportunity to discuss how my mobile and backend
experience can contribute to your team's goals. Thank you for your time
and consideration."""


if __name__ == "__main__":
    resume_path = render_resume_pdf(FAKE_TAILORED)
    print(f"\n✅ Resume PDF     : {resume_path}")

    letter_path = render_cover_letter_pdf(
        FAKE_LETTER, candidate_name=FAKE_TAILORED["name"],
    )
    print(f"✅ Cover letter PDF: {letter_path}")

    print(f"\nOpen both files. Check the layout.")
    print(f"Resume path : {Path(resume_path).absolute()}")
    print(f"Letter path : {Path(letter_path).absolute()}")
    
    import re
    from app.pipeline.pdf_writer import _env, _normalize_for_template

    template = _env.get_template("resume.html")
    html = template.render(**_normalize_for_template(FAKE_TAILORED))

    preview_path = "output/resume_preview.html"
    with open(preview_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n🌐 HTML preview: {Path(preview_path).absolute()}")
    print(f"   Double-click to open in your browser.")