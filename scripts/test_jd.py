# scripts/test_jd.py
import json
import logging

from app.pipeline.extractor import extract_jd_json

logging.basicConfig(level=logging.INFO)

jd_text = """

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

result = extract_jd_json(jd_text)
print(json.dumps(result, indent=2, ensure_ascii=False))