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
    "phone": "+91 78512 34567",
    "location": "Noida, India",
    "website": "linkedin.com/in/Rahul-Sharma",
    "links": [
        "github.com/RahulSharma",
        "leetcode.com/u/SharmaRahul7",
        "RahulSharma.vercel.app",
    ],
    "summary": (
        "Android and backend developer with hands-on experience building "
        "Kotlin/Jetpack Compose mobile apps and FastAPI services. Delivered "
        "RapidLink, a routing platform with a JWT-secured FastAPI backend and "
        "Compose UI, and URL-Shorten, a high-throughput URL shortener that "
        "sustains 934 RPS at peak load. Strong foundation in PostgreSQL, Redis, "
        "Docker, and clean architecture patterns for scalable, production-ready "
        "systems."
    ),
    "skills": {
        "Backend": [
            "FastAPI", "Python", "PostgreSQL", "REST API design", "Docker",
            "Redis", "JWT / OAuth2", "SQLAlchemy", "Alembic", "Uvicorn",
            "Nginx", "bcrypt", "Locust", "Pydantic",
        ],
        "Android": [
            "Kotlin", "Jetpack Compose", "Retrofit", "Kotlin Flow",
            "Coroutines/Flow", "MVVM", "Clean Architecture", "Hilt",
            "Room", "WorkManager", "Foreground Services", "Navigation Compose",
        ],
        "Tools & DevOps": [
            "Git", "GitHub Actions", "Docker Compose", "Postman", "Linux",
            "VS Code", "Android Studio",
        ],
    },
    "projects": [
        {
            "name": "RapidLink",
            "duration": "Jan 2026 – Present",
            "tech": [
                "Kotlin", "Jetpack Compose", "FastAPI", "PostgreSQL",
                "OSRM", "Docker", "MapLibre",
            ],
            "links": [
                "rahulsharma.vercel.app",
                "github.com/RahulSharma/RapidLink",
            ],
            "description": [
                "Built a FastAPI service on a self-hosted OSRM engine "
                "(Dockerized) that serves multiple route alternatives with ETAs, "
                "replacing per-request paid mapping APIs",
                "Implemented JWT authentication (signup, login, token refresh) "
                "using the OAuth2 password flow with bcrypt hashing and "
                "per-token-type signing secrets",
                "Modeled users and profiles in PostgreSQL with SQLAlchemy and "
                "versioned schema changes via Alembic migrations",
                "Designed a traffic-simulation layer applying per-segment weights "
                "to the road network, with a Leaflet.js dashboard to manage "
                "traffic state",
                "Built a 3-stage GPS filter rejecting fixes with accuracy worse "
                "than 30m, suppressing drift under 3m, and discarding speeds "
                "over 40 m/s",
                "Structured the Android client with MVVM, Clean Architecture, "
                "Hilt, and Kotlin Flow; stored full trip history in Room for "
                "offline review",
            ],
        },
        {
            "name": "URL-Shorten",
            "duration": "Aug 2025 – Nov 2025",
            "tech": ["Python", "FastAPI", "PostgreSQL", "Redis", "Nginx", "Docker"],
            "links": [
                "rahulsharma.vercel.app",
                "github.com/RahulSharma/URL-Shorten",
            ],
            "description": [
                "Built a URL shortener with 3 FastAPI servers behind Nginx, "
                "containerized with Docker Compose and round-robin load "
                "balanced across all 3 instances",
                "Used Redis as a cache layer so repeated redirects never hit "
                "PostgreSQL, with a 10-minute TTL before refetch",
                "Added IP-based rate limiting using Redis INCR — 5 requests per "
                "60-second window per IP, atomic and race-condition free",
                "Generated 6-character short codes using Python's secrets module "
                "with automatic retry on PostgreSQL UniqueViolationError",
                "Load-tested with Locust from 100 to 5000 concurrent users; peak "
                "throughput 934 RPS at 500 users with zero failures",
            ],
        },
        {
            "name": "ShopEase",
            "duration": "Mar 2025 – Jul 2025",
            "tech": ["Kotlin", "Compose", "Firebase", "Retrofit", "Room"],
            "links": [
                "rahulsharma.vercel.app",
                "github.com/RahulSharma/ShopEase",
            ],
            "description": [
                "Built a full e-commerce flow — product search, cart, favorites, "
                "and order placement — with Jetpack Compose and Material 3",
                "Structured the app in Clean Architecture layers (data, domain, "
                "presentation) using MVVM ViewModels and Hilt for DI",
                "Integrated Firebase Authentication for login and registration, "
                "and Retrofit for the product catalog API",
                "Added Room for offline caching, enabling users to browse "
                "previously loaded products without a network connection",
            ],
        },
    ],
    "education": [
        {
            "degree": "Bachelor of Computer Applications (BCA)",
            "institution": "University of Noida",
            "year": "2023 – 2026",
        },
    ],
    "achievements": [
        "Ideathon Runner-Up (REJOICE 2026): Won 2nd place pitching RapidLink "
        "as a scalable, B2B logistics routing solution",
        "Open Source Licensing: Published the full RapidLink mobile engine and " 
        "Solved 350+ problems on LeetCode, strengthening DSA fundamentals",
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
