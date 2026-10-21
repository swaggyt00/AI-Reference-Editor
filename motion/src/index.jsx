import React from 'react';
import {Composition,registerRoot} from 'remotion';
import {MotionComposition} from './motion.jsx';
const Root=()=> <Composition id="Motion" component={MotionComposition}
  durationInFrames={150} fps={30} width={1080} height={1920}
  defaultProps={{baseFile:'base.mp4',layers:[]}}/>;
registerRoot(Root);
