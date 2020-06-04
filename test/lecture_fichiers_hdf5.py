import numpy as np 
from matplotlib import pyplot as plt
import h5py

'''HDF5 files'''

datas=[]
for i in range(1,2001):
    if i in range(1,10):
        nomFichier=(r'C:\Users\liomlight\Desktop\test5\test2001_stack_plane_0000'+str(i)+'.hdf5')
    elif i in range(11,100):
        nomFichier=(r'C:\Users\liomlight\Desktop\test5\test2001_stack_plane_000'+str(i)+'.hdf5')
    elif i in range(101,1000):
        nomFichier=(r'C:\Users\liomlight\Desktop\test5\test2001_stack_plane_00'+str(i)+'.hdf5')
    elif i in range(1001,10000):
        nomFichier=(r'C:\Users\liomlight\Desktop\test5\test2001_stack_plane_0'+str(i)+'.hdf5')     
    print(nomFichier)
    with h5py.File(nomFichier, "r") as f:
        # List all groups
        print("Keys: %s" % f.keys())
        a_group_key = list(f.keys())[0]
    
        # Get the data
        group = f[a_group_key]
        print('group:')
        print(group)
        data=group[()] #extraire les données
        print(data)
        #a_data_key = list(group.keys())[0]
        #data=group[a_data_key]
        #print(data)
        
        plt.imshow(data)
        plt.show()

    #fig,a =  plt.subplots(2,2)
    #a[0][0].imshow(data)
    #plt.show()

'''Camera Focus '''
x = np.arange(1,11) 
y = 2 * x + 5 

z = np.array([[ 97696.9725, 97483.517 ], [ 97796.7945, 97432.463 ], 
              [ 97996.629, 97381.5995], [ 98296.476, 97330.736 ], 
              [ 98696.3355, 97279.8725], [ 99196.2075, 97229.009 ], 
              [ 99796.092, 97178.1455], [100495.989, 97127.282 ], 
              [101295.8985, 97076.4185], [101295.8985, 97025.555 ]])

plt.figure(0)
plt.title("Camera Focus Function") 
plt.xlabel("Sample Horizontal Position (um)") 
plt.ylabel("Camera Position (um)") 
plt.plot(z[:,0],z[:,1]) 
plt.show()