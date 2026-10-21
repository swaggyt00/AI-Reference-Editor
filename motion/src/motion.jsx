import React from 'react';
import {AbsoluteFill, OffthreadVideo, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';

const limits={extrapolateLeft:'clamp',extrapolateRight:'clamp'};
const smooth=t=>1-Math.pow(1-t,3);
const placement=(item)=>({position:'absolute',left:(item.x ?? .5)*100+'%',top:(item.y ?? .5)*100+'%',zIndex:item.z??10});
const animated=(item,frame,fps)=>{
  const a=Math.round(item.start*fps), b=Math.round(item.end*fps), local=frame-a;
  if(local<0||local>=b-a) return null;
  const fi=Math.max(1,Math.round(fps*.25)),fo=Math.max(1,Math.round(fps*.2));
  const opacity=interpolate(local,[0,fi,Math.max(fi,b-a-fo),b-a],[0,1,1,0],limits);
  const entry=smooth(Math.min(1,local/fi));
  const dx=item.animation==='slide'?(1-entry)*140:0;
  const dy=item.animation==='rise'?(1-entry)*70:0;
  const scale=item.animation==='pop'?.72+.28*entry:1;
  return {opacity,transform:'translate(-50%,-50%) translate('+dx+'px,'+dy+'px) scale('+scale+')'};
};

const TextGraphic=({item})=>{
  const frame=useCurrentFrame(),{fps}=useVideoConfig(),anim=animated(item,frame,fps);
  if(!anim)return null;
  const card=item.kind==='card',badge=item.kind==='badge',caption=item.kind==='caption';
  return <div style={{...placement(item),...anim,
      width:card?'84%':'90%',maxWidth:980,textAlign:item.align??'center',
      whiteSpace:'pre-wrap',overflowWrap:'anywhere',
      fontFamily:'Arial,Helvetica,sans-serif',fontWeight:item.weight??800,
      fontSize:item.size??(badge?36:66),lineHeight:1.15,
      color:item.color??(card?'#151b29':'#fff'),
      background:item.background??(card?'rgba(248,249,255,.95)':(badge||caption)?'rgba(10,17,30,.82)':'transparent'),
      padding:card?'30px 34px':badge?'12px 22px':'12px 18px',
      borderRadius:badge?999:card?26:12,
      textShadow:item.kind==='title'?'0 5px 18px #000a':'none',
      boxShadow:card?'0 18px 45px #0006':'none',
      border:badge?'2px solid #ffffff77':'none'}}>{item.text}</div>;
};
const ImageGraphic=({item})=>{
  const frame=useCurrentFrame(),{fps}=useVideoConfig(),anim=animated(item,frame,fps);
  if(!anim)return null;
  return <div style={{...placement(item),...anim,width:(item.width??.65)*100+'%'}}>
    <Img src={staticFile('assets/'+item.asset)} style={{width:'100%',height:'auto',
      borderRadius:item.radius??16,filter:'drop-shadow(0 12px 20px #0006)'}}/>
  </div>;
};
const VideoGraphic=({item})=>{
  const frame=useCurrentFrame(),{fps}=useVideoConfig(),anim=animated(item,frame,fps);
  if(!anim)return null;
  const begin=Math.round(item.start*fps);
  const duration=Math.max(1,Math.round((item.end-item.start)*fps));
  // Sequence resets local time, so the insert begins at the requested media moment.
  const localFrame=frame-begin;
  return <div style={{...placement(item),...anim,width:(item.width??.8)*100+'%',
    height:(item.height??.32)*100+'%',borderRadius:18,overflow:'hidden',
    border:'3px solid #ffffffaa',boxShadow:'0 18px 35px #0009'}}>
    <OffthreadVideo src={staticFile('assets/'+item.asset)} volume={0}
      startFrom={Math.round((item.source_start??0)*fps)}
      endAt={Math.round((item.source_start??0)*fps)+duration}
      style={{width:'100%',height:'100%',objectFit:'cover'}}/>
  </div>;
};
const RouteGraphic=({item})=>{
  const frame=useCurrentFrame(),{fps}=useVideoConfig(),anim=animated(item,frame,fps);
  if(!anim)return null;
  const a=Math.round(item.start*fps),len=Math.max(1,Math.round((item.end-item.start)*fps));
  const u=Math.max(0,Math.min(1,(frame-a)/(len*.8)));
  const pts=item.points ?? [[.12,.8],[.32,.56],[.61,.58],[.86,.23]];
  const path=pts.map(([x,y],i)=>(i?'L':'M')+' '+Math.round(800*x)+' '+Math.round(430*y)).join(' ');
  return <div style={{...placement(item),...anim,width:'84%',height:530,borderRadius:22,
    background:'rgba(11,28,42,.94)',border:'1px solid #ffffff44',overflow:'hidden',
    boxShadow:'0 22px 54px #0008'}}>
    <div style={{fontSize:30,fontWeight:800,color:'#fff',padding:'16px 30px'}}>{item.text||'Маршрут'}</div>
    <svg width="100%" height="430" viewBox="0 0 800 430">
      <defs><pattern id="grid" width="36" height="36" patternUnits="userSpaceOnUse">
      <path d="M 36 0 L 0 0 0 36" stroke="#426075" strokeWidth="1" opacity=".45" fill="none"/>
      </pattern></defs>
      <rect width="800" height="430" fill="url(#grid)"/>
      <path d={path} fill="none" stroke="#50b8ff" strokeWidth="10" strokeLinecap="round"
        strokeDasharray="2200" strokeDashoffset={2200*(1-u)}/>
      {pts.map(([x,y],i)=><circle key={i} cx={800*x} cy={430*y}
        r="12" stroke="#40aeff" strokeWidth="5" fill="#fff"/>)}
    </svg>
  </div>;
};
export const MotionComposition=({baseFile,layers=[]})=><AbsoluteFill style={{background:'#0b0e13',overflow:'hidden'}}>
  {baseFile?<OffthreadVideo src={staticFile('assets/'+baseFile)}
    style={{width:'100%',height:'100%',objectFit:'cover'}} volume={0}/>:null}
  {layers.map((item,i)=>item.kind==='image'?<ImageGraphic item={item} key={i}/>:
     item.kind==='video'?<VideoGraphic item={item} key={i}/>:
     item.kind==='route'?<RouteGraphic item={item} key={i}/>:
     <TextGraphic item={item} key={i}/>)}
</AbsoluteFill>;
