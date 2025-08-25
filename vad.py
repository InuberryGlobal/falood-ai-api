import webrtcvad

class VAD:
    def __init__(self, sample_rate=16000, mode=3):
        self.vad = webrtcvad.Vad(mode)
        self.sample_rate = sample_rate
        self.frame_ms = 30
        self.frame_bytes = int(sample_rate * self.frame_ms / 1000) * 2  

    def is_speech(self, pcm_bytes):
        return self.vad.is_speech(pcm_bytes, self.sample_rate)

    def frame_size(self):
        return self.frame_bytes
