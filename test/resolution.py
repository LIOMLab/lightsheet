import numpy as np 
from matplotlib import pyplot as plt
from scipy import signal,interpolate,optimize
import h5py

nomFichier=(r'C:\Users\liomlight\Desktop\billes\test_singleImage_plane_00001.hdf5')

def gaussian(x,a,x0,sigma):
    '''Gaussian Function'''
    return a*np.exp(-(x-x0)**2/(2*sigma**2))

def gaussian2d(x,y,a,x0,y0,sigmax,sigmay):
    '''2D Gaussian Function'''
    return a*np.exp(-((x-x0)**2/(2*sigmax**2)+(y-y0)**2/(2*sigmay**2)))

def fwhm(y):
    '''Full width at half maximum'''
    max_y = max(y)  # Find the maximum y value
    xs = [x for x in range(len(y)) if y[x] > max_y/2.0]
    print(xs)
    fwhm_val = max(xs) - min(xs) + 1
    return fwhm_val  

widths = []
colonnes = [810,865,920,956,1045,1340,957,1288,1820,1148,800]
rangees =[1284,1385,1300,1169,1060,1305,648,966,910,226,1470]
psf = np.zeros((len(colonnes),100,100))

with h5py.File(nomFichier, "r") as f:
    for i in range(0,len(list(f.keys()))):
        key = list(f.keys())[i]
        group = f[key]
        data=group[()]
        plt.imshow(np.log(np.abs(data)+1),cmap='gray')
        plt.show()
        for j,k,n in zip(colonnes,rangees,range(len(colonnes))):
            print(j)
            x=np.arange(2160)
            y=data[:,j]
            y = (y - np.min(y))/(np.max(y) - np.min(y))
            y2=signal.savgol_filter(y, 31, 3)
            f2 = interpolate.interp1d(x, y, kind='cubic')
            widt=fwhm(y2)
            print('fwhm:')
            print(widt)
            widths.append(widt)
            #popt,pcov = optimize.curve_fit(gaussian,x[1230:1330],y[1230:1330])#,bounds=(0, 'inf'), maxfev=10000)
            plt.plot(x,y, label='original')
            plt.plot(x,y2, label='savgol_filter')
            #plt.plot(x[1230:1330],gaussian(x[1230:1330],*popt), label='gaussian fit')
            #plt.plot(x,f2(x), label='interp1d')
            #plt.plot(x[1230:1330],y2[1230:1330])
            plt.legend()
            plt.show()
            
            psf[n,:,:] = data[(k-50):(k+50),(j-50):(j+50)]
        
    print('Plan '+nomFichier+' terminé')
    
moyenne = np.average(np.array(widths))
print(moyenne)

moy_psf = np.average(psf, axis=0)
plt.imshow(moy_psf,cmap='gray')
plt.show()

#popt,pcov = optimize.curve_fit(gaussian2d,moy_psf,y[1230:1330])#,bounds=(0, 'inf'), maxfev=10000)
