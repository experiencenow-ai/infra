#!/usr/bin/env python3
"""
Creative Indexing for Sonnet (Right Brain).

Generates multiple memory entries from a single thought:
1. Original content
2. Fragment variations
3. Cross-domain links (extracted patterns)
4. Concept combinations

This enables unexpected retrieval - searching for "democracy" might
retrieve a memory about "consensus voting" from a blockchain discussion.
"""

import re
from typing import List, Tuple

# Common cross-domain concepts that might link disparate ideas
CONCEPT_BRIDGES = {
    # Patterns that appear across domains
    "voting": ["consensus", "democracy", "election", "choice", "decision"],
    "network": ["graph", "web", "connection", "nodes", "distributed"],
    "flow": ["stream", "current", "movement", "pipe", "channel"],
    "cycle": ["loop", "iteration", "rhythm", "pattern", "recurring"],
    "layer": ["stack", "level", "hierarchy", "abstraction", "tier"],
    "key": ["unlock", "access", "secret", "cryptographic", "essential"],
    "root": ["origin", "base", "foundation", "source", "fundamental"],
    "branch": ["fork", "diverge", "tree", "path", "option"],
    "merge": ["combine", "unify", "integrate", "synthesis", "blend"],
    "transform": ["convert", "change", "morph", "evolve", "mutate"],
}


def extract_key_phrases(content: str) -> List[str]:
    """Extract potentially meaningful phrases from content."""
    # Remove common words
    stop_words = {
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
        'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as',
        'into', 'through', 'during', 'before', 'after', 'above', 'below',
        'between', 'under', 'again', 'further', 'then', 'once', 'here',
        'there', 'when', 'where', 'why', 'how', 'all', 'each', 'few',
        'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not',
        'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just',
        'and', 'but', 'if', 'or', 'because', 'until', 'while', 'this',
        'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we',
        'they', 'what', 'which', 'who', 'whom', 'myself', 'yourself',
    }
    words = re.findall(r'\b[a-zA-Z]{3,}\b', content.lower())
    meaningful = [w for w in words if w not in stop_words]
    phrases = []
    # Single words
    phrases.extend(meaningful[:10])
    # Bigrams from adjacent meaningful words
    for i in range(len(meaningful) - 1):
        phrases.append(f"{meaningful[i]} {meaningful[i+1]}")
    return phrases[:15]


def find_cross_domain_links(content: str) -> List[str]:
    """Find concepts that might link to other domains."""
    content_lower = content.lower()
    links = []
    for bridge_concept, related in CONCEPT_BRIDGES.items():
        if bridge_concept in content_lower:
            links.append(f"{bridge_concept} pattern")
            # Add some related concepts
            for rel in related[:2]:
                if rel not in content_lower:  # Don't duplicate
                    links.append(f"{bridge_concept}-{rel} link")
    return links


def generate_combinations(content: str, source: str) -> List[Tuple[str, str]]:
    """
    Generate multiple memory entries for creative retrieval.
    Returns list of (content, combination_type) tuples.
    """
    combinations = []
    # 1. Original
    combinations.append((content, "original"))
    # 2. Key phrases
    phrases = extract_key_phrases(content)
    for phrase in phrases[:5]:
        combinations.append((phrase, "key_phrase"))
    # 3. First/second half for longer content
    words = content.split()
    if len(words) > 10:
        mid = len(words) // 2
        combinations.append((" ".join(words[:mid]), "first_half"))
        combinations.append((" ".join(words[mid:]), "second_half"))
    # 4. Core (middle 50%)
    if len(words) > 8:
        start = len(words) // 4
        end = start + len(words) // 2
        combinations.append((" ".join(words[start:end]), "core_concept"))
    # 5. Cross-domain links
    links = find_cross_domain_links(content)
    for link in links[:3]:
        combinations.append((f"{link}: {content[:50]}", "cross_domain"))
    # 6. Question form (for retrieval by question)
    if not content.endswith('?'):
        combinations.append((f"What about {phrases[0] if phrases else 'this'}?", "question_form"))
    return combinations


def creative_chunk(content: str, max_chunks: int = 5) -> List[str]:
    """
    Chunk content creatively for overlapping retrieval.
    Unlike standard chunking, this creates overlapping windows.
    """
    sentences = re.split(r'[.!?]+', content)
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) <= 2:
        return [content]
    chunks = []
    # Standard sentences
    chunks.extend(sentences[:max_chunks])
    # Overlapping pairs
    for i in range(len(sentences) - 1):
        if len(chunks) >= max_chunks * 2:
            break
        chunks.append(f"{sentences[i]}. {sentences[i+1]}")
    return chunks[:max_chunks * 2]


if __name__ == "__main__":
    # Test
    test_content = "Blockchain consensus is like neurons voting in a distributed brain network."
    print("Original:", test_content)
    print("\nCombinations:")
    for content, ctype in generate_combinations(test_content, "test"):
        print(f"  [{ctype}] {content}")
