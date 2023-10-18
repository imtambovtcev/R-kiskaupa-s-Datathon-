import iceweather as iw
import requests
import json
import numpy as np
import cv2
from scipy.spatial import cKDTree

class WeatherSensor:

    def __init__(self, LAT, LONG):
        self.latitude = LAT
        self.longitude = LONG

    def get_sensor_data(self):
        Sdata = iw.observation_for_closest(self.latitude, self.longitude)
        SdataParse = Sdata[0]['results'][0]
        self.station_name = SdataParse.get('name')
        self.windspeed = SdataParse.get('F')
        self.temperature = SdataParse.get('T')

    def get_nearest_cam_image(self):
        # URL of the website you want to fetch
        url = "http://gagnaveita.vegagerdin.is/api/vefmyndavelar2014_1"
        response = requests.get(url)

        if response.status_code == 200:
            site_content = json.loads(response.text)
        else:
            print(f"Failed to fetch website content. Status code: {response.status_code}")

        valuepic = np.array([d['Slod'] for d in site_content])
        valueslat = np.array([d['Breidd'] for d in site_content])
        valueslong = np.array([d['Lengd'] for d in site_content])
        points = np.hstack((valueslat.reshape(-1, 1), valueslong.reshape(-1, 1))

        Sdata = iw.observation_for_closest(self.latitude, self.longitude)
        target_point = np.array([Sdata[1]['lat'], Sdata[1]['lon'])

        points = points
        target = target_point
        kdtree = cKDTree(points)
        nearest_neighbor_index = kdtree.query(target_point)[1]
        nearest_neighbor = points[nearest_neighbor_index]
        distance = kdtree.query(target_point)[0]

        # URL of the image you want to download
        image_url = valuepic[nearest_neighbor_index]

        # Send an HTTP GET request to the image URL
        response = requests.get(image_url)

        # Check if the request was successful (status code 200)
        if response.status_code == 200:
            # Get the binary content of the response
            image_data = response.content
            self.CamImg = image_data

    def display_cam_image(self):
        # Specify the local file path where you want to save the image
        temp_image_path = "temp_image.jpg"

        if self.CamImg is not None:
            # Write the image data to the local file
            with open(temp_image_path, "wb") as file:
                file.write(self.CamImg)
                image = cv2.imread(temp_image_path)

                # Check if the image was loaded successfully
                if image is not None:
                    # Display the image in a window
                    cv2.imshow(image)
        else:
            print("Image wasn't acquired")
