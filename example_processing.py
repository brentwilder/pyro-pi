import pickle
import glob
import pandas as pd
import numpy as np

# Saves the many, many pkl files created during Mobile-Pi collection and saves them to two clean csvs..

data_list = []
for filepath in glob.iglob('./MOBILE_PI/*_ht.pkl'):
    with open(filepath, 'rb') as f:
        data = pickle.load(f)
        time, rh, temp = zip(*data)
        time = time[0]
        rh = np.mean(rh)
        temp = np.mean(temp)
        data_list.append([time,rh,temp])
df = pd.DataFrame(data=data_list, columns=['Time', 'RH', 'Tair'])
print(df)
df.to_csv('./2022_1207_ht.csv')

data_list = []
for filepath in glob.iglob('./MOBILE_PI/*_pyr.pkl'):
    with open(filepath, 'rb') as f:
        data = pickle.load(f)
        time = data[0][0]
        p0_out = np.mean(data[4])
        p1_out = np.mean(data[8])
        data_list.append([time,p0_out,p1_out])
df = pd.DataFrame(data=data_list, columns=['Time', 'P1', 'P2'])
print(df)
df.to_csv('./2022_1207_pyr.csv')
