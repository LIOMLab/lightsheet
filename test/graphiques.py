import numpy as np 
from matplotlib import pyplot as plt
from scipy import interpolate,stats
data=np.array([[20.000087,   85.93735934],
 [20.333462,   85.97604982],
 [20.666837 ,  85.99915324],
 [21.000212  , 85.91196673],
 [21.333587   ,85.91659716],
 [21.6667715 , 85.93199806],
 [22.0001465 , 85.9677046 ],
 [22.3335215 , 85.95980706],
 [22.6668965 , 85.92865522],
 [23.000081  , 85.90316294],
 [23.333456  , 85.83246273],
 [23.666831  , 85.80708227],
 [24.000206  , 85.85668087],
 [24.3333905 , 85.73706133],
 [24.6667655 , 85.75982333],
 [25.0001405 , 85.73774494],
 [25.3335155 , 85.7582307 ],
 [25.6668905 , 85.76790584],
 [26.000075  , 85.87431938],
 [26.33345   , 85.81303602],
 [26.666825  , 85.75708906],
 [27.0002    , 85.69422312],
 [27.3333845 , 85.6978383 ],
 [27.6667595 , 85.73777857],
 [28.0001345 , 85.66961976],
 [28.3335095 , 85.69753235],
 [28.666694  , 85.5908003 ],
 [29.000069  , 85.71801736],
 [29.333444  , 85.64930509],
 [29.666819  , 85.67984504]])

#immobile:
#data=np.array([[81.599913,   85.99231808],
# [81.09991717, 85.9593663 ],
# [80.59992135 ,85.97639922],
# [80.09992552 ,85.98851094],
# [79.5999297  ,85.96849047],
# [79.09993388 ,85.9997278 ],
# [78.59993805 ,85.96147534],
# [78.09994222 ,85.96021926],
# [77.5999464  ,85.97142323],
# [77.09995058 ,85.94583116],
# [76.59995475 ,85.97830317],
# [76.09995892 ,85.96251211],
# [75.5999631  ,85.98392186],
# [75.09996727 ,85.96719883],
# [74.59997145 ,85.98462457],
# [74.09997563 ,85.98655343],
# [73.5999798  ,85.98198546],
# [73.09998398 ,85.97569257],
# [72.59998815 ,85.98694874],
# [72.09999233 ,85.96341712]]
#)

slope, intercept, r_value, p_value, std_err = stats.linregress(data[:,0],data[:,1])
print('slope:'+str(slope))
print('intercept:'+str(intercept))
print('r_value:'+str(r_value))
print('p_value:'+str(p_value))
print('std_err:'+str(std_err))

#z=np.array([[1,2,3,4,5],[6,7,8,9,10]])
#print(z)
#
#plt.figure(1)
#plt.title('Camera Focus Interpolation') 
#plt.xlabel('Sample Horizontal Position') 
#plt.ylabel('Camera Position')
##ax = plt.gca()
##ax.set_xticks(np.arange(2, 12, step=2))
##ax.set_yticks(np.arange(2, 12, step=2))
#plt.imshow(z, cmap='hot',extent = [2 , 6, 5 , 10])
##plt.hist2d(z[0], z[1])
#
##plt.xticks(None)
##plt.yticks(None)
##plt.plot(z[0], z[1], 'o')
#plt.show()

#x = np.arange(1,11) 
#y = 2 * x + 5 
#
#z = np.array([[ 97696.9725, 97483.517 ], [ 97796.7945, 97432.463 ], 
#              [ 97996.629, 97381.5995], [ 98296.476, 97330.736 ], 
#              [ 98696.3355, 97279.8725], [ 99196.2075, 97229.009 ], 
#              [ 99796.092, 97178.1455], [100495.989, 97127.282 ], 
#              [101295.8985, 97076.4185], [101295.8985, 97025.555 ]])
#
#plt.figure(1)
#plt.title("Camera Focus Function") 
#plt.xlabel("Sample Horizontal Position (um)") 
#plt.ylabel("Camera Position (um)") 
#plt.plot(z[:,0],z[:,1],'o', color='black') 
#plt.show()
#
#x = np.array(z[:,0])
#y = np.array(z[:,1])
#
#x = np.array([ 0, 1, 2, 3, 4, 5])
#y = np.array([12,14,22,39,58,77])
#
#xnew=np.linspace(0, 5, 200)
#tck = interpolate.splrep(x,y)
#ynew = interpolate.splev(xnew, tck)
#
#plt.figure(2)
#plt.title("Camera Focus Interpolation") 
#plt.xlabel("Sample Horizontal Position (um)") 
#plt.ylabel("Camera Position (um)") 
#plt.plot(x,y, 'o', label="original")
#plt.plot(xnew,ynew, label="interpolation")
#plt.legend()
#plt.show()