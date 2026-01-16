"""
Prompt Compressor - Reduce token count while preserving meaning.

Uses:
- fastembed for semantic deduplication (ONNX-based, no PyTorch)
- NLTK for text compression (stopwords, stemming)

Pipeline:
1. Split into segments (sentences/paragraphs)
2. Deduplicate semantically similar segments (neural embeddings)
3. Compress remaining text (stopwords, fillers)
4. Reassemble to target token budget

Expected: 70-85% reduction with 90%+ information retention.
CPU overhead: 200-500ms for typical prompt.
"""

import re
from typing import List, Tuple, Optional
import numpy as np

# NLTK for text processing
import nltk
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer

# Initialize NLTK
try:
    STOPWORDS = set(stopwords.words('english'))
except:
    nltk.download('stopwords', quiet=True)
    STOPWORDS = set(stopwords.words('english'))

try:
    from nltk.tokenize import sent_tokenize
    sent_tokenize("Test.")
except:
    nltk.download('punkt', quiet=True)
    nltk.download('punkt_tab', quiet=True)
    from nltk.tokenize import sent_tokenize

STEMMER = PorterStemmer()

# Lazy load fastembed model (33MB download on first use)
_embedding_model = None

def get_embedding_model():
    """Lazy load embedding model."""
    global _embedding_model
    if _embedding_model is None:
        try:
            from fastembed import TextEmbedding
            _embedding_model = TextEmbedding('BAAI/bge-small-en-v1.5')
        except ImportError:
            print("[WARN] fastembed not installed, using TF-IDF fallback")
            return None
    return _embedding_model

# Filler phrases to remove
FILLER_PATTERNS = [
    r'\bI think that\b',
    r'\bI believe that\b',
    r'\bIt seems that\b',
    r'\bIn order to\b',
    r'\bAs a result of\b',
    r'\bDue to the fact that\b',
    r'\bAt this point in time\b',
    r'\bIn the event that\b',
    r'\bFor the purpose of\b',
    r'\bWith regard to\b',
    r'\bI am going to\b',
    r'\bI will be\b',
    r'\bI would like to\b',
    r'\bIt is important to note that\b',
    r'\bIt should be noted that\b',
    r'\bAs mentioned earlier\b',
    r'\bAs previously stated\b',
]


def estimate_tokens(text: str) -> int:
    """Rough token estimate (4 chars per token)."""
    return len(text) // 4


def remove_fillers(text: str) -> str:
    """Remove common filler phrases."""
    for pattern in FILLER_PATTERNS:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', text).strip()


def compress_text_nltk(text: str, aggressive: bool = False) -> str:
    """
    Compress text using NLTK.
    
    aggressive=False: Remove fillers only (~20% reduction)
    aggressive=True: Also remove stopwords + stem (~50% reduction)
    """
    if not text or len(text) < 50:
        return text
    
    # Remove fillers
    text = remove_fillers(text)
    
    if not aggressive:
        return text
    
    # Tokenize and filter
    words = text.split()
    filtered = []
    for word in words:
        clean = word.lower().strip('.,!?:;()[]{}"\'-')
        if clean and clean not in STOPWORDS and len(clean) > 2:
            stemmed = STEMMER.stem(clean)
            filtered.append(stemmed)
    
    return ' '.join(filtered)


def split_into_segments(text: str, min_length: int = 30) -> List[str]:
    """Split text into logical segments for deduplication."""
    # First try to split by section headers
    sections = re.split(r'\n(?=={2,}|#{1,3}\s|\[)', text)
    
    segments = []
    for section in sections:
        section = section.strip()
        if len(section) > 500:
            # Further split long sections into sentences
            try:
                sents = sent_tokenize(section)
                segments.extend(sents)
            except:
                # Fallback: split by newlines
                segments.extend(section.split('\n'))
        elif section:
            segments.append(section)
    
    # Filter empty and very short segments
    return [s.strip() for s in segments if s.strip() and len(s.strip()) > min_length]


def deduplicate_semantic(segments: List[str], threshold: float = 0.85) -> List[str]:
    """
    Remove semantically similar segments using neural embeddings.
    
    threshold: Similarity above this = duplicate (0.85 = 85% similar)
    """
    if len(segments) <= 1:
        return segments
    
    model = get_embedding_model()
    if model is None:
        # Fallback to TF-IDF
        return deduplicate_tfidf(segments, threshold=0.4)
    
    # Get embeddings
    embeddings = list(model.embed(segments))
    embeddings = np.array(embeddings)
    
    # Normalize for cosine similarity
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings / norms
    
    # Compute similarity matrix
    sim_matrix = embeddings @ embeddings.T
    
    # Greedy deduplication: keep first occurrence, skip similar ones
    keep_indices = []
    for i in range(len(segments)):
        is_duplicate = False
        for j in keep_indices:
            if sim_matrix[i, j] > threshold:
                is_duplicate = True
                break
        if not is_duplicate:
            keep_indices.append(i)
    
    return [segments[i] for i in keep_indices]


def deduplicate_tfidf(segments: List[str], threshold: float = 0.4) -> List[str]:
    """Fallback TF-IDF deduplication (word-overlap based)."""
    if len(segments) <= 1:
        return segments
    
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        
        vectorizer = TfidfVectorizer(stop_words='english', max_features=1000, ngram_range=(1, 2))
        tfidf_matrix = vectorizer.fit_transform(segments)
        sim_matrix = cosine_similarity(tfidf_matrix)
    except Exception:
        return segments
    
    keep_indices = []
    for i in range(len(segments)):
        is_duplicate = False
        for j in keep_indices:
            if sim_matrix[i, j] > threshold:
                is_duplicate = True
                break
        if not is_duplicate:
            keep_indices.append(i)
    
    return [segments[i] for i in keep_indices]


def compress_prompt(
    prompt: str,
    target_tokens: int = 20000,
    dedup_threshold: float = 0.85,
    aggressive_compress: bool = True
) -> Tuple[str, dict]:
    """
    Compress a full prompt to target token budget.
    
    Returns: (compressed_text, stats_dict)
    
    Pipeline:
    1. Split into segments
    2. Deduplicate similar segments (semantic)
    3. Compress remaining text (NLTK)
    4. Truncate if still over budget
    """
    original_tokens = estimate_tokens(prompt)
    stats = {
        "original_tokens": original_tokens,
        "original_segments": 0,
        "after_dedup_segments": 0,
        "final_tokens": 0,
        "reduction_pct": 0
    }
    
    # Step 1: Split into segments
    segments = split_into_segments(prompt)
    stats["original_segments"] = len(segments)
    
    # Handle very short prompts
    if len(segments) <= 2:
        stats["final_tokens"] = original_tokens
        stats["after_dedup_segments"] = len(segments)
        return prompt, stats
    
    # Step 2: Semantic deduplication
    unique_segments = deduplicate_semantic(segments, threshold=dedup_threshold)
    stats["after_dedup_segments"] = len(unique_segments)
    
    # Step 3: Compress each segment
    compressed_segments = []
    for seg in unique_segments:
        compressed = compress_text_nltk(seg, aggressive=aggressive_compress)
        if compressed:
            compressed_segments.append(compressed)
    
    # Step 4: Reassemble
    result = '\n'.join(compressed_segments)
    
    # Step 5: Truncate only if over budget
    result_tokens = estimate_tokens(result)
    if result_tokens > target_tokens:
        char_budget = target_tokens * 4
        if len(result) > char_budget:
            keep_start = char_budget // 2
            keep_end = char_budget // 2
            result = result[:keep_start] + "\n[...compressed...]\n" + result[-keep_end:]
    
    stats["final_tokens"] = estimate_tokens(result)
    stats["reduction_pct"] = int((1 - stats["final_tokens"] / max(original_tokens, 1)) * 100)
    
    return result, stats


def compress_episodic_wakes(wakes: List[dict], target_chars: int = 20000) -> str:
    """
    Specialized compression for episodic memory wakes.
    
    Deduplicates similar wakes, keeps unique insights.
    """
    if not wakes:
        return ""
    
    # Extract text from each wake
    wake_texts = []
    for w in wakes:
        wake_num = w.get("wake_num", w.get("total_wakes", "?"))
        action = w.get("action", "?")
        final = w.get("final_text", "")[:500]
        wake_texts.append(f"#{wake_num} [{action}]: {final}")
    
    # Semantic deduplication
    unique = deduplicate_semantic(wake_texts, threshold=0.80)
    
    # Compress each
    compressed = [compress_text_nltk(w, aggressive=True) for w in unique]
    
    result = '\n'.join(compressed)
    
    # Truncate if needed
    if len(result) > target_chars:
        result = result[:target_chars] + "\n[...truncated...]"
    
    return result


# Quick test
if __name__ == "__main__":
    test_texts = [
        'Fixed the configuration bug in the system settings',
        'Fixed config bug in system settings', 
        'Investigated the database connection timeout issue',
        'Looked into database connection timeout problem',
        'Added new feature for user authentication',
    ]
    
    print("Testing semantic deduplication...")
    unique = deduplicate_semantic(test_texts, threshold=0.85)
    print(f"Original: {len(test_texts)} -> Unique: {len(unique)}")
    for u in unique:
        print(f"  - {u[:60]}")
    
    print("\n" + "="*50)
    
    # Test full compression
    test_prompt = """
    I think that the configuration problem is occurring because the system 
    is not properly loading the environment variables. As a result of this,
    the database connection fails. In order to fix this issue, we need to
    ensure that the .env file is properly configured.
    
    The configuration issue happens when environment variables are not loaded
    correctly. This causes database connections to fail. We should check the
    .env file configuration.
    
    I also investigated a separate issue with the authentication module.
    The auth tokens were expiring too quickly. Fixed the token expiry time.
    """
    
    compressed, stats = compress_prompt(test_prompt, target_tokens=100)
    print(f"\nFull compression test:")
    print(f"Original: {stats['original_tokens']} tokens, {stats['original_segments']} segments")
    print(f"Final: {stats['final_tokens']} tokens, {stats['after_dedup_segments']} segments")
    print(f"Reduction: {stats['reduction_pct']}%")
    print(f"\nCompressed:\n{compressed}")
