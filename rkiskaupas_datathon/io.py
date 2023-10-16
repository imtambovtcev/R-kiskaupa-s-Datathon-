import geopandas as gpd


def update_wfs(filename: str):
    '''
    Fetches the latest road data from a Web Feature Service (WFS) and saves it as a GeoJSON file.

    The function connects to the WFS service provided by gis.lmi.is, requests the road data, 
    and saves it to a local GeoJSON file.

    Parameters:
    - filename (str): The path and name of the GeoJSON file to save the road data to.

    Returns:
    None. The function saves the road data to the specified GeoJSON file.

    Example:
    >>> update_wfs("roads_data.geojson")
    This will save the road data to a file named "roads_data.geojson" in the current directory.
    '''

    # 1. Connect to the WFS service
    wfs_url = "https://gis.lmi.is/geoserver/ows?"

    # 2. Build the request URL for the GeoJSON data
    params = {
        "service": "WFS",
        "version": "1.0.0",
        "request": "GetFeature",
        "typeName": "IS_50V:samgongur_linur",
        "outputFormat": "application/json"
    }
    request_url = wfs_url + "&".join([f"{k}={v}" for k, v in params.items()])

    # 3. Retrieve the road data as a GeoDataFrame
    gdf = gpd.read_file(request_url)

    # 4. Save the GeoDataFrame to a GeoJSON file
    gdf.to_file(filename, driver="GeoJSON")
