"""Deterministic reference-preserving effects. All times are seconds."""
import cv2
import numpy as np


def active(effect,t):
    return float(effect.get('start',0))<=t<float(effect.get('end',float('inf')))


def progress(effect,t):
    st=float(effect.get('start',0));end=float(effect.get('end',st+1))
    u=float(np.clip((t-st)/max(1e-6,end-st),0,1))
    return u*u*(3-2*u) if effect.get('easing','smooth')=='smooth' else u


def apply(frame,t,effects,frame_number=0):
    h,w=frame.shape[:2]
    for e in effects:
        if not active(e,t):continue
        typ=e.get('type');u=progress(e,t)
        if typ=='zoom':
            s=float(e.get('from',1))+(float(e.get('to',1))-float(e.get('from',1)))*u
            if s<1:s=1
            cx=float(e.get('center_x',.5))*w;cy=float(e.get('center_y',.5))*h
            m=np.array([[s,0,(1-s)*cx],[0,s,(1-s)*cy]],dtype=np.float32)
            frame=cv2.warpAffine(frame,m,(w,h),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT)
        elif typ=='blur':
            sigma=max(0,float(e.get('from',0))+(float(e.get('to',0))-float(e.get('from',0)))*u)
            if sigma>.1:frame=cv2.GaussianBlur(frame,(0,0),sigmaX=sigma,sigmaY=sigma)
        elif typ=='flash':
            strength=float(e.get('strength',.5)) * (1-u)
            frame=np.clip(frame.astype(np.float32)*(1-strength)+255*strength,0,255).astype(np.uint8)
        elif typ=='shake':
            # Smooth deterministic shake (not independent random jitter each frame).
            amp=float(e.get('amplitude_px',3))*np.sin(np.pi*u)
            hz=float(e.get('frequency_hz',10))
            dx=amp*np.sin(2*np.pi*hz*t);dy=amp*.7*np.sin(2*np.pi*hz*.79*t)
            m=np.float32([[1,0,dx],[0,1,dy]])
            frame=cv2.warpAffine(frame,m,(w,h),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT)
        elif typ=='color':
            contrast=float(e.get('contrast',1));brightness=float(e.get('brightness',0))
            saturation=float(e.get('saturation',1))
            frame=cv2.convertScaleAbs(frame,alpha=contrast,beta=brightness)
            if saturation !=1:
                hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV).astype(np.float32)
                hsv[:,:,1]=np.clip(hsv[:,:,1]*saturation,0,255)
                frame=cv2.cvtColor(hsv.astype(np.uint8),cv2.COLOR_HSV2BGR)
        else:
            raise ValueError(f'Unknown effect: {typ}')
    return frame


def source_curve(u,keyframes):
    """Integrate speed ramp over normalized target time, then normalize result to source interval.
    No native movement is fabricated by this transform.
    """
    if not keyframes:return u
    keys=sorted([(0.,1.)]+[(float(k['at']),float(k['speed'])) for k in keyframes]+[(1.,1.)])
    xp=np.array([x[0] for x in keys]);sp=np.array([max(.05,x[1]) for x in keys])
    grid=np.linspace(0,1,513)
    val=np.interp(grid,xp,sp)
    integral=np.r_[0,np.cumsum((val[1:]+val[:-1])*.5/512)]
    return float(np.interp(u,grid,integral)/integral[-1])
