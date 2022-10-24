'''
Created on April 1st, 2022
'''

import numpy as np

# Math functions
def gaussian(x,a,x0,sigma):
    '''1D Gaussian Function'''
    return a*np.exp(-(x-x0)**2/(2*sigma**2))

def func(x, w0, x0, xR, offset):
    '''Gaussian Beam Width Function'''
    return w0 * (1+((x-x0)/xR)**2)**0.5 + offset

def fwhm(y):
    '''Full width at half maximum'''
    max_y = max(y)  # Find the maximum y value
    xs = [x for x in range(len(y)) if y[x] > max_y/2.0]
    fwhm_val = max(xs) - min(xs) + 1
    return fwhm_val
