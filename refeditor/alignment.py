"""Optional exact audio fingerprint overlap, when source shares part of reference audio.

Not speech recognition; unrelated music/room tone often produces no reliable match.
"""
import subprocess
import numpy as np


def audio_samples(path,samplerate=4000):
    cmd=['ffmpeg','-v','error','-i',str(path),'-vn','-ac','1','-ar',str(samplerate),
         '-f','f32le','-']
    result=subprocess.run(cmd,capture_output=True)
    if result.returncode!=0:return np.array([],dtype=np.float32)
    return np.frombuffer(result.stdout,dtype='<f4').astype(np.float64)


def audio_offset(reference,source,samplerate=4000,min_correlation=.32):
    """Return {reference_start_offset, score} when same audio waveform is found.
    Offset is reference timestamp matching the source's t=0, allowed to be negative.
    """
    a=audio_samples(reference,samplerate);b=audio_samples(source,samplerate)
    if len(a)<samplerate or len(b)<samplerate:return None
    if np.std(a)<1e-4 or np.std(b)<1e-4:return None
    n=1<<int((len(a)+len(b)-2).bit_length())
    spectrum=np.fft.rfft(a,n)*np.fft.rfft(b[::-1],n)
    correlation=np.fft.irfft(spectrum,n)[:len(a)+len(b)-1]
    loc=int(np.argmax(np.abs(correlation)))
    denom=(np.linalg.norm(a)*np.linalg.norm(b)+1e-12)
    score=float(correlation[loc]/denom)
    if abs(score)<min_correlation:return None
    lag=(loc-(len(b)-1))/samplerate
    return {'reference_offset_s':round(float(lag),5),'score':round(score,4)}
