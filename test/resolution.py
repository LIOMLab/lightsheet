import numpy as np 
from matplotlib import pyplot as plt
from scipy import signal,interpolate,optimize
import h5py
import sys

nomFichier=(r'C:\Users\liomlight\Desktop\billes\test_singleImage_plane_00010.hdf5') #test_singleImage_plane_00009#test_singleImage_plane_00002    #test_singleImage_plane_00001

def gaussian(x,a,x0,sigma):
    '''Gaussian Function'''
    return a*np.exp(-(x-x0)**2/(2*sigma**2))

def gaussian2d(z,a,x0,y0,sigmax,sigmay):
    '''2D Gaussian Function'''
    x,y=z
    ret =  a*np.exp(-((x-x0)**2/(2*sigmax**2)+(y-y0)**2/(2*sigmay**2)))
    #print(ret)
    return ret.ravel()

def fwhm(y):
    '''Full width at half maximum'''
    max_y = max(y)  # Find the maximum y value
    xs = [x for x in range(len(y)) if y[x] > max_y/2.0]
    print(xs)
    fwhm_val = max(xs) - min(xs) + 1
    return fwhm_val  

widths = []
colonnes = [1073,1127,1176,1311,1683,1726,1613,1569,887]#[959,930,869,1049,1252,1260,816,966]#[1329,1330,1382,1070,919,1610,1753,1802]#[810,865,920,956,1045,1340,957,1288,1820,1148,800]
rangees = [871,792,803,701,896,961,1058,1477,974]#[1220,1180,1208,1248,1323,1326,1411,1321]#[721,756,712,688,959,741,939,957]#[1284,1385,1300,1169,1060,1305,648,966,910,226,1470]
psf = np.zeros((len(colonnes),10,10))#np.zeros((len(colonnes),100,100))

with h5py.File(nomFichier, "r") as f:
    for i in range(0,len(list(f.keys()))):
        key = list(f.keys())[i]
        group = f[key]
        data=group[()]
        plt.imshow(np.log(np.abs(data)+1),cmap='gray')
        plt.show()
        for j,k,n in zip(colonnes,rangees,range(len(colonnes))):
            print(str(j)+','+str(k))
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
            
            psf[n,:,:] = data[(k-5):(k+5),(j-5):(j+5)]
            plt.imshow(np.log(np.abs(psf[n,:,:])+1),cmap='gray')
            plt.show()
        
    print('Plan '+nomFichier+' terminé')
    
moyenne = np.average(np.array(widths))
print(moyenne)
np.set_printoptions(threshold=sys.maxsize)
moy_psf = np.average(psf, axis=0)
print(moy_psf)

#filename = r'C:\Users\liomlight\Desktop\billes\moy_psf.hdf5'
#f = h5py.File(filename,'a')
#path_root = filename+'data'
#f.create_dataset(path_root, data=moy_psf)
#f.close()

plt.imshow(moy_psf,cmap='gray')
plt.show()

x=np.arange(10)
y=moy_psf[:,5]
y = (y - np.min(y))/(np.max(y) - np.min(y))
#y2=signal.savgol_filter(y, 11, 3)
widt=fwhm(y)
print('fwhm:')
print(widt)
#popt,pcov = optimize.curve_fit(gaussian,x[1230:1330],y[1230:1330])#,bounds=(0, 'inf'), maxfev=10000)
plt.plot(x,y, label='original')
#plt.plot(x,y2, label='savgol_filter')
#plt.plot(x[1230:1330],gaussian(x[1230:1330],*popt), label='gaussian fit')
#plt.plot(x,f2(x), label='interp1d')
#plt.plot(x[1230:1330],y2[1230:1330])
plt.legend()
plt.show()

#x=np.arange(100)
#y=np.arange(100)
#popt,pcov = optimize.curve_fit(gaussian2d,(x,y),moy_psf)#,bounds=(0, 'inf'), maxfev=10000)
#data_fit = gaussian2d((x,y),*popt)
#plt.imshow(data_fit,cmap='gray')
#plt.show()
