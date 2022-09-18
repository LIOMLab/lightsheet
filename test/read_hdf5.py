import numpy as np
from matplotlib import pyplot as plt
import h5py

'''HDF5 files'''

inFilename = (r'C:\Users\Admin\Documents\GitHub\lightsheet\test\test_split_01.hdf5')

with h5py.File(inFilename, "r") as inFile:
    print('Lecture de ' + inFilename)
    for key in inFile.keys():
        print(key)

        group = inFile[key]
        data = group[()]
        
        plt.imshow(data, cmap='gray')
        plt.show()

    print('Lecture terminée')
    
    #print("Keys: %s" % f.keys())
    #a_group_key = list(f.keys())[0]
    #group = f[a_group_key]
    #print('group:')
    #print(group)
    #data=group[()] #extraire les données
    #print(data)
    
    #plt.imshow(data)
    #plt.show()
    
    #a_data_key = list(group.keys())[0]
    #data=group[a_data_key]
    #print(data)

#fig,a =  plt.subplots(2,2)
#a[0][0].imshow(data)
#plt.show()
