import os,logging 
import torch
from typing import Any
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv() 
print(torch.cuda.is_available())   # True or False?
print(torch.cuda.device_count())   # How many GPUs?
logger = logging.getLogger(__name__)

MODEL_NAME = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384")) 
MAX_BATCH_SIZE = 32 

# select model if GPU not availablle run the model on CPU
def get_device() -> str:
    if torch.cuda.is_available():
        logger.info("Using GPU for embeddings")
        return "cuda"
    logger.info("GPU is not available - using CPU for embeddings")
    return "cpu"

# Load Model
def load_model(device : str) -> SentenceTransformer:
    try:
        model = SentenceTransformer(MODEL_NAME,device=device)
    except Exception as e:
        raise RuntimeError(
            F"Could not load embedding model '{MODEL_NAME}' : {e} "
        )
    
    logger.info("Loaded model '%s (dim=%d, device=%s)",
                MODEL_NAME, EMBEDDING_DIM, device)
    return model


device = get_device()
model = load_model(device=device)

def embed_chunks(chunks : list[dict[str : Any]]) -> list[dict[str : Any]]:
    if not chunks:
        logger.warning("embed_chunks called with empty list")
        return []
    
    texts = [chunk.get("text", "") for chunk in chunks]
    texts = [t if t.strip() else "empty" for t in texts]

    # use only batch that we need batch size is 20 we don't need to use batch size 32
    batch_size = min(MAX_BATCH_SIZE, len(texts))
    
    logger.info("Embedding %d chunks (batch_size=%d, device=%s)", len(texts), batch_size, device)
    
    try:
        vectors = model.encode(
            texts,
            device=device,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False
        )
    except RuntimeError as e:
        logger.error("Encoding failed on %s: %s", device, e)
        if device == "cuda":
            logger.warning("Retrying on CPU...")
            vectors = model.encode(
                texts,
                device="cpu",
                batch_size=batch_size,
                normalize_embeddings=True   
            )
        else:
            raise
        
    for chunk, vector in zip(chunks, vectors):
        chunk["embedding"] = vector.tolist()
        
    if device == "cuda":
        torch.cuda.empty_cache()
    
    logger.info("Embedding done: shape: %s", vectors.shape)
    return chunks


def embed_text(text : str) -> list[float]:
    
    if not text or not text.strip():
        raise ValueError("Cannot embed empty text")
    
    vector = model.encode(
        [text],
        device=device,
        normalize_embeddings=True,
        show_progress_bar=False
    )[0]
    
    if device == "cuda":
        torch.cuda.empty_cache()
        
    return vector.tolist()
    
if __name__ == "__main__":
    import json
    import sys

    from app.pipeline.pdf_reader import read_pdf
    from app.pipeline.extractor import extract_resume_json
    from app.pipeline.chunker import chunk_resume

    logging.basicConfig(level=logging.INFO)

    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "resume.pdf"

    # Run the full pipeline
    resume = extract_resume_json(read_pdf(pdf_path))
    chunks = chunk_resume(resume)
    embedded = embed_chunks(chunks)

    # Print a short preview (384 floats is too long to print whole)
    first = embedded[0]
    print(f"\nFirst chunk text: {first['text'][:80]}...")
    print(f"Embedding length: {len(first['embedding'])}")
    print(f"Embedding preview: {first['embedding'][:5]}...")
    print(f"\nTotal chunks embedded: {len(embedded)}")
    