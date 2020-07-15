from PIL import Image
import h5py
import numpy as np

for i in range(1,1502):
    print(i)
    if i in range(1,10):
        print('ok')
        nomFichier=(r'C:\Users\liomlight\Desktop\gros_stack_souris\test_souris_stack_plane_0000'+str(i)+'.hdf5')
    if i in range(10,100):
        nomFichier=(r'C:\Users\liomlight\Desktop\gros_stack_souris\test_souris_stack_plane_000'+str(i)+'.hdf5')
    if i in range(100,1000):
        nomFichier=(r'C:\Users\liomlight\Desktop\gros_stack_souris\test_souris_stack_plane_00'+str(i)+'.hdf5')
    if i in range(1000,10000):
        nomFichier=(r'C:\Users\liomlight\Desktop\gros_stack_souris\test_souris_stack_plane_0'+str(i)+'.hdf5')     
    print(nomFichier)
    with h5py.File(nomFichier, "r") as f:
        for j in range(0,len(list(f.keys()))):
            key = list(f.keys())[j]
            group = f[key]
            data=group[()]
            print(key)
            '''Convert to tiff format'''
            tiff = Image.fromarray(data)
            nomFichier = nomFichier.replace('gros_stack_souris', 'gros_stack_souris_tiff')
            tiff_filename = nomFichier.replace('.hdf5', '.tiff')
            tiff.save(tiff_filename)
        print('Plan '+nomFichier+' terminé')