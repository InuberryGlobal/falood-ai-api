from faster_whisper import WhisperModel

class Transcriber:
    def __init__(self, model_size="tiny", device="cpu", compute_type="int8"):
        # Explicitly set cpu_threads=1 (or 2) to prevent thread thrashing on Render's fractional CPUs
        self.model = WhisperModel(
            model_size, 
            device=device, 
            compute_type=compute_type,
            cpu_threads=2, 
            num_workers=1
        )
        self.beam_size = 1

    def transcribe(self, audio_np):
        segments, _ = self.model.transcribe(
            audio=audio_np, 
            language="en",
            beam_size=self.beam_size,
            vad_filter=True, 
        )
        return " ".join([seg.text for seg in segments])