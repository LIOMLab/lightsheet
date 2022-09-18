import numpy as np
import h5py
import tifffile

inFilename = (r'C:\Users\Admin\Documents\GitHub\lightsheet\test\test_stitched_01.hdf5')
outFilename = (r'C:\Users\Admin\Documents\GitHub\lightsheet\test\test_stitched_01.tiff')

with h5py.File(inFilename, "r") as inFile:
    with tifffile.TiffWriter(outFilename, bigtiff= True) as outFile:

        print('Input: ' + inFilename)
        print('Output: ' + outFilename)

        for key in inFile.keys():
            print(key)
            group = inFile[key]

            data = group[()]
            metadata = dict(group.attrs.items())

            outFile.write(data, contiguous=True, metadata = metadata )

print('Done')

with tifffile.TiffReader(outFilename) as readbackFile:
    print(readbackFile.tiff.version)
    print(len(readbackFile.pages))
    print(readbackFile.pages[0].imagej_description)
    metadata = readbackFile.imagej_metadata
    print(metadata)



