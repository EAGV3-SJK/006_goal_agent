import os
import json
import hashlib
from typing import Dict, Any

from schema import Artifact

class ArtifactStore:
    """Session 6 content-addressable ArtifactStore.
    Saves raw binary data and structured metadata under state/artifacts/.
    Identical payloads deduplicate based on SHA-256 hash handles.
    """
    
    def __init__(self, base_dir: str = "state/artifacts"):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def _paths_for_id(self, artifact_id: str) -> tuple[str, str]:
        """Utility to get the absolute paths for .bin and .json files from an artifact handle."""
        # Strip "art:" prefix to get the sha256 prefix
        if artifact_id.startswith("art:"):
            sha_prefix = artifact_id[4:]
        else:
            sha_prefix = artifact_id
            
        bin_path = os.path.join(self.base_dir, f"{sha_prefix}.bin")
        json_path = os.path.join(self.base_dir, f"{sha_prefix}.json")
        return bin_path, json_path

    def put(self, blob: bytes, *, content_type: str, source: str, descriptor: str) -> str:
        """Puts raw bytes into the content-addressable store.
        
        Args:
            blob: The raw binary payload to write.
            content_type: MIME type or format of the data.
            source: Source trace identifier.
            descriptor: Brief descriptor of the artifact content.
            
        Returns:
            The artifact ID string of the form "art:<sha256-prefix>".
        """
        # Calculate SHA-256 hash of the blob
        sha256_hash = hashlib.sha256(blob).hexdigest()
        sha_prefix = sha256_hash[:12]  # Use first 12 hex characters as standard short prefix
        artifact_id = f"art:{sha_prefix}"
        
        bin_path, json_path = self._paths_for_id(artifact_id)
        
        # Write binary content atomically if it doesn't already exist (deduplication)
        if not os.path.exists(bin_path):
            temp_bin = f"{bin_path}.tmp"
            try:
                with open(temp_bin, "wb") as f:
                    f.write(blob)
                if os.path.exists(bin_path):
                    os.remove(bin_path)
                os.rename(temp_bin, bin_path)
            except Exception as e:
                if os.path.exists(temp_bin):
                    try:
                        os.remove(temp_bin)
                    except Exception:
                        pass
                raise e
                
        # Write metadata JSON atomically if it doesn't already exist (deduplication)
        if not os.path.exists(json_path):
            meta = Artifact(
                id=artifact_id,
                content_type=content_type,
                size_bytes=len(blob),
                source=source,
                descriptor=descriptor
            )
            
            temp_json = f"{json_path}.tmp"
            try:
                with open(temp_json, "w", encoding="utf-8") as f:
                    # Leverage Pydantic serialization
                    f.write(meta.model_dump_json(indent=2))
                if os.path.exists(json_path):
                    os.remove(json_path)
                os.rename(temp_json, json_path)
            except Exception as e:
                if os.path.exists(temp_json):
                    try:
                        os.remove(temp_json)
                    except Exception:
                        pass
                raise e
                
        return artifact_id

    def get_bytes(self, artifact_id: str) -> bytes:
        """Retrieves raw binary payload for the given artifact ID.
        
        Args:
            artifact_id: The handle of the form "art:<sha256-prefix>".
            
        Returns:
            The raw bytes from storage.
            
        Raises:
            FileNotFoundError: If the artifact does not exist in the store.
        """
        bin_path, _ = self._paths_for_id(artifact_id)
        if not os.path.exists(bin_path):
            raise FileNotFoundError(f"Artifact payload not found for ID: {artifact_id}")
            
        with open(bin_path, "rb") as f:
            return f.read()

    def get_meta(self, artifact_id: str) -> Artifact:
        """Retrieves structured Artifact metadata for the given ID.
        
        Args:
            artifact_id: The handle of the form "art:<sha256-prefix>".
            
        Returns:
            An Artifact Pydantic model instance.
            
        Raises:
            FileNotFoundError: If the artifact metadata does not exist.
        """
        _, json_path = self._paths_for_id(artifact_id)
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"Artifact metadata not found for ID: {artifact_id}")
            
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return Artifact.model_validate(data)

    def exists(self, artifact_id: str) -> bool:
        """Checks if both binary and metadata files for the given ID exist in storage."""
        bin_path, json_path = self._paths_for_id(artifact_id)
        return os.path.exists(bin_path) and os.path.exists(json_path)
