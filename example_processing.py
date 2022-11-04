import pickle

with open('./DATETIME_ht.pkl', 'rb') as f:
    data = pickle.load(f)
    time, rh, temp = zip(*data)

with open('./DATETIME_pyr.pkl', 'rb') as f:
    data = pickle.load(f)
    print(data)
