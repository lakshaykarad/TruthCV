from __future__ import annotations
import os, json,re, requests, logging
from dotenv import load_dotenv
from pathlib import Path
from typing import Any

load_dotenv()

logger = logging.getLogger(__name__)
 
OLLAMA_HOST        = os.getenv("OLLAMA_HOST", "http://localhost:11434")
EXTRACTION_MODEL = os.getenv("EXTRACTION_MODEL", "qwen2.5:3b")
EXTRACTION_TIMEOUT = int(os.getenv("EXTRACTION_TIMEOUT", "120"))
EXTRACTION_RETRIES = int(os.getenv("EXTRACTION_RETRIES", "2"))

PROMPT_FILE_PATH = Path(__file__).resolve().parents[2] / "ollama" / "prompts" / "extract_resume.txt"

def load_prompt_template() -> str:
    """Load the NuExtract prompt template once and cache it."""
    if not PROMPT_FILE_PATH.exists():
        raise FileNotFoundError(f"Prompt template not found: {PROMPT_FILE_PATH}")
    return PROMPT_FILE_PATH.read_text(encoding="utf-8")

RESUME_EXTRACTION_PROMPT = load_prompt_template()

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
    r"self[- ]employed|independent)",
    re.IGNORECASE,
)

def _drop_hallucinated_experience(data: dict) -> dict:
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

def _coerce_to_schema(data: dict[str, Any]) -> dict[str, Any]:
    list_fields = [
        "skills", "experience", "projects", 
        "education", "achievements", "other_details", "links"
    ]
    scalar_fields = ["name", "email", "phone"]

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

def extract_resume_json(resume_text : str) -> dict[str,Any]:
    """Send resume text to the extraction LLM and return a validated dict.

    Raises:
        ValueError - if the model never returns parseable JSON after retries.
        RuntimeError - if Ollama itself is unreachable / errors out.
    """

    if not resume_text or not resume_text.strip():
        raise ValueError("Empty resume text; nothing to extract.")
    
    prompt = RESUME_EXTRACTION_PROMPT.replace("{{RESUME_TEXT}}", resume_text)
    
    last_error : Exception | None = None
    
    for attempt in range(1, EXTRACTION_RETRIES + 1):
        logger.info("NuExtract attempt %d/%d", attempt, EXTRACTION_RETRIES)
        
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
        
        return _drop_hallucinated_experience(_coerce_to_schema(data))
   
    raise ValueError(
        f"NuExtract failed to return valid JSON after {EXTRACTION_RETRIES} attempts. "
        f"Last error: {last_error}"
    )
    

if __name__ == "__main__":
    import sys
    from app.pipeline.pdf_reader import read_pdf

    if len(sys.argv) < 2: 
        sys.exit(1)

    logging.basicConfig(level=logging.INFO)

    text = read_pdf(sys.argv[1]) 

    result = extract_resume_json(text)
    print(json.dumps(result, indent=2, ensure_ascii=False))