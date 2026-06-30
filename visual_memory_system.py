import os
import logging
from typing import List, Dict, Optional, Union
from PIL import Image
import requests
from io import BytesIO
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http import models
from datetime import datetime

logger = logging.getLogger("serin_ai")

class VisualMemorySystem:
    """
    The Visual Cortex of Serin.
    Uses CLIP embeddings to store and recall visual memories (images).
    """
    def __init__(self, qdrant_client: QdrantClient, collection_name: str = "visual_memory") -> None:
        self.client = qdrant_client
        self.collection_name = collection_name
        
        # Load CLIP model (lightweight, runs on CPU/GPU)
        # clip-ViT-B-32 is a good balance of speed and performance
        logger.info(" Initializing Visual Cortex (CLIP model)...")
        try:
            self.model = SentenceTransformer('clip-ViT-B-32')
            logger.info(" Visual Cortex (CLIP) online")
        except Exception as e:
            logger.error(f" Failed to load CLIP model: {e}")
            self.model = None

        # Ensure collection exists
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """Create visual memory collection if it doesn't exist"""
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            
            if not exists:
                logger.info(f"Creating visual memory collection: {self.collection_name}")
                # CLIP ViT-B-32 output dimension is 512
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=512,
                        distance=models.Distance.COSINE
                    )
                )
        except Exception as e:
            logger.error(f" Error checking/creating visual collection: {e}")

    def _download_image(self, url: str) -> Optional[Image.Image]:
        """Download image from URL"""
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return Image.open(BytesIO(response.content))
        except Exception as e:
            logger.error(f" Failed to download image: {e}")
            return None

    def embed_image(self, image: Union[Image.Image, str]) -> Optional[List[float]]:
        """Generate embedding for an image (URL or PIL Image)"""
        if not self.model:
            return None
            
        try:
            if isinstance(image, str):
                img_obj = self._download_image(image)
                if not img_obj:
                    return None
            else:
                img_obj = image
                
            # Generate embedding
            embedding = self.model.encode(img_obj)
            return embedding.tolist()
        except Exception as e:
            logger.error(f" Error embedding image: {e}")
            return None

    def analyze_image(self, image_url: str) -> Optional[str]:
        """
        Deprecated: Image analysis is now handled by the VLM directly.
        Raises NotImplementedError to signal callers to use VLM instead.
        """
        raise NotImplementedError("Image analysis is now handled by the VLM directly")

    def store_image_memory(
        self,
        image_url: str,
        user_id: str,
        username: str,
        channel_id: str,
        context_text: str = ""
    ) -> bool:
        """Store an image in visual memory"""
        try:
            embedding = self.embed_image(image_url)
            if not embedding:
                return False
            
            # Create unique ID based on timestamp (must be integer for Qdrant)
            import uuid
            point_id = str(uuid.uuid4())
            
            payload = {
                "type": "image",
                "url": image_url,
                "user_id": user_id,
                "username": username,
                "channel_id": channel_id,
                "context": context_text,
                "timestamp": datetime.now().isoformat()
            }
            
            self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    models.PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload=payload
                    )
                ]
            )
            logger.info(f"📸 Visual memory stored for {username}")
            return True
        except Exception as e:
            logger.error(f" Error storing visual memory: {e}")
            return False

    def recall_image(self, image_url: str, threshold: float = 0.85) -> List[Dict]:
        """
        Recall similar images from memory.
        Returns list of matches with metadata.
        """
        try:
            embedding = self.embed_image(image_url)
            if not embedding:
                return []
            
            # Use query_points instead of deprecated search
            results = self.client.query_points(
                collection_name=self.collection_name,
                query=embedding,
                limit=3,
                score_threshold=threshold
            )
            
            matches = []
            for hit in results.points:
                matches.append({
                    "score": hit.score,
                    "username": hit.payload.get("username"),
                    "context": hit.payload.get("context"),
                    "timestamp": hit.payload.get("timestamp"),
                    "url": hit.payload.get("url")
                })
            
            return matches
        except Exception as e:
            logger.error(f" Error recalling visual memory: {e}")
            return []

    def recall_image_from_bytes(self, image_bytes: bytes, threshold: float = 0.85) -> List[Dict]:
        """
        Recall similar images from raw bytes (avoids re-downloading).
        Returns list of matches with metadata.
        """
        if not self.model or not image_bytes:
            return []
        try:
            img_obj = Image.open(BytesIO(image_bytes))
            embedding = self.model.encode(img_obj).tolist()
            results = self.client.query_points(
                collection_name=self.collection_name,
                query=embedding,
                limit=3,
                score_threshold=threshold
            )
            return [
                {
                    "score": hit.score,
                    "username": hit.payload.get("username"),
                    "context": hit.payload.get("context"),
                    "timestamp": hit.payload.get("timestamp"),
                    "url": hit.payload.get("url"),
                }
                for hit in results.points
            ]
        except Exception as e:
            logger.error(f" Error recalling visual memory from bytes: {e}")
            return []

    def store_image_from_bytes(
        self,
        image_bytes: bytes,
        image_url: str,
        user_id: str,
        username: str,
        channel_id: str,
        context_text: str = ""
    ) -> bool:
        """
        Store an image from raw bytes (avoids re-downloading for CLIP).
        """
        if not self.model or not image_bytes:
            return False
        try:
            img_obj = Image.open(BytesIO(image_bytes))
            embedding = self.model.encode(img_obj).tolist()
            import uuid
            point_id = str(uuid.uuid4())
            payload = {
                "type": "image",
                "url": image_url,
                "user_id": user_id,
                "username": username,
                "channel_id": channel_id,
                "context": context_text,
                "timestamp": datetime.now().isoformat(),
            }
            self.client.upsert(
                collection_name=self.collection_name,
                points=[models.PointStruct(id=point_id, vector=embedding, payload=payload)],
            )
            logger.info(f"📸 Visual memory stored from bytes for {username}")
            return True
        except Exception as e:
            logger.error(f" Error storing visual memory from bytes: {e}")
            return False
