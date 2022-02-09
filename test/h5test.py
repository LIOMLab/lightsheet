import h5py
import glob

with h5py.File('stack_links.h5',mode='w') as h5fw:
    link_cnt = 0 
    for h5name in glob.glob('C:/Users/Admin/Desktop/lightsheet_data/test-2020-02-02/stack01*.hdf5'):
        link_cnt += 1
        h5fw['link'+str(link_cnt)] = h5py.ExternalLink(h5name,'/') 