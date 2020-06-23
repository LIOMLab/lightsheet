import numpy as np 
from matplotlib import pyplot as plt
import h5py

'''HDF5 files'''

datas=[]
for i in range(1,30):
    if i in range(1,10):
        nomFichier=(r'C:\Users\liomlight\Desktop\test_etl\test_singleImage_plane_0000'+str(i)+'.hdf5')
    elif i in range(11,100):
        nomFichier=(r'C:\Users\liomlight\Desktop\test\test_singleImage_plane_000'+str(i)+'.hdf5')
    elif i in range(101,1000):
        nomFichier=(r'C:\Users\liomlight\Desktop\test7\test10003_stack_plane_00'+str(i)+'.hdf5')
    elif i in range(1001,10000):
        nomFichier=(r'C:\Users\liomlight\Desktop\test7\test10003_stack_plane_0'+str(i)+'.hdf5')     
    print(nomFichier)
    with h5py.File(nomFichier, "r") as f:
        for i in range(0,len(list(f.keys()))):
            key = list(f.keys())[i]
            group = f[key]
            data=group[()]
            if np.average(data)<=100:
                print('-Erreur')
            else:
                print('ok')
        print('Plan '+nomFichier+' terminé')
        
        #print("Keys: %s" % f.keys())
        #a_group_key = list(f.keys())[0]
        #group = f[a_group_key]
        #print('group:')
        #print(group)
        #data=group[()] #extraire les données
        #print(data)
        
        plt.imshow(data)
        plt.show()
        
        #a_data_key = list(group.keys())[0]
        #data=group[a_data_key]
        #print(data)

    #fig,a =  plt.subplots(2,2)
    #a[0][0].imshow(data)
    #plt.show()
