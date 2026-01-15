#!/usr/bin/env python3
"""
Multi-Database Memory System for Mira's Council of Minds.

6 databases: {haiku, sonnet, opus} × {short, long}
Plus archive for cold storage.

Sonnet uses creative indexing with 3x more combinations.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional, Any

# Configuration
CONFIG = {
    "haiku": {
        "short_capacity": 1000,
        "long_capacity": 10000,
        "search_top_k": 5,
        "combination_multiplier": 1,
    },
    "sonnet": {
        "short_capacity": 1500,
        "long_capacity": 15000,
        "search_top_k": 10,  # More results for creative variety
        "combination_multiplier": 3,  # Store 3x more entries
    },
    "opus": {
        "short_capacity": 1000,
        "long_capacity": 10000,
        "search_top_k": 5,
        "combination_multiplier": 1,
    },
}

# Lifecycle thresholds (in wakes)
LIFECYCLE = {
    "short_purge_threshold": 50,       # Purge if not accessed in N wakes
    "short_promote_min_age": 60,       # Must exist for N wakes to promote (after purge threshold)
    "short_promote_min_access": 3,     # Must be accessed N times to promote
    "long_archive_threshold": 500,     # Archive if not accessed in N wakes
}

_brain_memory = None

class MemoryEntry:
    """Single memory entry with metadata."""
    def __init__(self, content: str, source: str, model: str, wake: int,
                 combination_type: str = "original", parent_id: str = None):
        self.id = f"{model}_w{wake}_{datetime.now().strftime('%H%M%S%f')}"
        self.content = content
        self.source = source
        self.model = model
        self.combination_type = combination_type
        self.parent_id = parent_id
        self.wake_created = wake
        self.wake_last_accessed = wake
        self.access_count = 1
        self.importance = 0.5
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "source": self.source,
            "model": self.model,
            "combination_type": self.combination_type,
            "parent_id": self.parent_id,
            "wake_created": self.wake_created,
            "wake_last_accessed": self.wake_last_accessed,
            "access_count": self.access_count,
            "importance": self.importance,
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> 'MemoryEntry':
        entry = cls.__new__(cls)
        entry.id = d["id"]
        entry.content = d["content"]
        entry.source = d.get("source", "unknown")
        entry.model = d.get("model", "unknown")
        entry.combination_type = d.get("combination_type", "original")
        entry.parent_id = d.get("parent_id")
        entry.wake_created = d.get("wake_created", 0)
        entry.wake_last_accessed = d.get("wake_last_accessed", 0)
        entry.access_count = d.get("access_count", 1)
        entry.importance = d.get("importance", 0.5)
        return entry
    
    def touch(self, wake: int):
        """Update access metadata."""
        self.wake_last_accessed = wake
        self.access_count += 1


class SimpleMemoryDB:
    """Simple keyword-based memory database (fallback when ChromaDB unavailable)."""
    
    def __init__(self, path: Path):
        self.path = path
        self.entries: Dict[str, MemoryEntry] = {}
        self._load()
    
    def _load(self):
        if self.path.exists():
            try:
                with open(self.path) as f:
                    for line in f:
                        if line.strip():
                            d = json.loads(line)
                            entry = MemoryEntry.from_dict(d)
                            self.entries[entry.id] = entry
            except:
                pass
    
    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, 'w') as f:
            for entry in self.entries.values():
                f.write(json.dumps(entry.to_dict()) + "\n")
    
    def add(self, entry: MemoryEntry) -> bool:
        self.entries[entry.id] = entry
        self._save()
        return True
    
    def search(self, query: str, top_k: int = 5, current_wake: int = 0) -> List[MemoryEntry]:
        """Simple keyword search with access tracking."""
        query_terms = query.lower().split()
        scored = []
        for entry in self.entries.values():
            content_lower = entry.content.lower()
            score = sum(1 for term in query_terms if term in content_lower)
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [entry for _, entry in scored[:top_k]]
        # Update access metadata
        for entry in results:
            entry.touch(current_wake)
        self._save()
        return results
    
    def get(self, entry_id: str) -> Optional[MemoryEntry]:
        return self.entries.get(entry_id)
    
    def remove(self, entry_id: str) -> bool:
        if entry_id in self.entries:
            del self.entries[entry_id]
            self._save()
            return True
        return False
    
    def all_entries(self) -> List[MemoryEntry]:
        return list(self.entries.values())
    
    def count(self) -> int:
        return len(self.entries)


class ChromaMemoryDB:
    """ChromaDB-based semantic memory database."""
    
    def __init__(self, path: Path, collection_name: str):
        import chromadb
        self.path = path
        self.collection_name = collection_name
        self.client = chromadb.PersistentClient(path=str(path))
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        # Keep metadata in separate file for lifecycle management
        self.meta_path = path / f"{collection_name}_meta.jsonl"
        self.metadata: Dict[str, dict] = {}
        self._load_metadata()
    
    def _load_metadata(self):
        if self.meta_path.exists():
            try:
                with open(self.meta_path) as f:
                    for line in f:
                        if line.strip():
                            d = json.loads(line)
                            self.metadata[d["id"]] = d
            except:
                pass
    
    def _save_metadata(self):
        self.meta_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.meta_path, 'w') as f:
            for meta in self.metadata.values():
                f.write(json.dumps(meta) + "\n")
    
    def add(self, entry: MemoryEntry) -> bool:
        try:
            self.collection.add(
                ids=[entry.id],
                documents=[entry.content],
                metadatas=[{"source": entry.source, "model": entry.model}]
            )
            self.metadata[entry.id] = entry.to_dict()
            self._save_metadata()
            return True
        except Exception as e:
            print(f"ChromaDB add error: {e}")
            return False
    
    def search(self, query: str, top_k: int = 5, current_wake: int = 0) -> List[MemoryEntry]:
        try:
            results = self.collection.query(query_texts=[query], n_results=top_k)
            entries = []
            for doc_id in results["ids"][0]:
                if doc_id in self.metadata:
                    entry = MemoryEntry.from_dict(self.metadata[doc_id])
                    entry.touch(current_wake)
                    self.metadata[doc_id] = entry.to_dict()
                    entries.append(entry)
            self._save_metadata()
            return entries
        except Exception as e:
            print(f"ChromaDB search error: {e}")
            return []
    
    def get(self, entry_id: str) -> Optional[MemoryEntry]:
        if entry_id in self.metadata:
            return MemoryEntry.from_dict(self.metadata[entry_id])
        return None
    
    def remove(self, entry_id: str) -> bool:
        try:
            self.collection.delete(ids=[entry_id])
            if entry_id in self.metadata:
                del self.metadata[entry_id]
                self._save_metadata()
            return True
        except:
            return False
    
    def all_entries(self) -> List[MemoryEntry]:
        return [MemoryEntry.from_dict(m) for m in self.metadata.values()]
    
    def count(self) -> int:
        return len(self.metadata)


def create_db(path: Path, name: str):
    """Create appropriate database (ChromaDB if available, else Simple)."""
    try:
        import chromadb
        return ChromaMemoryDB(path, name)
    except ImportError:
        return SimpleMemoryDB(path / f"{name}.jsonl")


class ModelMemory:
    """Memory system for a single model (short + long term)."""
    
    def __init__(self, model: str, base_path: Path):
        self.model = model
        self.config = CONFIG[model]
        self.short = create_db(base_path / f"{model}_short", f"{model}_short")
        self.long = create_db(base_path / f"{model}_long", f"{model}_long")
    
    def add(self, content: str, source: str, wake: int, tier: str = "short") -> bool:
        """Add memory, with creative combinations for Sonnet."""
        entries = self._generate_entries(content, source, wake)
        db = self.short if tier == "short" else self.long
        success = True
        for entry in entries:
            if not db.add(entry):
                success = False
        return success
    
    def _generate_entries(self, content: str, source: str, wake: int) -> List[MemoryEntry]:
        """Generate memory entries, with extra combinations for Sonnet."""
        entries = []
        # Original entry
        original = MemoryEntry(content, source, self.model, wake, "original")
        entries.append(original)
        # Creative combinations (Sonnet only)
        if self.config["combination_multiplier"] > 1:
            # Extract key phrases
            words = content.split()
            if len(words) > 5:
                # First half
                first_half = " ".join(words[:len(words)//2])
                entries.append(MemoryEntry(
                    first_half, source, self.model, wake,
                    "fragment_first", original.id
                ))
                # Second half
                second_half = " ".join(words[len(words)//2:])
                entries.append(MemoryEntry(
                    second_half, source, self.model, wake,
                    "fragment_second", original.id
                ))
            # Extract noun phrases / key terms (simplified)
            if len(words) > 3:
                # Middle chunk
                mid_start = len(words) // 4
                mid_end = mid_start + len(words) // 2
                middle = " ".join(words[mid_start:mid_end])
                entries.append(MemoryEntry(
                    middle, source, self.model, wake,
                    "core_concept", original.id
                ))
        return entries
    
    def search(self, query: str, wake: int, include_long: bool = True) -> List[dict]:
        """Search memory, returning formatted results."""
        results = []
        # Search short-term
        short_results = self.short.search(query, self.config["search_top_k"], wake)
        for entry in short_results:
            results.append({
                "content": entry.content,
                "tier": "short",
                "wake_created": entry.wake_created,
                "wake_last_accessed": entry.wake_last_accessed,
                "access_count": entry.access_count,
                "source": entry.source,
            })
        # Search long-term
        if include_long:
            long_k = max(3, self.config["search_top_k"] // 2)
            long_results = self.long.search(query, long_k, wake)
            for entry in long_results:
                results.append({
                    "content": entry.content,
                    "tier": "long",
                    "wake_created": entry.wake_created,
                    "wake_last_accessed": entry.wake_last_accessed,
                    "access_count": entry.access_count,
                    "source": entry.source,
                })
        return results
    
    def stats(self) -> dict:
        return {
            "model": self.model,
            "short_count": self.short.count(),
            "long_count": self.long.count(),
            "short_capacity": self.config["short_capacity"],
            "long_capacity": self.config["long_capacity"],
        }


class BrainMemory:
    """Complete brain memory system with 6 databases."""
    
    def __init__(self, base_path: Path):
        self.base_path = base_path / "memory_db"
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.haiku = ModelMemory("haiku", self.base_path)
        self.sonnet = ModelMemory("sonnet", self.base_path)
        self.opus = ModelMemory("opus", self.base_path)
        self.archive = create_db(self.base_path / "archive", "archive")
        self._models = {"haiku": self.haiku, "sonnet": self.sonnet, "opus": self.opus}
    
    def add(self, content: str, source: str, model: str, wake: int) -> bool:
        """Add memory to specified model's short-term."""
        if model not in self._models:
            return False
        return self._models[model].add(content, source, wake, "short")
    
    def search(self, query: str, model: str, wake: int) -> List[dict]:
        """Search specified model's memory."""
        if model not in self._models:
            return []
        return self._models[model].search(query, wake)
    
    def search_all(self, query: str, wake: int) -> Dict[str, List[dict]]:
        """Search all models' memories."""
        return {
            "haiku": self.haiku.search(query, wake),
            "sonnet": self.sonnet.search(query, wake),
            "opus": self.opus.search(query, wake),
        }
    
    def promote(self, entry_id: str, model: str) -> bool:
        """Promote entry from short-term to long-term."""
        if model not in self._models:
            return False
        mem = self._models[model]
        entry = mem.short.get(entry_id)
        if entry:
            mem.long.add(entry)
            mem.short.remove(entry_id)
            return True
        return False
    
    def archive_entry(self, entry_id: str, model: str) -> bool:
        """Move entry from long-term to archive."""
        if model not in self._models:
            return False
        mem = self._models[model]
        entry = mem.long.get(entry_id)
        if entry:
            self.archive.add(entry)
            mem.long.remove(entry_id)
            return True
        return False
    
    def stats(self) -> dict:
        return {
            "haiku": self.haiku.stats(),
            "sonnet": self.sonnet.stats(),
            "opus": self.opus.stats(),
            "archive_count": self.archive.count(),
        }
    
    def format_for_prompt(self, model: str, query: str, wake: int) -> str:
        """Format memories for injection into model prompt."""
        results = self.search(query, model, wake)
        seen_content = {r["content"] for r in results}
        # Also get recent entries regardless of search match
        if model in self._models:
            mem = self._models[model]
            recent = []
            for entry in mem.short.all_entries():
                if entry.content not in seen_content:
                    recent.append({
                        "content": entry.content,
                        "tier": "short",
                        "wake_created": entry.wake_created,
                        "wake_last_accessed": entry.wake_last_accessed,
                        "access_count": entry.access_count,
                        "source": entry.source,
                    })
            # Sort by wake_created descending, take 5 most recent
            recent.sort(key=lambda x: x["wake_created"], reverse=True)
            results.extend(recent[:5])
        if not results:
            return ""
        lines = [f"=== YOUR MEMORIES ({model}) ==="]
        for r in results[:10]:  # Limit for context
            lines.append(f"[{r['tier']}|w{r['wake_created']}|{r['access_count']}x] {r['content'][:300]}")
        lines.append("===")
        return "\n".join(lines)


def get_brain_memory(base_path: str) -> BrainMemory:
    """Get or create global brain memory instance."""
    global _brain_memory
    if _brain_memory is None:
        _brain_memory = BrainMemory(Path(base_path))
    return _brain_memory
