from flask import Flask, render_template
import os

app = Flask(__name__)

@app.route('/')
def home():
    # Get token from environment variable
    mapbox_token = os.environ.get('MAPBOX_TOKEN')
    if not mapbox_token:
        mapbox_token = 'pk.eyJ1Ijoibm9hbWpnYWwiLCJhIjoiY20zbHJ5MzRvMHBxZTJrcW9uZ21pMzMydiJ9.B_aBdP5jxu9nwTm3CoNhlg'
    
    # Print the Mapbox style URL for use in other scripts
    print("\nMapbox Style URL for use in other scripts:")
    print("==========================================")
    print(f"MAP_STYLE = 'mapbox://styles/noamjgal/your-custom-style-id'")
    print("==========================================\n")
    
    return render_template('map.html', mapbox_token=mapbox_token)

if __name__ == '__main__':
    app.run(debug=True)