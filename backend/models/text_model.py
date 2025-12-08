
import re
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def _token_set(s):
    return set(re.findall(r"\b[a-z0-9']+\b", (s or '').lower()))

def jaccard_similarity(a, b):
    A = _token_set(a); B = _token_set(b)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)

def _first_informative_sentence(text):
    sents = re.split(r'(?<=[.!?])\s+', (text or '').strip())
    for s in sents:
        if len(s) > 20:
            return s.strip()
    return (sents[0].strip() if sents else "Read article for accurate details")

def _embedding_similarity(a, b):
    try:
        from sentence_transformers import SentenceTransformer, util
    except Exception as e:
        raise ImportError(f"sentence-transformers unavailable: {e}") from e

    model_name = 'all-MiniLM-L6-v2'
    model = SentenceTransformer(model_name)
    emb_a = model.encode([a], convert_to_tensor=True)
    emb_b = model.encode([b], convert_to_tensor=True)
    sim = float(util.cos_sim(emb_a, emb_b).cpu().item())
    return sim, f"sentence-transformers::{model_name}"

def _rewrite_with_transformer(title, content, max_length=30):
    try:
        from transformers import pipeline
    except Exception as e:
        raise ImportError(f"transformers unavailable: {e}") from e

    prompt = (f"Rewrite the following headline to make it factually accurate given the article content.\\n\\n"
              f"Headline: {title}\\n\\nArticle: {content}\\n\\nAccurate headline:")
    pipe = pipeline('text2text-generation', model='t5-small', device=-1)
    out = pipe(prompt, max_length=max_length, truncation=True)
    if out and isinstance(out, list):
        return out[0].get('generated_text', '').strip()
    return None

def check_and_rewrite_headline(title, content, threshold_embedding=0.75, threshold_jaccard=0.55):
    res = {
        'original_title': title,
        'similarity': 0.0,
        'method': 'none',
        'is_misleading': False,
        'suggested_title': title
    }

    # Try embedding-based similarity first
    try:
        sim, method = _embedding_similarity(title, content)
        res['similarity'] = round(float(sim), 3)
        res['method'] = method
        mis = sim < threshold_embedding
        res['is_misleading'] = bool(mis)
        if mis:
            try:
                rewritten = _rewrite_with_transformer(title, content)
                res['suggested_title'] = rewritten if rewritten else _first_informative_sentence(content)
            except Exception as e:
                logger.info(f"rewrite failed: {e}")
                res['suggested_title'] = _first_informative_sentence(content)
        return res
    except Exception as e:
        logger.info(f"embedding path unavailable: {e} - falling back to Jaccard")

    # Fallback to Jaccard similarity
    sim = jaccard_similarity(title, content)
    res['similarity'] = round(float(sim), 3)
    res['method'] = 'jaccard'
    mis = sim < threshold_jaccard
    res['is_misleading'] = bool(mis)
    if mis:
        try:
            rewritten = _rewrite_with_transformer(title, content)
            res['suggested_title'] = rewritten if rewritten else _first_informative_sentence(content)
        except Exception as e:
            logger.info(f"rewrite unavailable: {e}")
            res['suggested_title'] = _first_informative_sentence(content)
    return res
