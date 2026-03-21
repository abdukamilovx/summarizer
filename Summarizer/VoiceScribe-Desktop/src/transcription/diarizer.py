"""
Speaker diarization using voice embeddings and spectral clustering.
Identifies distinct speakers and labels transcript segments accordingly.
"""
import numpy as np
from typing import Optional

from transcription.engine import TranscriptionSegment
from utils.logger import log


class SpeakerDiarizer:
    """Assigns speaker labels to transcript segments based on voice embeddings.

    Uses resemblyzer for voice embeddings and spectral clustering
    to group segments by speaker identity.
    """

    def __init__(
        self,
        num_speakers: Optional[int] = None,
        sample_rate: int = 16000,
    ):
        self._num_speakers = num_speakers
        self._sample_rate = sample_rate
        self._encoder = None

    def _ensure_encoder(self):
        if self._encoder is None:
            log.info("Loading voice encoder model...")
            from resemblyzer import VoiceEncoder
            self._encoder = VoiceEncoder()
            log.info("Voice encoder loaded")

    def diarize(
        self,
        audio: np.ndarray,
        segments: list[TranscriptionSegment],
    ) -> list[TranscriptionSegment]:
        """Assign speaker labels to segments based on voice similarity.

        Args:
            audio: Full audio recording as numpy array (mono, 16kHz).
            segments: Transcript segments with timestamps.

        Returns:
            Same segments with `speaker` field set to "Speaker 1", "Speaker 2", etc.
        """
        if not segments:
            return segments

        self._ensure_encoder()

        # Extract embeddings for each segment
        embeddings = []
        valid_indices = []

        for i, seg in enumerate(segments):
            seg_audio = self._extract_audio(audio, seg.start, seg.end)

            # Skip very short segments (< 0.5s) — unreliable embeddings
            if len(seg_audio) < self._sample_rate * 0.5:
                continue

            try:
                from resemblyzer import preprocess_wav
                # Preprocess: normalize + trim silence
                processed = preprocess_wav(seg_audio, source_sr=self._sample_rate)
                if len(processed) < 1600:  # too short after preprocessing
                    continue

                embedding = self._encoder.embed_utterance(processed)
                embeddings.append(embedding)
                valid_indices.append(i)
            except Exception as e:
                log.warning(f"Failed to embed segment {i}: {e}")

        if len(embeddings) < 2:
            log.warning("Not enough segments for diarization (need at least 2)")
            if embeddings:
                segments[valid_indices[0]].speaker = "Speaker 1"
            return segments

        embedding_matrix = np.array(embeddings)
        log.info(f"Computing speaker clusters for {len(embeddings)} segments...")

        # Determine number of speakers
        n_speakers = self._num_speakers or self._estimate_num_speakers(embedding_matrix)
        n_speakers = min(n_speakers, len(embeddings))

        # Cluster embeddings
        labels = self._cluster(embedding_matrix, n_speakers)

        # Map cluster labels to "Speaker 1", "Speaker 2", ... by order of appearance
        label_map = {}
        speaker_counter = 0
        for label in labels:
            if label not in label_map:
                speaker_counter += 1
                label_map[label] = f"Speaker {speaker_counter}"

        # Assign speaker labels to valid segments
        for idx, label in zip(valid_indices, labels):
            segments[idx].speaker = label_map[label]

        # For skipped short segments, assign nearest valid segment's speaker
        self._fill_missing_speakers(segments, valid_indices)

        n_found = len(label_map)
        log.info(f"Diarization complete: {n_found} speakers identified")
        return segments

    def _extract_audio(self, audio: np.ndarray, start: float, end: float) -> np.ndarray:
        """Extract audio slice by timestamps."""
        start_idx = max(0, int(start * self._sample_rate))
        end_idx = min(len(audio), int(end * self._sample_rate))
        return audio[start_idx:end_idx]

    def _estimate_num_speakers(self, embeddings: np.ndarray) -> int:
        """Estimate optimal number of speakers using silhouette score."""
        from sklearn.cluster import SpectralClustering
        from sklearn.metrics import silhouette_score

        max_k = min(6, len(embeddings) - 1)
        if max_k < 2:
            return 2

        best_k = 2
        best_score = -1

        for k in range(2, max_k + 1):
            try:
                clustering = SpectralClustering(
                    n_clusters=k,
                    affinity="cosine",
                    random_state=42,
                    n_init=3,
                )
                labels = clustering.fit_predict(embeddings)

                if len(set(labels)) < 2:
                    continue

                score = silhouette_score(embeddings, labels, metric="cosine")
                if score > best_score:
                    best_score = score
                    best_k = k
            except Exception:
                continue

        log.info(f"Estimated {best_k} speakers (silhouette={best_score:.3f})")
        return best_k

    def _cluster(self, embeddings: np.ndarray, n_clusters: int) -> np.ndarray:
        """Cluster embeddings into speaker groups."""
        from sklearn.cluster import SpectralClustering

        clustering = SpectralClustering(
            n_clusters=n_clusters,
            affinity="cosine",
            random_state=42,
            n_init=5,
        )
        return clustering.fit_predict(embeddings)

    def _fill_missing_speakers(
        self,
        segments: list[TranscriptionSegment],
        valid_indices: list[int],
    ):
        """Fill in speaker labels for segments that were too short to embed."""
        if not valid_indices:
            return

        for i, seg in enumerate(segments):
            if seg.speaker is not None:
                continue

            # Find the nearest valid segment by index
            nearest_idx = min(valid_indices, key=lambda vi: abs(vi - i))
            seg.speaker = segments[nearest_idx].speaker
