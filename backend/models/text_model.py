
import re
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_ST_MODEL = None
_ST_MODEL_NAME = 'all-MiniLM-L6-v2'
_PARAPHRASE_MODEL = None
_PARAPHRASE_TOKENIZER = None
_PARAPHRASE_MODEL_NAME = 'Vamsi/T5_Paraphrase_Paws'
_FLAN_MODEL = None
_FLAN_TOKENIZER = None
_FLAN_MODEL_NAME = 'google/flan-t5-small'

def _token_set(s):
    return set(re.findall(r"\b[a-z0-9']+\b", (s or '').lower()))

def jaccard_similarity(a, b):
    A = _token_set(a); B = _token_set(b)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)

def _article_lead(content, max_chars=800):
    """First paragraph of the article, through the first full stop when possible."""
    text = (content or '').strip()
    if not text:
        return ''
    parts = [p.strip() for p in re.split(r'\n\s*\n+', text) if p.strip()]
    lead = _first_complete_sentence_from_paragraphs(parts) if parts else text
    if not lead:
        lead = parts[0] if parts else text
    if len(lead) > max_chars:
        cut = lead[:max_chars]
        stop = max(cut.rfind('.'), cut.rfind('!'), cut.rfind('?'))
        lead = cut[: stop + 1] if stop > max_chars // 2 else cut.rsplit(' ', 1)[0]
    return lead

def _get_st_model():
    global _ST_MODEL
    if _ST_MODEL is None:
        from sentence_transformers import SentenceTransformer
        _ST_MODEL = SentenceTransformer(_ST_MODEL_NAME)
    return _ST_MODEL

def _embedding_similarity(a, b):
    try:
        from sentence_transformers import util
    except Exception as e:
        raise ImportError(f"sentence-transformers unavailable: {e}") from e

    model = _get_st_model()
    emb_a = model.encode([a], convert_to_tensor=True)
    emb_b = model.encode([b], convert_to_tensor=True)
    sim = float(util.cos_sim(emb_a, emb_b).cpu().item())
    return sim, f"sentence-transformers::{_ST_MODEL_NAME}"

def _clean_headline_suggestion(text, max_len=500):
    """One headline line: first sentence only, fix casing; do not truncate mid-sentence."""
    if not text:
        return ''
    text = re.sub(r'\s+', ' ', str(text).strip())
    text = re.sub(r'\.{2,}', '.', text)
    sentence = _first_sentence_through_stop(text) or re.split(r'(?<=[.!?])\s+', text)[0].strip()
    if not sentence:
        return ''
    if sentence.endswith(('.', '!', '?')):
        sentence = sentence[:-1].strip()
    if sentence:
        sentence = sentence[0].upper() + sentence[1:]
        for day in ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'):
            sentence = re.sub(rf'\b{day}\b', day.capitalize(), sentence, flags=re.I)
    if len(sentence) > max_len:
        sentence = sentence[: max_len - 1].rsplit(' ', 1)[0]
    return sentence

def _get_paraphrase_model():
    global _PARAPHRASE_MODEL, _PARAPHRASE_TOKENIZER
    if _PARAPHRASE_MODEL is None:
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        _PARAPHRASE_TOKENIZER = AutoTokenizer.from_pretrained(_PARAPHRASE_MODEL_NAME)
        _PARAPHRASE_MODEL = AutoModelForSeq2SeqLM.from_pretrained(_PARAPHRASE_MODEL_NAME)
    return _PARAPHRASE_MODEL, _PARAPHRASE_TOKENIZER

def _get_flan_model():
    global _FLAN_MODEL, _FLAN_TOKENIZER
    if _FLAN_MODEL is None:
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        _FLAN_TOKENIZER = AutoTokenizer.from_pretrained(_FLAN_MODEL_NAME)
        _FLAN_MODEL = AutoModelForSeq2SeqLM.from_pretrained(_FLAN_MODEL_NAME)
    return _FLAN_MODEL, _FLAN_TOKENIZER

def _split_sentences(text):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', (text or '').strip()) if s.strip()]

_ABBREV_ENDINGS = frozenset({
    'mr.', 'mrs.', 'ms.', 'dr.', 'prof.', 'sr.', 'jr.', 'vs.', 'etc.',
    'u.s.', 'u.k.', 'd.c.', 'a.m.', 'p.m.', 'e.g.', 'i.e.', 'st.', 'ave.',
})

def _ends_with_sentence_stop(text):
    t = (text or '').strip()
    return bool(t) and t[-1] in '.!?' or bool(re.search(r'[.!?]["\']?\s*$', t))

def _first_sentence_through_stop(text):
    """Return text from the start through the first sentence-ending . ! ?"""
    text = re.sub(r'\s+', ' ', (text or '').strip())
    if not text:
        return ''

    if _ends_with_sentence_stop(text):
        m = re.search(r'^(.+?[.!?]["\']?)(?:\s+|$)', text)
        return m.group(1).strip() if m else text

    # Walk char-by-char; skip abbreviation periods (U.S., D.C., etc.)
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in '.!?':
            if ch == '.':
                word_start = text.rfind(' ', 0, i) + 1
                word = text[word_start:i + 1].lower()
                if word in _ABBREV_ENDINGS:
                    i += 1
                    continue
                if i > 0 and text[i - 1].isdigit():
                    i += 1
                    continue
            return text[: i + 1].strip()
        i += 1
    return text

def _first_complete_sentence_from_paragraphs(parts):
    """Merge leading paragraphs until the first full sentence (ends with . ! ?)."""
    if not parts:
        return ''
    buf = []
    for para in parts:
        buf.append(para.strip())
        combined = ' '.join(buf)
        if _ends_with_sentence_stop(combined):
            return _first_sentence_through_stop(combined)
    return _first_sentence_through_stop(' '.join(buf))

def _lead_sentence_for_paraphrase(content, min_len=40):
    """Main narrative lead — first complete sentence of the body (through full stop)."""
    parts = [p.strip() for p in re.split(r'\n\s*\n+', (content or '').strip()) if p.strip()]
    if not parts:
        return ''

    start_idx = 0
    if len(parts) >= 2:
        first_sent = _first_sentence_through_stop(parts[0])
        if first_sent and len(first_sent) < 100 and _ends_with_sentence_stop(first_sent):
            start_idx = 1

    sentence = _first_complete_sentence_from_paragraphs(parts[start_idx:])
    if sentence and len(sentence) >= min_len:
        return sentence

    sentence = _first_sentence_through_stop(' '.join(parts))
    return sentence if sentence else parts[0].strip()

def _is_junk_paraphrase(text):
    if not text or len(text) < 30:
        return True
    junk = text.lower().strip()
    if junk in ('false', 'true', 'none', 'yes', 'no'):
        return True
    return len(junk.split()) < 6

def _is_verbatim_copy(text, source, threshold=0.94):
    if not text or not source:
        return not text
    return jaccard_similarity(text, source) >= threshold

def _pick_best_paraphrase(candidates, source, max_len=500):
    """Choose the model candidate that rewrites without copying or drifting off-topic."""
    best = None
    best_score = -1.0
    for raw in candidates:
        text = _clean_headline_suggestion(raw, max_len=max_len)
        if _is_junk_paraphrase(text):
            continue
        j = jaccard_similarity(text, source)
        if j >= 0.94 or j < 0.12:
            continue
        # Prefer meaningful rewrites: lower overlap is better, but not too low
        score = 1.0 - j
        if score > best_score:
            best, best_score = text, score
    return best

def _try_paws_paraphrase(source, max_new_tokens=120):
    """Primary: T5 fine-tuned on PAWS for generic paraphrasing (any topic)."""
    model, tokenizer = _get_paraphrase_model()
    inputs = tokenizer(
        'paraphrase: ' + source,
        return_tensors='pt',
        truncation=True,
        max_length=512,
    )
    outputs = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        num_beams=5,
        num_return_sequences=5,
        diversity_penalty=1.2,
        no_repeat_ngram_size=3,
    )
    candidates = [tokenizer.decode(seq, skip_special_tokens=True).strip() for seq in outputs]
    return _pick_best_paraphrase(candidates, source)

def _try_flan_paraphrase(source, max_new_tokens=120):
    """Fallback: instruction-tuned Flan-T5 rewrite."""
    prompt = (
        'Paraphrase the sentence below using different words. '
        'Keep every fact. Output one sentence only.\n\n'
        'Sentence: ' + source
    )
    model, tokenizer = _get_flan_model()
    inputs = tokenizer(prompt, return_tensors='pt', truncation=True, max_length=512)
    outputs = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        num_beams=4,
        no_repeat_ngram_size=3,
        length_penalty=1.1,
    )
    raw = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
    text = _clean_headline_suggestion(raw, max_len=500)
    if _is_junk_paraphrase(text) or _is_verbatim_copy(text, source):
        return None
    return text

def _paraphrase_lead_sentence(content):
    """Paraphrase the main lead sentence with ML models only — no hardcoded rules."""
    source = _lead_sentence_for_paraphrase(content)
    if not source:
        return 'Read article for accurate details', 'none'

    try:
        paws = _try_paws_paraphrase(source)
        if paws and not _is_verbatim_copy(paws, source):
            return paws, 'paws-paraphrase'
    except Exception as e:
        logger.info(f"paws paraphrase failed: {e}")

    try:
        flan = _try_flan_paraphrase(source)
        if flan and not _is_verbatim_copy(flan, source):
            return flan, 'flan-paraphrase'
    except Exception as e:
        logger.info(f"flan paraphrase failed: {e}")

    return 'Read article for accurate details', 'paraphrase-unavailable'

def _rewrite_with_transformer(title, content, max_new_tokens=90):
    text, _ = _paraphrase_lead_sentence(content)
    return text if text and text != 'Read article for accurate details' else None

def _suggested_title_when_misleading(title, content, original_sim, compare_against, use_jaccard=False):
    suggested, source = _paraphrase_lead_sentence(content)
    return suggested, source

def check_and_rewrite_headline(title, content, threshold_embedding=0.75, threshold_jaccard=0.55):
    res = {
        'original_title': title,
        'similarity': 0.0,
        'method': 'none',
        'is_misleading': False,
        'suggested_title': title,
        'suggestion_source': 'unchanged',
    }

    lead = _article_lead(content)
    compare_against = lead or content

    try:
        sim, method = _embedding_similarity(title, compare_against)
        res['similarity'] = round(float(sim), 3)
        res['method'] = method
        mis = sim < threshold_embedding
        res['is_misleading'] = bool(mis)
        if mis:
            suggested, source = _suggested_title_when_misleading(
                title, content, sim, compare_against, use_jaccard=False
            )
            res['suggested_title'] = suggested
            res['suggestion_source'] = source
        return res
    except Exception as e:
        logger.info(f"embedding path unavailable: {e} - falling back to Jaccard")

    sim = jaccard_similarity(title, compare_against)
    res['similarity'] = round(float(sim), 3)
    res['method'] = 'jaccard'
    mis = sim < threshold_jaccard
    res['is_misleading'] = bool(mis)
    if mis:
        suggested, source = _suggested_title_when_misleading(
            title, content, sim, compare_against, use_jaccard=True
        )
        res['suggested_title'] = suggested
        res['suggestion_source'] = source
    return res
