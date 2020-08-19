import numpy as np 
from matplotlib import pyplot as plt
from scipy import signal,interpolate,optimize
import h5py

#nomFichier=(r'C:\Users\liomlight\Desktop\billes_stack\test_stack_plane_00007.hdf5') #test_stack_plane_00004#test_stack_plane_00003#00001
#nomFichier=(r'C:\Users\liomlight\Desktop\left_laser\test_stack_plane_00001.hdf5') #test_stack_plane_00001
#nomFichier=(r'C:\Users\liomlight\Desktop\right_laser\test_stack_plane_00004.hdf5') #test_stack_plane_00003#test_stack_plane_00002 #test_stack_plane_00001
#nomFichier=(r'C:\Users\liomlight\Desktop\all_lasers\test_stack_plane_00001.hdf5')
#nomFichier=(r'C:\Users\liomlight\Desktop\left_nouvelle_lentille\test_stack_plane_00003.hdf5')
nomFichier=(r'C:\Users\liomlight\Desktop\test_laser_brisé\test_stack_plane_00001.hdf5')

def gaussian(x,a,x0,sigma):
    '''Gaussian Function'''
    return a*np.exp(-(x-x0)**2/(2*sigma**2))

def fwhm(y):
    '''Full width at half maximum'''
    max_y = max(y)  # Find the maximum y value
    xs = [x for x in range(len(y)) if y[x] > max_y/2.0]
    print(xs)
    fwhm_val = max(xs) - min(xs) + 1
    return fwhm_val  

widths = []
colonne = 1704 #1357 #1283 #1434#1425 #1216#1177## 1434###1100     #1216      #1312#1906#1300#1148
rangee =  1962 #884 #1165 ##779 #1003 #1314#831#848 #677#922## 831#937 ###735 #1181   #925#1105#1338
y=[]

with h5py.File(nomFichier, "r") as f:
    axial = np.zeros(len(list(f.keys())))
    x=np.arange(len(list(f.keys())))
    img = np.zeros((2160,len(list(f.keys()))))
    for i in range(len(list(f.keys()))):
        key = list(f.keys())[i]
        group = f[key]
        data=group[()]
        #if i == 0 or i == 50 or i == 100:
        #    plt.imshow(np.log(np.abs(data)+1),cmap='gray')
        #    plt.show()
        img[:,i]=data[:,colonne]
        y.append(data[rangee,colonne])
    plt.imshow(img,cmap='gray')
    plt.show()
    y=np.array(y)
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
        
    print('Plan '+nomFichier+' terminé')
    
moyenne = np.average(np.array(widths))
print(moyenne)
