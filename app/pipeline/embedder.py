import os,logging 
import torch
import requests
from typing import Any 
from app.config import settings
 
logger = logging.getLogger(__name__)

OLLAMA_HOST = settings.ollama_host
MODEL_NAME = settings.embedding_model
EMBEDDING_DIM = settings.embedding_dim
MAX_BATCH_SIZE = settings.max_batch_size

# select model if GPU not availablle run the model on CPU   
def get_device() -> str:
    if torch.cuda.is_available():
        logger.info("Using GPU for embeddings")
        return "cuda"
    logger.info("GPU is not available - using CPU for embeddings")
    return "cpu"

# Load Model
def load_model(text_list: list[str]) -> list[list[float]]:
    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/embed",
            json={"model": MODEL_NAME, "input": text_list},
            timeout=300,
        )
        resp.raise_for_status()
        return resp.json()["embeddings"]
    except Exception as e:
        raise RuntimeError(f"Could not load embedding model '{MODEL_NAME}' : {e}")

device = get_device() 

def embed_chunks(chunks : list[dict[str : Any]]) -> list[dict[str : Any]]:
    if not chunks:
        logger.warning("embed_chunks called with empty list")
        return []
    
    texts = [f"search_document: {chunk.get('text', '')}" for chunk in chunks]

    texts = [t if t.strip() else "empty" for t in texts]

    # use only batch that we need batch size is 20 we don't need to use batch size 32
    batch_size = min(MAX_BATCH_SIZE, len(texts))
    
    logger.info("Embedding %d chunks (batch_size=%d, device=%s)", len(texts), batch_size, device)
    
    all_vectors = []
    
    # Process through the list in batches
    try:
        vectors = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            batch_vectors = load_model(batch)
            vectors.extend(batch_vectors)
    except RuntimeError as e:
        logger.error("Encoding failed: %s", e)
        raise   
        
    for chunk, vector in zip(chunks, vectors):
        chunk["embedding"] = vector
        
    if device == "cuda":
        torch.cuda.empty_cache()
    
    logger.info("Embedding done: %d chunks", len(vectors))
    return chunks


def embed_text(text : str) -> list[float]:
    
    if not text or not text.strip():
        raise ValueError("Cannot embed empty text")
    
    vectors = load_model([text])

    if device == "cuda":
        torch.cuda.empty_cache()
        
    return vectors[0]
     