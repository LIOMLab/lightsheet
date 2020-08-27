from PIL import Image
import numpy as np
from matplotlib import pyplot as plt
from scipy import signal

def fwhm(y):
    '''Full width at half maximum'''
    max_y = max(y)  # Find the maximum y value
    print(max_y)
    xs = [x for x in range(len(y)) if y[x] > max_y/2.0]
    #print(xs)
    fwhm_val = max(xs) - min(xs) + 1
    return fwhm_val  

im = Image.open(r'C:\Users\liomlight\Desktop\Resolution_axiale\resolution_axiale2.tif')
#im = Image.open(r'C:\Users\liomlight\Desktop\Resolution_axiale\jpg-resolution_axiale2.jpg')
#im.show()
imarray = np.array(im)

print(imarray.shape)
#y = np.average(imarray[468,:],axis=1) #verticalement
y = np.average(imarray[:,698],axis=1) #horizontalement
print(y)
print(len(y))
x=np.arange(len(y))
print(len(x))
#y = (y - np.min(y))/(np.max(y) - np.min(y))
y2 = signal.savgol_filter(y, 11, 3)
original_width=fwhm(y)
clean_width=fwhm(y2)
print('original fwhm:'+str(original_width))
print('savgol fwhm:'+str(clean_width))
plt.plot(x,y, label='original')
#plt.plot(x,y2, label='savgol_filter')
plt.legend()
plt.show()