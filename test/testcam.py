import pco
from pco import sdk
import matplotlib.pyplot as plt

with pco.Camera() as cam:

    shutter_mode = cam.sdk.get_camera_setup()
    print('shutter_mode:')
    print(shutter_mode)

    cam.record(number_of_images=5,mode='ring buffer')
    images, metadatas = cam.images()

    for image in images:
        plt.imshow(image, cmap='gray')
        plt.show()
    
    cam.stop() #automatically called if record mode is 'sequence' or 'sequence non blocking'
    cam.close() #automatically called with statement 'with pco.Camera() as cam:'