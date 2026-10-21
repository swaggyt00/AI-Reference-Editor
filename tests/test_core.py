import unittest
import numpy as np
import cv2
from refeditor.analyzer import black_edge_bounds
from refeditor.effects import apply,source_curve
from refeditor.renderer import effect_mask,cover

class CoreTests(unittest.TestCase):
    def test_black_edge_measurement(self):
        f=np.full((120,240,3),150,dtype=np.uint8)
        f[:,:60]=0;f[:,180:]=0
        x=black_edge_bounds(f)
        self.assertAlmostEqual(x[0],.25,delta=.015)
        self.assertAlmostEqual(x[1],.75,delta=.015)
    def test_preserve_unmasked_frame(self):
        f=np.full((120,240,3),150,dtype=np.uint8)
        self.assertEqual(black_edge_bounds(f),[0.0,1.0])
    def test_mask_applied_at_measured_boundary(self):
        f=np.full((120,240,3),200,dtype=np.uint8)
        r=effect_mask(f,[.25,.75])
        self.assertEqual(int(r[:,0].max()),0)
        self.assertEqual(int(r[:,-1].max()),0)
        self.assertEqual(int(r[:,120].min()),200)
    def test_zoom_does_not_change_dimensions(self):
        f=np.full((120,240,3),150,dtype=np.uint8)
        zoom={'type':'zoom','start':0,'end':1,'from':1.0,'to':1.5}
        r=apply(f,.5,[zoom])
        self.assertEqual(r.shape,f.shape)
    def test_flash_white_and_recedes(self):
        f=np.full((120,240,3),50,dtype=np.uint8)
        fx={'type':'flash','start':0,'end':1,'strength':.8}
        self.assertGreater(float(apply(f,.1,[fx]).mean()),float(apply(f,.8,[fx]).mean()))
    def test_ramp_is_monotonic_and_normalized(self):
        keys=[{'at':.25,'speed':.5},{'at':.75,'speed':1.8}]
        values=[source_curve(i/20,keys) for i in range(21)]
        self.assertAlmostEqual(values[0],0,places=5)
        self.assertAlmostEqual(values[-1],1,places=5)
        self.assertTrue(all(a<=b for a,b in zip(values,values[1:])))
    def test_cover(self):
        f=np.zeros((720,1920,3),dtype=np.uint8)
        self.assertEqual(cover(f,960,720).shape,(720,960,3))

if __name__=='__main__':unittest.main()
