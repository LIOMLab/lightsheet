import h5py
import glob

with h5py.File('merged.h5',mode='w') as h5fw:
    dset_suffix = 0
    for h5name in glob.glob('*.hdf5'):
        h5fr = h5py.File(h5name,'r') 
        dset1 = list(h5fr.keys())[0]
        arr_data = h5fr[dset1][:]
        newdset = 'frame_' + str(dset_suffix)
        h5fw.create_dataset(newdset,data=arr_data) 
        dset_suffix += 1
        