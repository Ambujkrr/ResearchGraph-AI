"""Small, revision-pinned CPU embedding model; loaded lazily."""
import hashlib
import os
from functools import lru_cache
MODEL='sentence-transformers/all-MiniLM-L6-v2'
REVISION='1110a243fdf4706b3f48f1d95db1a4f5529b4d41'
DIMENSION=384

def paper_text(paper): return paper.title.strip() + ('\n' + paper.abstract.strip() if paper.abstract and paper.abstract.strip() else '')
def content_hash(paper): return hashlib.sha256(paper_text(paper).encode('utf-8')).hexdigest()
@lru_cache(maxsize=1)
def model():
    import torch
    from sentence_transformers import SentenceTransformer
    threads=max(1,min(int(os.environ.get('EMBEDDING_CPU_THREADS','2')),8))
    torch.set_num_threads(threads)
    return SentenceTransformer(MODEL,revision=REVISION,device='cpu')
def encode(texts):
    return model().encode(texts,normalize_embeddings=True,show_progress_bar=False).tolist()
