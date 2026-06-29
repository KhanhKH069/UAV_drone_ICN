import time
import psutil
import csv
import argparse
import datetime

try:
    import GPUtil
    has_gpu = True
except ImportError:
    has_gpu = False
    print("GPUtil not installed. GPU monitoring disabled.")

def monitor_resources(duration_sec, interval_sec, out_csv):
    print(f"Monitoring resources for {duration_sec} seconds (Interval: {interval_sec}s)...")
    
    with open(out_csv, mode='w', newline='') as file:
        writer = csv.writer(file)
        headers = ["Timestamp", "CPU_Usage_%", "RAM_Usage_MB"]
        if has_gpu:
            headers.extend(["GPU_Usage_%", "VRAM_Usage_MB"])
        writer.writerow(headers)

        start_time = time.time()
        
        while time.time() - start_time < duration_sec:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().used / (1024 * 1024)
            
            row = [timestamp, cpu, round(ram, 2)]
            
            if has_gpu:
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu = gpus[0]
                    row.extend([gpu.load * 100, gpu.memoryUsed])
                else:
                    row.extend([0, 0])
                    
            writer.writerow(row)
            file.flush()
            time.sleep(interval_sec)

    print(f"Monitoring complete. Data saved to {out_csv}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monitor CPU, RAM, and GPU usage.")
    parser.add_argument("--duration", type=int, default=60, help="Duration in seconds")
    parser.add_argument("--interval", type=float, default=1.0, help="Interval in seconds")
    parser.add_argument("--out_csv", type=str, default="resource_usage.csv", help="Output CSV file")
    args = parser.parse_args()
    
    psutil.cpu_percent(interval=0.1)
    
    monitor_resources(args.duration, args.interval, args.out_csv)
