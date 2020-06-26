#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Wed Jun 24 10:59:31 2020

@author: pjmac
"""

import h5py
import numpy as np
import matplotlib.pyplot as plt 
from scipy.signal import savgol_filter
from scipy.optimize import curve_fit
from scipy.ndimage import gaussian_filter
from os import listdir
from os.path import isfile, join

mypath=r'C:\Users\liomlight\Desktop\test\calib-sample-pos-2'
#mypath='/Users/pjmac/Downloads/calib-sample-pos-2'
#mypath='/Users/pjmac/Downloads/calib-sample-pos-3'


#get name of files:
h5filenames = [f for f in listdir(mypath) if isfile(join(mypath, f))]
h5filenames.sort()
numFrames=len(h5filenames)
#load first frame to get dimensions of frame:
f = h5py.File(join(mypath,h5filenames[0]),'r')
dset=np.array(f['camera_position001'])
numcol, numrow = dset.shape
metricvar=np.zeros((numFrames))

#load all frames
for iteration, h in enumerate(h5filenames):
    f = h5py.File(join(mypath,h),'r')
    frame=np.array(f['camera_position001'])
    frame = gaussian_filter(frame, sigma=3)

    flatframe=frame.flatten()
    metricvar[iteration]=np.var(flatframe)

    flatframe[::-1].sort()
    numElements=flatframe.shape[0]
    plt.imshow(frame,aspect='auto')
    plt.show()


def gauss(x,a,x0,sigma):
    return a*np.exp(-(x-x0)**2/(2*sigma**2))

metricvar=(metricvar-np.min(metricvar))/(np.max(metricvar)-np.min(metricvar))
print('metricvar:'+str(metricvar))
metricvar = savgol_filter(metricvar, 11, 3) # window size 51, polynomial order 3
print('metricvar:'+str(metricvar))

n=len(metricvar)
x=np.arange(n)#range(n)

n = len(metricvar)              
mean = sum(x*metricvar)/n           
sigma = sum(metricvar*(x-mean)**2)/n
poscenter=np.argmax(metricvar)

popt,pcov = curve_fit(gauss,x,metricvar,p0=[1,mean,sigma],bounds=(0, 'inf'))

amp,center,variance=popt
print('center:'+str(center))
print('amp:'+str(amp))
print('variance:'+str(variance))

plt.plot(metricvar)
plt.plot(x,gauss(x,*popt),'ro:',label='fit')

plt.show()

    