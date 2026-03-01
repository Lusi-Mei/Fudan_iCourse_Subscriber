"""Speech-to-text using ffmpeg pipe + sherpa-onnx SenseVoice + silero VAD."""

import os
import subprocess
import time

import numpy as np
import sherpa_onnx

from . import config


class Transcriber:
    """SenseVoice-based transcriber with VAD segmentation."""

    def __init__(self):
        self._recognizer = None
        self._vad = None

    def _init(self):
        if self._recognizer is not None:
            return

        model_dir = config.SENSEVOICE_MODEL_DIR
        model_path = os.path.join(model_dir, "model.int8.onnx")
        tokens_path = os.path.join(model_dir, "tokens.txt")
        vad_path = config.SILERO_VAD_PATH

        for p, name in [(model_path, "SenseVoice model"), (tokens_path, "tokens.txt"), (vad_path, "silero_vad.onnx")]:
            if not os.path.isfile(p):
                raise FileNotFoundError(
                    f"{name} not found at '{p}'. "
                    f"Download from https://github.com/k2-fsa/sherpa-onnx/releases/tag/asr-models"
                )

        print("[Transcriber] Loading SenseVoice model...")
        self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=model_path,
            tokens=tokens_path,
            use_itn=True,
            num_threads=2,
            debug=False,
        )

        vad_config = sherpa_onnx.VadModelConfig()
        vad_config.silero_vad.model = vad_path
        vad_config.silero_vad.min_silence_duration = 0.25
        vad_config.sample_rate = 16000
        self._vad = sherpa_onnx.VoiceActivityDetector(vad_config, buffer_size_in_seconds=120)
        print("[Transcriber] Model loaded.")

    def _drain_segments(self, texts: list[str]):
        """Recognize and collect all complete speech segments from VAD."""
        while not self._vad.empty():
            segment = self._vad.front.samples
            self._vad.pop()
            stream = self._recognizer.create_stream()
            stream.accept_waveform(16000, segment)
            self._recognizer.decode_stream(stream)
            text = stream.result.text.strip()
            if text:
                texts.append(text)

    def transcribe_video(self, video_path: str) -> str:
        """Transcribe a video file directly via ffmpeg pipe.

        ffmpeg decodes video → 16kHz mono PCM stream
        → silero VAD splits into speech segments
        → SenseVoice recognizes each segment
        → returns concatenated text.
        """
        self._init()
        t0 = time.time()

        # Drain any leftover VAD state from a previous (possibly failed) call
        self._vad.flush()
        while not self._vad.empty():
            self._vad.pop()

        cmd = [
            "ffmpeg", "-i", video_path,
            "-ar", "16000", "-ac", "1",
            "-f", "f32le", "-"
        ]
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )

        sample_rate = 16000
        window_size = 512  # samples per VAD window (32ms at 16kHz)
        chunk_size = 16000  # read 1 second at a time from ffmpeg
        bytes_per_sample = 4  # float32

        texts = []
        total_read = 0

        while True:
            raw = proc.stdout.read(chunk_size * bytes_per_sample)
            if not raw:
                break

            samples = np.frombuffer(raw, dtype=np.float32)
            total_read += len(samples)

            # Feed samples to VAD in window-sized chunks
            idx = 0
            while idx + window_size <= len(samples):
                self._vad.accept_waveform(samples[idx:idx + window_size])
                idx += window_size

                # Process any complete speech segments
                self._drain_segments(texts)

            # Handle remaining samples (less than window_size)
            if idx < len(samples):
                self._vad.accept_waveform(samples[idx:])

        # Flush VAD
        self._vad.flush()
        self._drain_segments(texts)

        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg exited with code {proc.returncode}")
        elapsed = time.time() - t0
        duration = total_read / sample_rate
        transcript = " ".join(texts)
        print(f"[Transcriber] Done: {duration:.0f}s audio, {len(transcript)} chars, {len(texts)} segments in {elapsed:.0f}s")
        return transcript
