from enum import Enum


class AudioFormat(str, Enum):
    MP3 = "mp3"
    OGG = "ogg"
    WAV = "wav"
    FLAC = "flac"
    AAC = "aac"
    M4A = "m4a"


SUPPORTED_INPUTS = {fmt.value for fmt in AudioFormat}
SUPPORTED_OUTPUTS = {fmt.value for fmt in AudioFormat}