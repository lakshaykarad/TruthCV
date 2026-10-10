from __future__ import annotations
import os, json,re, requests, logging
from dotenv import load_dotenv
from pathlib import Path
from typing import Any
from app.config import settings
load_dotenv()

logger = logging.getLogger(__name__)
 
OLLAMA_HOST = settings.ollama_host
EXTRACTION_MODEL = settings.extraction_model
EXTRACTION_TIMEOUT = settings.extraction_timeout
EXTRACTION_RETRIES = settings.extraction_retries
PROMPT_DIR = settings.prompt_dir
PLACEHOLDERS = ("{{TEXT}}", "{{RESUME_TEXT}}", "{{JD_TEXT}}")

def load_prompt_template(prompt_name: str) -> str:
    
    """Load the Extraction prompt template once and cache it."""
    prompt_path = PROMPT_DIR / f"extract_{prompt_name}.txt"
    
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {prompt_name}")
    return prompt_path.read_text(encoding="utf-8")


END_OUTPUT_PATTERN = re.compile(r"<\|end-output\|>.*", re.DOTALL)

def _clean_model_output(raw_model_response : str) -> str:
    """Strip NuExtract artifacts before json.loads()."""
    raw_model_response = END_OUTPUT_PATTERN .sub("",raw_model_response)
    raw_model_response = raw_model_response.replace("<|end-output|>", "").strip()
    
    if raw_model_response.startswith("```"):
        raw_model_response = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_model_response, flags=re.DOTALL).strip()
    return raw_model_response

SUSPICIOUS_EXPERIENCE = re.compile(
    r"(self[- ]directed|project portfolio|personal project|freelance|"
    r"self[- ]employed|independent|"
    r"backend\s*&\s*android|frontend\s*&\s*android|full[- ]stack|"
    r"^(backend|frontend|android|ios|mobile|web|software|devops)$)",
    re.IGNORECASE,
)

def _drop_hallucinated_experience(data: dict) -> dict:
    
    if "experience" not in data:
        return data
     
    clean_json_text = []
    for exp in data.get("experience") or []:
        if not isinstance(exp, dict):
            continue
        experience = f"{exp.get('company', '')} {exp.get('duration', '')}"
        if SUSPICIOUS_EXPERIENCE.search(experience):
            logger.warning("Dropping hallucinated experience: %s", experience)
            continue
        clean_json_text.append(exp)
    data["experience"] = clean_json_text
    return data

def _coerce_resume_schema(data: dict[str, Any]) -> dict[str, Any]:
    list_fields = [
        "skills", "experience", "projects", 
        "education", "achievements", "other_details", "links"
    ]
    scalar_fields = ["name", "email", "phone", "location", "website"]

    for field in list_fields:
        val = data.get(field)
        if val is None:
            data[field] = []
        elif not isinstance(val, list):
            data[field] = [val]

    for field in scalar_fields:
        val = data.get(field)
        if val is not None and not isinstance(val, str):
            data[field] = str(val)
        
    valid_url_re = re.compile(
        r"(github\.com|gitlab\.com|vercel\.app|netlify\.app|"
        r"github\.io|herokuapp\.com|onrender\.com|railway\.app|"
        r"leetcode\.com|linkedin\.com|youtube\.com|"
        r"\.dev/|\.io/|\.com/)",
        re.IGNORECASE,
    )
    portfolio_url = (data.get("website") or "").strip().lower()

    for proj in data.get("projects") or []:
        if not isinstance(proj, dict):
            continue
        raw_links = proj.get("links") or []
        cleaned: list[str] = []
        seen: set[str] = set()
        for link in raw_links:
            if not isinstance(link, str):
                continue
            link = link.strip()
            low = link.lower()
            if not link:
                continue
            if portfolio_url and portfolio_url in low:
                logger.debug("Dropping portfolio URL from project: %s", link)
                continue
            if not valid_url_re.search(link):
                logger.debug("Dropping invalid project link: %s", link)
                continue
            if low in seen:
                continue
            seen.add(low)
            cleaned.append(link)
        proj["links"] = cleaned
    return data

def _coerce_jd_schema(data: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize JD JSON: fill missing fields, strip whitespace, dedupe lists.
    """
    list_fields = [
        "required_skills",
        "preferred_skills",
        "responsibilities",
        "qualifications",
    ]
    scalar_fields = ["title", "company", "location"]
 
    for field in list_fields:
        val = data.get(field)
        if val is None:
            data[field] = []
            continue
        if not isinstance(val, list):
            val = [val]

        cleaned: list[str] = []
        seen: set[str] = set()
        for item in val:
            if not isinstance(item, str):
                item = str(item)
            item = item.strip()
            if not item:
                continue
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(item)
        data[field] = cleaned
 
    for field in scalar_fields:
        val = data.get(field)
        if val is None:
            data[field] = None
        elif not isinstance(val, str):
            data[field] = str(val).strip()
        else:
            data[field] = val.strip() or None

    return data

def _call_ollama(prompt : str) -> str:
    "Single HTTP call to Ollama. Returns the raw 'response' string."
    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": EXTRACTION_MODEL,
                "prompt": prompt,
                "stream": False, 
                "format" : "json",
                "options": {
                    "temperature": 0,   
                    "top_k": 10,
                    "num_predict": 8192,
                    "num_ctx": 16384,   
                },
            },
            timeout=EXTRACTION_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Ollama request failed {e}") from e
    
    return resp.json().get("response","")

def extract_resume_json(resume_text: str) -> dict[str, Any]: 
    return _extract(resume_text, prompt_name="resume")

def extract_jd_json(jd_text: str) -> dict[str, Any]: 
    return _extract(jd_text, prompt_name="jd")

def _extract(text: str, prompt_name: str) -> dict[str, Any]:
    
    if not text or not text.strip():
        raise ValueError("Empty resume text; nothing to extract.")
     
    prompt_template = load_prompt_template(prompt_name)
 
    prompt = None
    for placeholder in PLACEHOLDERS:
        if placeholder in prompt_template:
            prompt = prompt_template.replace(placeholder, text)
            break

    if prompt is None:
        raise ValueError(
            f"No placeholder ({', '.join(PLACEHOLDERS)}) found in "
            f"extract_{prompt_name}.txt"
        )
    
    last_error : Exception | None = None
    
    for attempt in range(1, EXTRACTION_RETRIES + 1):
        logger.info("Extraction attempt %d/%d (prompt=%s)", attempt, EXTRACTION_RETRIES, prompt_name)
        
        raw = _call_ollama(prompt)
        cleaned = _clean_model_output(raw)
        
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            last_error = e
            logger.warning("Bad JSON on attempt %d: %s", attempt, e)
            logger.debug("Raw output: %s", cleaned[:400])
            continue
        
        if not isinstance(data, dict):
            last_error = ValueError("Model returned non-dict JSON")
            logger.warning("Non-dict JSON on attempt %d", attempt)
            continue
        
        if prompt_name == "resume":
            return _drop_hallucinated_experience(_coerce_resume_schema(data))
        else:
            return _coerce_jd_schema(data=data)
   
    raise ValueError(
        f"Extraction failed to return valid JSON after {EXTRACTION_RETRIES} attempts. "
        f"Last error: {last_error}"
    )
    