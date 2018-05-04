#!./streamlit_run

from streamlit import io, cache
import pandas as pd
import numpy as np

io.title('Uber Example')
DATE_TIME = 'date/time'

@cache
def load_data(nrows):
    data = pd.read_csv('uber-raw-data-sep14.csv', nrows=nrows)
    data.rename(str.lower, axis='columns', inplace=True)
    data[DATE_TIME] = pd.to_datetime(data[DATE_TIME])
    return data

nrows = 100000
data = load_data(nrows)

io.subheader('Usage By Day')
hist = np.histogram(data[DATE_TIME].dt.hour, bins=24, range=(0,24))
counts = pd.DataFrame(hist[0]).set_index(hist[1][:-1])
io.bar_chart(counts)

hour = 10
io.subheader(f'Usage at {hour}h')
io.map(data[data[DATE_TIME].dt.hour == hour])

io.subheader('Raw Data')
io.write(data)

# io.header('Raw Data')

# io.write(data)
#
# # data['hour'] = data['Date/Time'].dt.hour
# # data['day'] = data['Date/Time'].dt.dayofweek
# # io.write('About to write data')
# # io.write('Wrote raw data')
#
# io.write('Here is a test!')

#
# # io.binned_scatter_chart(data[['hour', 'day']].set_index('hour'))
# # # io.write(data[['hour', 'day']].set_index('hour'))
# # io.header('Pick Up Times')
# # freq, hours = np.histogram(data[DATE_TIME].dt.hour, bins=24, range=(0,24))
# # io.write(freq)
# # io.bar_chart(freq)
# #
# # io.geo_chart(data[['Lat', 'Lon']].set_index('Lat'))
# #
# #
# #
# #
# # # io.write(hours)
# #
# #
# # # freq, lats = np.histogram(data['Lat'], bins=20, range=(40.6, 40.8))
# # # hist_data = pd.DataFrame({'freq': freq, 'lats': lats[:-1]}).set_index('lats')
# # # io.bar_chart(hist_data, height=300)
# # # # io.bar_chart()
# # # io.help(np.histogram)
