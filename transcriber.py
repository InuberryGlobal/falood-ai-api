from faster_whisper import WhisperModel

class Transcriber:
    def __init__(self, model_size="small", device="cpu", compute_type="int8"):
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        self.beam_size = 1

    def transcribe(self, audio_np):
        segments, _ = self.model.transcribe(
            audio=audio_np, 
            language="en",
            beam_size=self.beam_size,
            vad_filter=True, 
        )
        return " ".join([seg.text for seg in segments])