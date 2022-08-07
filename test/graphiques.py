import numpy as np 
from matplotlib import pyplot as plt
from scipy import interpolate,stats
data=np.array([ [20.000087  , 85.93735934],
                [20.333462  , 85.97604982],
                [20.666837  , 85.99915324],
                [21.000212  , 85.91196673],
                [21.333587  , 85.91659716],
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
                [29.666819  , 85.67984504] ])

slope, intercept, r_value, p_value, std_err = stats.linregress(data[:,0],data[:,1])
print('slope:' + str(slope))
print('intercept:' + str(intercept))
print('r_value:' + str(r_value))
print('p_value:' + str(p_value))
print('std_err:' + str(std_err))







