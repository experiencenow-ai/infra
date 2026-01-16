"""
Prompt Compression - Reduce token count while preserving information.

Applied as FINAL step after all context is assembled.
Uses semantic deduplication + linguistic compression.

Installation (on target server):
    pip install nltk sentence-transformers

Expected results:
    - 70-85% token reduction
    - 90%+ information retention
    - ~2-3 second CPU overhead (one-time per wake)
"""

import re
import hashlib
from typing import List, Tuple, Optional

# =============================================================================
# Graceful imports - fall back if libraries not installed
# =============================================================================

NLTK_AVAILABLE = False
SENTENCE_TRANSFORMERS_AVAILABLE = False

try:
    import nltk
    from nltk.corpus import stopwords
    from nltk.stem import PorterStemmer
    from nltk.tokenize import sent_tokenize, word_tokenize
    
    # Download required data (silent)
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        nltk.download('punkt', quiet=True)
        nltk.download('punkt_tab', quiet=True)
    try:
        nltk.data.find('corpora/stopwords')
    except LookupError:
        nltk.download('stopwords', quiet=True)
    
    NLTK_AVAILABLE = True
    STOPWORDS = set(stopwords.words('english'))
    STEMMER = PorterStemmer()
except ImportError:
    STOPWORDS = set()
    STEMMER = None

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    SENTENCE_TRANSFORMERS_AVAILABLE = True
    # Load model lazily
    _embedding_model = None
except ImportError:
    pass


# =============================================================================
# Core compression functions
# =============================================================================

def compress_prompt(text: str, target_ratio: float = 0.3) -> str:
    """
    Compress assembled prompt to target ratio of original size.
    
    Steps:
    1. Split into sections (preserve structure)
    2. Semantic dedup within each section
    3. Linguistic compression (stopwords, stemming)
    4. Final truncation if still over target
    
    Args:
        text: Full assembled prompt
        target_ratio: Target size as fraction of original (0.3 = 30%)
    
    Returns:
        Compressed prompt
    """
    if not text or len(text) < 500:
        return text
    
    original_len = len(text)
    target_len = int(original_len * target_ratio)
    
    # Split into sections (preserve headers)
    sections = _split_into_sections(text)
    
    compressed_sections = []
    for header, content in sections:
        # Semantic dedup if available
        if SENTENCE_TRANSFORMERS_AVAILABLE and len(content) > 1000:
            content = _semantic_dedupe(content)
        
        # Linguistic compression
        if NLTK_AVAILABLE:
            content = _linguistic_compress(content)
        else:
            content = _basic_compress(content)
        
        compressed_sections.append((header, content))
    
    # Reassemble
    result = _reassemble_sections(compressed_sections)
    
    # Final truncation if needed
    if len(result) > target_len * 1.5:
        result = _smart_truncate(result, target_len)
    
    reduction = (1 - len(result) / original_len) * 100
    print(f"  [COMPRESS] {original_len:,} → {len(result):,} chars ({reduction:.0f}% reduction)")
    
    return result


def _split_into_sections(text: str) -> List[Tuple[str, str]]:
    """Split prompt into sections by headers (=== HEADER ===)."""
    sections = []
    current_header = ""
    current_content = []
    
    for line in text.split('\n'):
        if line.startswith('===') and line.endswith('==='):
            # Save previous section
            if current_content:
                sections.append((current_header, '\n'.join(current_content)))
            current_header = line
            current_content = []
        else:
            current_content.append(line)
    
    # Don't forget last section
    if current_content:
        sections.append((current_header, '\n'.join(current_content)))
    
    return sections


def _reassemble_sections(sections: List[Tuple[str, str]]) -> str:
    """Reassemble sections with headers."""
    parts = []
    for header, content in sections:
        if header:
            parts.append(header)
        parts.append(content)
    return '\n'.join(parts)


# =============================================================================
# Semantic deduplication (sentence-transformers)
# =============================================================================

def _get_embedding_model():
    """Lazy load embedding model."""
    global _embedding_model
    if _embedding_model is None and SENTENCE_TRANSFORMERS_AVAILABLE:
        # Small, fast model - 90MB
        _embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
    return _embedding_model


def _semantic_dedupe(text: str, similarity_threshold: float = 0.80) -> str:
    """
    Remove semantically similar sentences.
    
    If two sentences are >80% similar, keep only the first.
    """
    model = _get_embedding_model()
    if model is None:
        return text
    
    # Split into sentences
    if NLTK_AVAILABLE:
        sentences = sent_tokenize(text)
    else:
        sentences = re.split(r'[.!?]+', text)
    
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    
    if len(sentences) < 3:
        return text
    
    # Get embeddings
    try:
        embeddings = model.encode(sentences, show_progress_bar=False)
    except Exception as e:
        print(f"  [COMPRESS] Embedding failed: {e}")
        return text
    
    # Deduplicate
    unique_indices = []
    for i, emb in enumerate(embeddings):
        is_duplicate = False
        for j in unique_indices:
            similarity = np.dot(emb, embeddings[j]) / (
                np.linalg.norm(emb) * np.linalg.norm(embeddings[j]) + 1e-8
            )
            if similarity > similarity_threshold:
                is_duplicate = True
                break
        if not is_duplicate:
            unique_indices.append(i)
    
    # Reconstruct
    unique_sentences = [sentences[i] for i in unique_indices]
    
    deduped = len(sentences) - len(unique_sentences)
    if deduped > 0:
        print(f"  [DEDUPE] Removed {deduped} similar sentences")
    
    return '. '.join(unique_sentences) + '.'


# =============================================================================
# Linguistic compression (NLTK)
# =============================================================================

def _linguistic_compress(text: str) -> str:
    """
    Compress text using NLP techniques:
    - Remove stopwords
    - Stem words
    - Remove filler phrases
    """
    # Remove filler phrases first
    text = _remove_fillers(text)
    
    # Process sentence by sentence to preserve some structure
    if NLTK_AVAILABLE:
        sentences = sent_tokenize(text)
    else:
        sentences = re.split(r'[.!?]+', text)
    
    compressed = []
    for sent in sentences:
        if len(sent.strip()) < 10:
            continue
        
        # Tokenize and filter
        words = word_tokenize(sent) if NLTK_AVAILABLE else sent.split()
        
        # Remove stopwords and stem
        filtered = []
        for w in words:
            w_lower = w.lower().strip('.,!?:;()[]{}')
            if w_lower and w_lower not in STOPWORDS and len(w_lower) > 2:
                if STEMMER:
                    filtered.append(STEMMER.stem(w_lower))
                else:
                    filtered.append(w_lower)
        
        if filtered:
            compressed.append(' '.join(filtered))
    
    return '. '.join(compressed)


def _remove_fillers(text: str) -> str:
    """Remove common filler phrases."""
    fillers = [
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
        r'\bAs mentioned previously\b',
        r'\bAs I mentioned\b',
        r'\bBasically\b',
        r'\bEssentially\b',
        r'\bActually\b',
        r'\bObviously\b',
        r'\bClearly\b',
    ]
    
    for filler in fillers:
        text = re.sub(filler, '', text, flags=re.IGNORECASE)
    
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


# =============================================================================
# Fallback compression (no dependencies)
# =============================================================================

BASIC_STOPWORDS = frozenset({
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'to', 'of',
    'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through',
    'during', 'before', 'after', 'above', 'below', 'between', 'under',
    'again', 'further', 'then', 'once', 'here', 'there', 'when', 'where',
    'why', 'how', 'all', 'each', 'both', 'few', 'more', 'most', 'other',
    'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than',
    'too', 'very', 'just', 'also', 'now', 'i', 'me', 'my', 'myself', 'we',
    'our', 'ours', 'you', 'your', 'he', 'him', 'his', 'she', 'her', 'it',
    'its', 'they', 'them', 'their', 'this', 'that', 'these', 'those', 'am',
    'and', 'but', 'if', 'or', 'because', 'until', 'while', 'about',
})


def _basic_compress(text: str) -> str:
    """Basic compression without NLP libraries."""
    text = _remove_fillers(text)
    
    words = text.split()
    filtered = [w for w in words if w.lower().strip('.,!?:;') not in BASIC_STOPWORDS]
    
    return ' '.join(filtered)


# =============================================================================
# Smart truncation (preserve important parts)
# =============================================================================

def _smart_truncate(text: str, target_len: int) -> str:
    """
    Truncate to target length while preserving structure.
    
    Keeps:
    - All headers
    - Beginning and end of each section
    """
    if len(text) <= target_len:
        return text
    
    sections = _split_into_sections(text)
    
    # Calculate budget per section
    total_content = sum(len(c) for _, c in sections)
    ratio = target_len / max(total_content, 1)
    
    truncated = []
    for header, content in sections:
        section_budget = int(len(content) * ratio * 0.9)  # 90% of proportional
        
        if len(content) <= section_budget:
            truncated.append((header, content))
        else:
            # Keep beginning and end
            half = section_budget // 2
            new_content = content[:half] + '\n...[truncated]...\n' + content[-half:]
            truncated.append((header, new_content))
    
    return _reassemble_sections(truncated)


# =============================================================================
# Module interface
# =============================================================================

def get_compression_status() -> dict:
    """Return status of compression capabilities."""
    return {
        "nltk": NLTK_AVAILABLE,
        "sentence_transformers": SENTENCE_TRANSFORMERS_AVAILABLE,
        "expected_reduction": "70-85%" if SENTENCE_TRANSFORMERS_AVAILABLE else "40-50%"
    }


def compress_episodic_wakes(wakes: List[dict], max_output_chars: int = 20000) -> str:
    """
    Compress a list of wake entries using semantic clustering.
    
    Groups similar wakes together, keeps one representative per cluster.
    """
    if not wakes:
        return "(no wakes)"
    
    if not SENTENCE_TRANSFORMERS_AVAILABLE:
        # Fallback: just format and truncate
        lines = []
        for w in wakes[:50]:  # Max 50
            wake_num = w.get("wake_num", "?")
            action = w.get("action", "?")
            final = w.get("final_text", "")[:100]
            lines.append(f"#{wake_num} [{action}] {final}")
        
        result = '\n'.join(lines)
        if len(result) > max_output_chars:
            result = result[:max_output_chars] + "\n...[truncated]..."
        return result
    
    # Semantic clustering
    model = _get_embedding_model()
    
    # Extract summaries from each wake
    summaries = []
    for w in wakes:
        final = w.get("final_text", "")[:200]
        action = w.get("action", "")
        summaries.append(f"{action}: {final}")
    
    # Get embeddings and cluster
    try:
        embeddings = model.encode(summaries, show_progress_bar=False)
    except Exception as e:
        print(f"  [COMPRESS] Wake clustering failed: {e}")
        return '\n'.join(summaries[:30])
    
    # Cluster similar wakes (greedy)
    clusters = []  # List of (representative_idx, [member_indices])
    used = set()
    
    for i, emb in enumerate(embeddings):
        if i in used:
            continue
        
        cluster = [i]
        used.add(i)
        
        for j in range(i + 1, len(embeddings)):
            if j in used:
                continue
            
            similarity = np.dot(emb, embeddings[j]) / (
                np.linalg.norm(emb) * np.linalg.norm(embeddings[j]) + 1e-8
            )
            if similarity > 0.75:  # Same cluster
                cluster.append(j)
                used.add(j)
        
        clusters.append((i, cluster))
    
    # Format clusters
    lines = []
    for rep_idx, members in clusters:
        w = wakes[rep_idx]
        wake_num = w.get("wake_num", "?")
        action = w.get("action", "?")
        final = w.get("final_text", "")[:150]
        
        if len(members) > 1:
            member_nums = [wakes[m].get("wake_num", "?") for m in members[:5]]
            lines.append(f"#{wake_num}+{len(members)-1} [{action}] {final} (also: {member_nums})")
        else:
            lines.append(f"#{wake_num} [{action}] {final}")
    
    result = '\n'.join(lines)
    
    print(f"  [CLUSTER] {len(wakes)} wakes → {len(clusters)} clusters")
    
    if len(result) > max_output_chars:
        result = result[:max_output_chars] + "\n...[truncated]..."
    
    return result
