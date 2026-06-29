import pandas as pd
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import argparse
import os
import math

def latlon_to_xy(lat, lon, lat0, lon0):
    """Convert Lat/Lon (degrees) to X/Y (meters) relative to a home position"""
    R = 6378137.0
    dLat = math.radians(lat - lat0)
    dLon = math.radians(lon - lon0)
    x = dLon * math.cos(math.radians(lat0)) * R
    y = dLat * R
    return x, y

def plot_data(csv_file, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    try:
        df = pd.read_csv(csv_file)
    except FileNotFoundError:
        print(f"Error: Could not find {csv_file}")
        return

    if 'timestamp' in df.columns and 'alt' in df.columns:
        t0 = df['timestamp'].iloc[0]
        if df['timestamp'].max() > 1e10:
            rel_time = (df['timestamp'] - t0) / 1000.0 if df['timestamp'].iloc[0] > 1e12 else (df['timestamp'] - t0)
        else:
            rel_time = df['timestamp'] - t0
            
        plt.figure(figsize=(10, 5))
        plt.plot(rel_time, df['alt'], label='Altitude (m)', color='blue')
        plt.xlabel('Time (seconds)')
        plt.ylabel('Altitude (m)')
        plt.title('UAV Altitude over Time')
        plt.grid(True)
        plt.legend()
        plt.tight_layout()
        plt.savefig(os.path.join(out_dir, 'altitude_plot.png'), dpi=300)
        plt.close()

    if all(col in df.columns for col in ['lat', 'lon', 'alt']):
        lat0, lon0 = df['lat'].iloc[0], df['lon'].iloc[0]
        x_m = []
        y_m = []
        for _, row in df.iterrows():
            x, y = latlon_to_xy(row['lat'], row['lon'], lat0, lon0)
            x_m.append(x)
            y_m.append(y)
            
        fig = plt.figure(figsize=(10, 8))
        ax = fig.add_subplot(111, projection='3d')
        ax.plot(x_m, y_m, df['alt'], label='Flight Path', color='red', linewidth=2)
        ax.set_xlabel('East (meters)')
        ax.set_ylabel('North (meters)')
        ax.set_zlabel('Altitude (meters)')
        ax.set_title('3D Flight Trajectory (Local Coordinate System)')
        plt.legend()
        plt.tight_layout()
        plt.savefig(os.path.join(out_dir, 'trajectory_3d.png'), dpi=300)
        plt.close()
        
    print(f"Saved optimized plots to {out_dir}/")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=str, default="blackbox.csv", help="Path to Blackbox CSV")
    parser.add_argument("--out_dir", type=str, default="plots", help="Directory to save plots")
    args = parser.parse_args()
    plot_data(args.csv, args.out_dir)
