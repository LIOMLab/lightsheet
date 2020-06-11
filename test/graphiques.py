import numpy as np 
from matplotlib import pyplot as plt
from scipy import interpolate

x = np.arange(1,11) 
y = 2 * x + 5 

z = np.array([[ 97696.9725, 97483.517 ], [ 97796.7945, 97432.463 ], 
              [ 97996.629, 97381.5995], [ 98296.476, 97330.736 ], 
              [ 98696.3355, 97279.8725], [ 99196.2075, 97229.009 ], 
              [ 99796.092, 97178.1455], [100495.989, 97127.282 ], 
              [101295.8985, 97076.4185], [101295.8985, 97025.555 ]])

plt.figure(1)
plt.title("Camera Focus Function") 
plt.xlabel("Sample Horizontal Position (um)") 
plt.ylabel("Camera Position (um)") 
plt.plot(z[:,0],z[:,1],'o', color='black') 
plt.show()

x = np.array(z[:,0])
y = np.array(z[:,1])

x = np.array([ 0, 1, 2, 3, 4, 5])
y = np.array([12,14,22,39,58,77])

xnew=np.linspace(0, 5, 200)
tck = interpolate.splrep(x,y)
ynew = interpolate.splev(xnew, tck)

plt.figure(2)
plt.title("Camera Focus Interpolation") 
plt.xlabel("Sample Horizontal Position (um)") 
plt.ylabel("Camera Position (um)") 
plt.plot(x,y, 'o', label="original")
plt.plot(xnew,ynew, label="interpolation")
plt.legend()
plt.show()